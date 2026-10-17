"""Build reproducible MinerU preprocessing inputs from the fixed benchmark manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/evaluation/document-pipelines"
TRACKS = {
    "ocr": BASE / "ocr/reference/manifest.json",
    "tables": BASE / "tables/reference/manifest.json",
    "layout": BASE / "layout/inputs/manifest.json",
}
SPLITS = ("development", "validation", "locked_test")
DPI = 180
MAX_SKEW_DEGREES = 5.0
SKEW_SEARCH_LIMIT_DEGREES = 10.0
SKEW_SEARCH_STEP = 0.25


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def get_rows(track: str, manifest: dict[str, Any], split: str) -> list[dict[str, Any]]:
    rows = manifest.get("items", []) if track == "tables" else manifest.get("pages", [])
    return [row for row in rows if row.get("split") == split]


def row_id(track: str, row: dict[str, Any]) -> str:
    return str(row.get("reference_id") if track == "tables" else row.get("id"))


def source_path(track: str, manifest_path: Path, row: dict[str, Any]) -> Path:
    path = manifest_path.parent / row["input_pdf"]
    if not path.is_file():
        raise FileNotFoundError(f"Missing {track} input for {row_id(track, row)}: {path}")
    return path


def rasterize(pdf_path: Path, dpi: int = DPI) -> tuple[Image.Image, tuple[float, float], int]:
    document = pdfium.PdfDocument(str(pdf_path))
    try:
        if len(document) != 1:
            raise ValueError(f"Expected a one-page PDF: {pdf_path} has {len(document)} pages")
        page = document[0]
        width, height = page.get_size()
        text_page = page.get_textpage()
        text_chars = len(text_page.get_text_range().strip())
        bitmap = page.render(scale=dpi / 72)
        image = bitmap.to_pil().convert("RGB")
        bitmap.close()
        text_page.close()
        page.close()
    finally:
        document.close()
    return image, (float(width), float(height)), text_chars


def grayscale_features(image: Image.Image) -> dict[str, float]:
    gray = np.asarray(ImageOps.grayscale(image), dtype=np.uint8)
    p1, p5, p95, p99 = (float(value) for value in np.percentile(gray, [1, 5, 95, 99]))
    if min(gray.shape) >= 3:
        laplacian = (
            -4 * gray[1:-1, 1:-1].astype(np.float32)
            + gray[:-2, 1:-1]
            + gray[2:, 1:-1]
            + gray[1:-1, :-2]
            + gray[1:-1, 2:]
        )
        edge_variance = float(np.var(laplacian))
    else:
        edge_variance = 0.0
    return {
        "gray_p1": p1,
        "gray_p5": p5,
        "gray_p95": p95,
        "gray_p99": p99,
        "contrast_p95_p5": p95 - p5,
        "laplacian_variance": edge_variance,
    }


def projection_score(image: Image.Image) -> float:
    gray = np.asarray(ImageOps.grayscale(image), dtype=np.uint8)
    p5, p95 = (float(value) for value in np.percentile(gray, [5, 95]))
    threshold = (p5 + p95) / 2
    background_is_light = float(np.median(gray)) >= threshold
    foreground = gray < threshold if background_is_light else gray > threshold
    foreground_by_row = np.count_nonzero(foreground, axis=1).astype(np.float64)
    return float(np.var(foreground_by_row))


def _border_background_color(image: Image.Image) -> tuple[int, int, int]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    border = np.concatenate((rgb[0, :, :], rgb[-1, :, :], rgb[:, 0, :], rgb[:, -1, :]), axis=0)
    return tuple(int(value) for value in np.median(border, axis=0))


def estimate_skew(image: Image.Image) -> tuple[float, float]:
    preview = image.convert("L")
    preview.thumbnail((900, 900), Image.Resampling.LANCZOS)
    if min(preview.size) < 80:
        return 0.0, 0.0

    background = int(np.median(np.asarray(preview, dtype=np.uint8)))
    candidates = np.arange(-SKEW_SEARCH_LIMIT_DEGREES, SKEW_SEARCH_LIMIT_DEGREES + 0.001, SKEW_SEARCH_STEP)
    scores: list[float] = []
    for angle in candidates:
        rotated = preview.rotate(
            float(angle), resample=Image.Resampling.BILINEAR, fillcolor=background, expand=False
        )
        scores.append(projection_score(rotated))
        rotated.close()
    best_index = int(np.argmax(scores))
    return float(candidates[best_index]), float(scores[best_index])


def apply_contrast(image: Image.Image, features: dict[str, float]) -> Image.Image:
    values = np.asarray(ImageOps.grayscale(image), dtype=np.float32)
    low, high = features["gray_p1"], features["gray_p99"]
    if high <= low:
        return ImageOps.grayscale(image)
    scaled = np.clip((values - low) * (255.0 / (high - low)), 0, 255).astype(np.uint8)
    return Image.fromarray(scaled, mode="L")


def transform_image(
    image: Image.Image,
    variant: str,
    *,
    skew_threshold: float | None,
    contrast_threshold: float | None,
    precomputed_features: dict[str, float] | None = None,
    precomputed_skew: tuple[float, float] | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    features = precomputed_features or grayscale_features(image)
    wants_deskew = variant in {"V1", "V3"} or variant == "V4"
    wants_contrast = variant in {"V2", "V3"} or variant == "V4"
    angle, angle_score = (precomputed_skew or estimate_skew(image)) if wants_deskew else (0.0, 0.0)
    deskew = wants_deskew and abs(angle) <= MAX_SKEW_DEGREES and (
        abs(angle) >= 0.5
        if variant in {"V1", "V3"}
        else abs(angle) >= float(skew_threshold or 0)
    )
    contrast = wants_contrast and (
        variant in {"V2", "V3"}
        or features["contrast_p95_p5"] < float(contrast_threshold or -math.inf)
    )

    result = image.copy()
    if deskew and angle:
        rotated = result.rotate(
            angle, resample=Image.Resampling.BICUBIC, fillcolor=_border_background_color(result), expand=False
        )
        result.close()
        result = rotated
    if contrast:
        contrast_features = grayscale_features(result)
        contrasted = apply_contrast(result, contrast_features)
        features["contrast_mapping_p1"] = contrast_features["gray_p1"]
        features["contrast_mapping_p99"] = contrast_features["gray_p99"]
        result.close()
        result = contrasted

    return result, {
        **features,
        "estimated_skew_degrees": angle,
        "skew_projection_score": angle_score,
        "deskew_applied": bool(deskew and angle),
        "contrast_applied": bool(contrast),
        "contrast_method": "grayscale_p1_p99_stretch" if contrast else None,
    }


def pdf_from_image(image: Image.Image, size_points: tuple[float, float], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    dpi_x = image.width * 72 / size_points[0]
    dpi_y = image.height * 72 / size_points[1]
    image.save(output, format="PDF", resolution=(dpi_x + dpi_y) / 2)


def variant_name(variant: str, skew_threshold: float | None, contrast_quantile: int | None) -> str:
    if variant != "V4":
        return variant
    if skew_threshold not in {0.5, 1.0, 1.5} or contrast_quantile not in {25, 50}:
        raise ValueError("V4 requires --skew-threshold 0.5|1.0|1.5 and --contrast-quantile 25|50")
    return f"V4-skew{skew_threshold:g}-contrast{contrast_quantile}"


def derive_contrast_threshold(quantile: int) -> tuple[float, dict[str, Any]]:
    manifest_path = TRACKS["ocr"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    values = []
    for row in get_rows("ocr", manifest, "development"):
        image, _, _ = rasterize(source_path("ocr", manifest_path, row))
        values.append(grayscale_features(image)["contrast_p95_p5"])
        image.close()
    threshold = float(np.percentile(values, quantile))
    return threshold, {
        "population": "OCR development reference crops only",
        "sample_count": len(values),
        "quantile": quantile,
        "contrast_p95_p5_threshold": threshold,
    }


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    track = args.track
    manifest_path = TRACKS[track]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected_splits = SPLITS if args.split == "all" else (args.split,)
    name = variant_name(args.variant, args.skew_threshold, args.contrast_quantile)
    contrast_threshold = None
    threshold_source = None
    if args.variant == "V4":
        contrast_threshold, threshold_source = derive_contrast_threshold(int(args.contrast_quantile))

    out_dir = args.output.resolve() / name / track
    if out_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing variant inputs: {out_dir}")
    out_dir.mkdir(parents=True)
    pages: list[dict[str, Any]] = []
    for split in selected_splits:
        split_rows = get_rows(track, manifest, split)
        for row in split_rows:
            item_id = row_id(track, row)
            original = source_path(track, manifest_path, row)
            target = out_dir / split / "inputs" / f"{item_id}.pdf"
            target.parent.mkdir(parents=True, exist_ok=True)
            features: dict[str, Any] = {}
            text_chars = 0
            if args.variant == "V0":
                try:
                    os.link(original, target)
                except OSError:
                    shutil.copy2(original, target)
                reason = "unmodified_control"
            else:
                image, size_points, text_chars = rasterize(original)
                if text_chars > 0:
                    try:
                        os.link(original, target)
                    except OSError:
                        shutil.copy2(original, target)
                    features = grayscale_features(image)
                    reason = "benchmark_input_text_layer_present; left_unchanged"
                    image.close()
                else:
                    processed, features = transform_image(
                        image,
                        args.variant,
                        skew_threshold=args.skew_threshold,
                        contrast_threshold=contrast_threshold,
                    )
                    pdf_from_image(processed, size_points, target)
                    deskew = features["deskew_applied"]
                    contrast = features["contrast_applied"]
                    reason = "applied:" + ",".join(
                        name for name, applied in (("deskew", deskew), ("contrast", contrast)) if applied
                    ) if deskew or contrast else "quality_thresholds_not_met; left_pixels_unchanged"
                    processed.close()
                    image.close()

            pages.append({
                "id": item_id,
                "input_pdf": f"inputs/{item_id}.pdf",
                "output_pdf": f"{split}/inputs/{item_id}.pdf",
                "split": split,
                "issuer": row.get("issuer"),
                "source_pdf": row.get("source_file"),
                "source_document_sha256": row.get("source_pdf_sha256"),
                "benchmark_input_pdf": row["input_pdf"],
                "benchmark_input_sha256": sha256(original),
                "output_sha256": sha256(target),
                "input_text_layer_characters": text_chars,
                "decision": reason,
                "quality_features": features,
            })

    run_manifest = {
        "dataset_id": f"mineru-preprocessing-{track}-{name.lower()}",
        "base_dataset_id": manifest.get("dataset_id"),
        "track": track,
        "variant": name,
        "source_split_counts": manifest.get("split_counts", manifest.get("split_table_counts")),
        "included_splits": list(selected_splits),
        "dpi": DPI,
        "transform": {
            "deskew_threshold_degrees": args.skew_threshold if args.variant == "V4" else None,
            "max_deskew_degrees": MAX_SKEW_DEGREES,
            "skew_search_limit_degrees": SKEW_SEARCH_LIMIT_DEGREES,
            "contrast_percentiles": [1, 99],
            "contrast_threshold_source": threshold_source,
        },
        "page_count": len(pages),
        "pages": pages,
    }
    for split in selected_splits:
        split_manifest = {
            **run_manifest,
            "split": split,
            "page_count": sum(page["split"] == split for page in pages),
            "pages": [page for page in pages if page["split"] == split],
        }
        (out_dir / split / "manifest.json").write_text(
            json.dumps(split_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    (out_dir / "variant-manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"variant": name, "track": track, "items": len(pages), "output": str(out_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", choices=tuple(TRACKS), required=True)
    parser.add_argument("--split", choices=(*SPLITS, "all"), default="development")
    parser.add_argument("--variant", choices=("V0", "V1", "V2", "V3", "V4"), required=True)
    parser.add_argument("--skew-threshold", type=float, choices=(0.5, 1.0, 1.5))
    parser.add_argument("--contrast-quantile", type=int, choices=(25, 50))
    parser.add_argument("--output", type=Path, default=BASE / "results/mineru-preprocessing/inputs")
    args = parser.parse_args()
    if args.variant == "V4" and (args.skew_threshold is None or args.contrast_quantile is None):
        parser.error("V4 requires both --skew-threshold and --contrast-quantile")
    print(json.dumps(prepare(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
