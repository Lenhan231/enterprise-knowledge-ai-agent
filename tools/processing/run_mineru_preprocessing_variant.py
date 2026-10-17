"""Prepare and run one MinerU Basic preprocessing variant on one track/split."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from run_document_pipeline_performance import ResourceSampler
from prepare_mineru_preprocessing_variants import (
    DPI,
    MAX_SKEW_DEGREES,
    SKEW_SEARCH_LIMIT_DEGREES,
    estimate_skew,
    grayscale_features,
    pdf_from_image,
    rasterize,
    transform_image,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def row_list(manifest: dict[str, Any], track: str, split: str) -> list[dict[str, Any]]:
    rows = manifest.get("items", []) if track == "tables" else manifest.get("pages", [])
    return [row for row in rows if row.get("split") == split]


def item_id(track: str, row: dict[str, Any]) -> str:
    return str(row.get("reference_id") if track == "tables" else row.get("id"))


def find_archives(folder: Path, expected_id: str) -> list[Path]:
    archives = sorted(folder.rglob("*.zip")) if folder.exists() else []
    exact = [path for path in archives if path.stem == expected_id]
    return exact or [path for path in archives if expected_id in path.name]


def parse_directory(input_dir: Path, output_dir: Path, log_path: Path) -> tuple[int, float]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = ["mineru-kit", "parse", str(input_dir), "-o", str(output_dir), "--format", "zip", "--tier", "basic"]
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, text=True)
    return process.returncode, time.perf_counter() - started


def parse_one(input_pdf: Path, item_id_value: str, out_root: Path, logs: Path) -> tuple[bool, float, str | None]:
    page_out = out_root / item_id_value
    page_out.mkdir(parents=True, exist_ok=True)
    command = ["mineru-kit", "parse", str(input_pdf), "-o", str(page_out), "--format", "zip", "--tier", "basic"]
    started = time.perf_counter()
    with (logs / f"{item_id_value}-fallback.log").open("w", encoding="utf-8") as log:
        process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, text=True)
    archives = find_archives(page_out, item_id_value)
    if process.returncode == 0 and archives:
        target = out_root / item_id_value / f"{item_id_value}.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        if archives[0] != target:
            shutil.copy2(archives[0], target)
        return True, time.perf_counter() - started, None
    return False, time.perf_counter() - started, f"exit={process.returncode}; archives={len(archives)}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", choices=("ocr", "tables", "layout"), required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True, help="Directory containing the base manifest and inputs/.")
    parser.add_argument("--split", choices=("development", "validation", "locked_test"), required=True)
    parser.add_argument("--variant", choices=("V0", "V1", "V2", "V3", "V4"), required=True)
    parser.add_argument("--skew-threshold", type=float, choices=(0.5, 1.0, 1.5))
    parser.add_argument("--contrast-threshold", type=float)
    parser.add_argument("--feature-cache", type=Path, help="Optional shared JSON cache for image quality features and skew estimates.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, help="Optional smoke-run cap; do not use limited outputs for scoring.")
    args = parser.parse_args()
    if args.variant == "V4" and (args.skew_threshold is None or args.contrast_threshold is None):
        parser.error("V4 requires --skew-threshold and --contrast-threshold")
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite run output: {args.output}")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cache_path = args.feature_cache
    feature_cache: dict[str, Any] = {"version": 1, "dpi": DPI, "items": {}}
    if cache_path and cache_path.is_file():
        feature_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if feature_cache.get("version") != 1 or feature_cache.get("dpi") != DPI:
            raise ValueError(f"Incompatible feature cache: {cache_path}")
    feature_cache.setdefault("items", {})
    feature_cache_hits = 0
    feature_records_computed = 0
    skew_estimates_computed = 0
    rows = row_list(manifest, args.track, args.split)
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        raise ValueError(f"No {args.split} rows for track {args.track}")

    out = args.output.resolve()
    inputs = out / "inputs"
    inputs.mkdir(parents=True)
    logs = out / "logs"
    logs.mkdir()
    item_meta: list[dict[str, Any]] = []
    preprocess_started = time.perf_counter()
    for row in rows:
        identifier = item_id(args.track, row)
        source = args.input_root / row["input_pdf"]
        if not source.is_file():
            raise FileNotFoundError(f"Input missing for {identifier}: {source}")
        target = inputs / f"{identifier}.pdf"
        before = sha256(source)
        features: dict[str, Any] = {}
        if args.variant == "V0":
            shutil.copy2(source, target)
            decision = "unmodified_control"
        else:
            image, size_points, text_chars = rasterize(source)
            if text_chars:
                shutil.copy2(source, target)
                features = grayscale_features(image)
                decision = "benchmark_input_text_layer_present; left_unchanged"
                image.close()
            else:
                cached = feature_cache["items"].get(before)
                if cached is None:
                    cached = {"grayscale_features": None, "skew_estimate": None}
                    feature_cache["items"][before] = cached
                else:
                    feature_cache_hits += 1
                base_features = cached.get("grayscale_features")
                if base_features is None:
                    base_features = grayscale_features(image)
                    cached["grayscale_features"] = base_features
                    feature_records_computed += 1
                skew_estimate = cached.get("skew_estimate")
                if args.variant in {"V1", "V3", "V4"} and skew_estimate is None:
                    skew_estimate = estimate_skew(image)
                    cached["skew_estimate"] = list(skew_estimate)
                    skew_estimates_computed += 1
                transformed, features = transform_image(
                    image,
                    args.variant,
                    skew_threshold=args.skew_threshold,
                    contrast_threshold=args.contrast_threshold,
                    precomputed_features=base_features,
                    precomputed_skew=tuple(skew_estimate) if skew_estimate is not None else None,
                )
                pdf_from_image(transformed, size_points, target)
                decision = "applied:" + ",".join(
                    name for name, value in (("deskew", features["deskew_applied"]), ("contrast", features["contrast_applied"])) if value
                ) if features["deskew_applied"] or features["contrast_applied"] else "thresholds_not_met"
                transformed.close()
                image.close()
            features["input_text_layer_characters"] = text_chars
        item_meta.append({
            "id": identifier,
            "source_input": row["input_pdf"],
            "source_sha256": before,
            "prepared_sha256": sha256(target),
            "decision": decision,
            "quality_features": features,
        })
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(feature_cache, ensure_ascii=False), encoding="utf-8")
    preprocess_seconds = time.perf_counter() - preprocess_started

    archive_root = out / "mineru-output"
    batch_root = out / "batch-raw"
    resource_sampler = ResourceSampler()
    resource_sampler.start()
    batch_code, batch_seconds = parse_directory(inputs, batch_root, logs / "directory-batch.log")
    output_rows = []
    missing = []
    for row in item_meta:
        identifier = row["id"]
        archives = find_archives(batch_root, identifier)
        target = archive_root / identifier / f"{identifier}.zip"
        if archives:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(archives[0]), target)
            output_rows.append({"id": identifier, "status": "ok", "archive": str(target.relative_to(out)), "mode": "directory_batch"})
        else:
            missing.append((identifier, inputs / f"{identifier}.pdf"))

    fallback_seconds = 0.0
    for identifier, input_pdf in missing:
        ok, elapsed, error = parse_one(input_pdf, identifier, archive_root, logs)
        fallback_seconds += elapsed
        output_rows.append({
            "id": identifier,
            "status": "ok" if ok else "error",
            "archive": f"mineru-output/{identifier}/{identifier}.zip" if ok else None,
            "mode": "single_input_retry",
            "error": error,
        })
    output_rows.sort(key=lambda row: row["id"])
    shutil.rmtree(batch_root, ignore_errors=True)
    resource_usage = resource_sampler.stop()

    split_manifest = {
        "dataset_id": manifest.get("dataset_id"),
        "track": args.track,
        "split": args.split,
        "variant": args.variant,
        "page_count": len(rows),
        "pages": [{"id": item_id(args.track, row), "input_pdf": f"inputs/{item_id(args.track, row)}.pdf", "split": args.split} for row in rows],
    }
    (out / "manifest.json").write_text(json.dumps(split_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run_meta = {
        "engine": "mineru",
        "dataset_id": manifest.get("dataset_id"),
        "track": args.track,
        "split": args.split,
        "variant": args.variant,
        "tier": "basic",
        "mineru_package_version": "4.0.12 (pinned by kernel)",
        "dpi": DPI,
        "transform_config": {
            "skew_threshold_degrees": args.skew_threshold,
            "max_skew_degrees": MAX_SKEW_DEGREES,
            "skew_search_limit_degrees": SKEW_SEARCH_LIMIT_DEGREES,
            "contrast_percentiles": [1, 99],
            "contrast_p95_p5_threshold": args.contrast_threshold,
        },
        "limit_smoke_run": args.limit,
        "preprocess_seconds": round(preprocess_seconds, 3),
        "feature_cache": {
            "path": str(cache_path) if cache_path else None,
            "hits": feature_cache_hits,
            "feature_records_computed": feature_records_computed,
            "skew_estimates_computed": skew_estimates_computed,
        },
        "deskewed_items": sum(bool(row["quality_features"].get("deskew_applied")) for row in item_meta),
        "contrast_normalized_items": sum(bool(row["quality_features"].get("contrast_applied")) for row in item_meta),
        "total_transforms_applied": sum(
            bool(row["quality_features"].get("deskew_applied")) + bool(row["quality_features"].get("contrast_applied"))
            for row in item_meta
        ),
        "batch_inference_seconds": round(batch_seconds, 3),
        "directory_batch_exit_code": batch_code,
        "single_input_fallback_seconds": round(fallback_seconds, 3),
        "inference_resources": resource_usage,
        "source_items": item_meta,
        "outputs": output_rows,
        "output_count": sum(row["status"] == "ok" for row in output_rows),
        "status": "complete" if len(output_rows) == len(rows) and all(row["status"] == "ok" for row in output_rows) else "incomplete",
    }
    (out / "run-metadata.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"track": args.track, "split": args.split, "variant": args.variant, "status": run_meta["status"], "outputs": run_meta["output_count"], "items": len(rows), "batch_seconds": batch_seconds, "fallback_items": len(missing), "output": str(out)}, ensure_ascii=False), flush=True)
    if run_meta["status"] != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
