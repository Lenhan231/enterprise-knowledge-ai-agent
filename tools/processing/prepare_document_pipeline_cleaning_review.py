"""Prepare a prediction-blind review packet for production PDF text cleaning."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/evaluation/document-pipelines"
DEFAULT_INVENTORY = BASE / "results/follow-up-metrics/cleaning-candidates-v1.json"
DEFAULT_OUTPUT = BASE / "human-review/cleaning-pilot-v3"
DEFAULT_RESULTS = BASE / "results/follow-up-metrics/cleaning-pilot-v1"
sys.path.insert(0, str(ROOT / "src"))

from core.document_processing.processors.pdf.processor import PDFProcessor  # noqa: E402
from core.document_processing.processors.pdf.digital_born.native_text import (  # noqa: E402
    extract_native_page_text,
)
from prepare_document_pipeline_human_review import write_review_page  # noqa: E402


def fragments(text: str, source: str) -> list[dict]:
    result = []
    for line in text.splitlines():
        for fragment in re.split(r"(?<=[.!?])\s+", " ".join(line.split())):
            fragment = fragment.strip()
            if fragment:
                result.append({"source": source, "text": fragment, "classification": ""})
    return result


def render_page(page: fitz.Page, output: Path, regions: list[dict] | None = None) -> None:
    pixmap = page.get_pixmap(dpi=144, alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    if regions:
        draw = ImageDraw.Draw(image)
        scale_x = pixmap.width / max(page.rect.width, 1)
        scale_y = pixmap.height / max(page.rect.height, 1)
        for region in regions:
            rect = fitz.Rect(region["bbox"]) * page.rotation_matrix
            box = (
                (rect.x0 - page.rect.x0) * scale_x,
                (rect.y0 - page.rect.y0) * scale_y,
                (rect.x1 - page.rect.x0) * scale_x,
                (rect.y1 - page.rect.y0) * scale_y,
            )
            draw.rectangle(box, outline="#ff7a00", width=max(3, pixmap.width // 700))
            draw.text((box[0] + 3, box[1] + 3), "OCR region", fill="#d9480f", stroke_width=2, stroke_fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "JPEG", quality=88, optimize=True)
    image.close()


def build_review_from_saved_outputs(
    inventory_path: Path, production_path: Path, output: Path,
    sample_size: int | None,
) -> dict:
    """Build a smaller, OCR-only annotation view without rerunning inference."""
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite review packet: {output}")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    if inventory["dataset_id"] != production["dataset_id"]:
        raise ValueError("Candidate inventory and saved production outputs do not match")
    candidate_by_id = {row["id"]: row for row in inventory["pages"]}
    items = []
    for result in production["pages"]:
        candidate = candidate_by_id.get(result["id"])
        if candidate is None or candidate["split"] != result["split"]:
            raise ValueError(f"No matching candidate inventory row for {result['id']}")
        items.append({
            "id": result["id"],
            "split": result["split"],
            "dataset_id": production["dataset_id"],
            "issuer": result["issuer"],
            "source_file": result["source_file"],
            "source_page_number": result["source_page_number"],
            "image": f"../cleaning-pilot-v1/images/{result['id']}.jpg",
            "ocr_path_candidate": candidate["ocr_path_candidate"],
            "native_text_context": result["native_text"],
            "reviewed_ocr_spans_json": json.dumps(
                fragments(result["ocr_text"], "ocr"), ensure_ascii=False, indent=2,
            ),
        })
    if sample_size is not None:
        items = _select_review_sample(items, candidate_by_id, sample_size)
    output.mkdir(parents=True)
    image_dir = output / "images"
    image_dir.mkdir()
    for item in items:
        with fitz.open(ROOT / item["source_file"]) as document:
            candidate = candidate_by_id[item["id"]]
            render_page(
                document[int(item["source_page_number"]) - 1],
                image_dir / f"{item['id']}.jpg",
                candidate["embedded_image_regions"],
            )
        item["image"] = f"images/{item['id']}.jpg"
    write_review_page(
        output / "review.html",
        "Production PDF cleaning review",
        "cleaning",
        items,
        [
            ("native_text_context", "Native PDF text context (read-only)"),
            (
                "reviewed_ocr_spans_json",
                "Classify each OCR span as new_valid, duplicate, or noise",
            ),
        ],
    )
    summary = {
        "dataset_id": production["dataset_id"],
        "status": "unreviewed_cleaner_output_blind_review_packet",
        "page_count": len(items),
        "candidate_page_count": len(production["pages"]),
        "sample_method": "deterministic split and issuer-stratified pilot; includes the only full-page OCR candidate" if sample_size is not None else "all candidate pages",
        "split_counts": {
            split: sum(item["split"] == split for item in items)
            for split in ("development", "validation")
        },
        "ocr_span_count": sum(
            len(json.loads(item["reviewed_ocr_spans_json"])) for item in items
        ),
        "pages_with_ocr_spans": sum(bool(item["reviewed_ocr_spans_json"] != "[]") for item in items),
        "review_html": str((output / "review.html").relative_to(ROOT)),
        "production_output": str(production_path.resolve().relative_to(ROOT)),
        "reviewed_page_ids": [item["id"] for item in items],
    }
    (output / "packet-manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return summary


def _select_review_sample(
    items: list[dict], candidates: dict[str, dict], sample_size: int,
) -> list[dict]:
    if sample_size < 2:
        raise ValueError("Pilot sample size must be at least 2 to include both splits")
    eligible = [
        item for item in items
        if json.loads(item["reviewed_ocr_spans_json"])
    ]
    if len(eligible) < sample_size:
        raise ValueError(f"Only {len(eligible)} pages have OCR spans; cannot sample {sample_size}")
    targets = {"development": sample_size // 2, "validation": sample_size - sample_size // 2}
    selected = []
    for split in ("development", "validation"):
        pool = [item for item in eligible if item["split"] == split]
        pool.sort(key=lambda item: hashlib.sha256(f"cleaning-pilot-v1:{item['id']}".encode()).hexdigest())
        if split == "validation":
            full_page = next((item for item in pool if candidates[item["id"]]["ocr_path_candidate"] == "full_page"), None)
            if full_page:
                selected.append(full_page)
                pool.remove(full_page)
        seen_issuers = {item["issuer"] for item in selected if item["split"] == split}
        needed = targets[split] - sum(item["split"] == split for item in selected)
        picked = []
        for item in pool:
            if item["issuer"] in seen_issuers:
                continue
            picked.append(item)
            seen_issuers.add(item["issuer"])
            if len(picked) == needed:
                break
        selected.extend(picked)
        if sum(item["split"] == split for item in selected) < targets[split]:
            selected_ids = {item["id"] for item in selected}
            needed = targets[split] - sum(item["split"] == split for item in selected)
            selected.extend([item for item in pool if item["id"] not in selected_ids][:needed])
    return selected


def _page_texts(extracted: str, page_numbers: list[int]) -> dict[int, str]:
    matches = list(re.finditer(r"\n--- Page (\d+) ---\n", extracted))
    texts = {}
    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(extracted)
        texts[page_number] = extracted[match.end():end].strip()
    return {number: texts.get(number, "") for number in page_numbers}


def build(inventory_path: Path, output: Path, results_path: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite review packet: {output}")
    if results_path.exists():
        raise FileExistsError(f"Refusing to overwrite cleaning results: {results_path}")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    results_path.mkdir(parents=True)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for candidate in inventory["pages"]:
        grouped[candidate["source_file"]].append(candidate)

    # Use normal upload's parser branch and OCR defaults; disable table parsing
    # to isolate the shared text-cleaning operations.
    processor = PDFProcessor({
        "parser_engine": "pymupdf_tesseract",
        "ocr_fallback": True,
        "extract_tables": False,
    })
    items = []
    result_items = []
    for source_file, candidates in sorted(grouped.items()):
        source_path = ROOT / source_file
        page_numbers = sorted({int(candidate["source_page_number"]) for candidate in candidates})
        processor.page_numbers = set(page_numbers)
        processor.text_extractor.page_numbers = set(page_numbers)
        captured: dict[int, list[str]] = defaultdict(list)
        original_page_ocr = processor.text_extractor._ocr_page
        original_word_ocr = processor.text_extractor._ocr_page_words

        def capture_page_ocr(page, pixmap=None, **kwargs):
            text = original_page_ocr(page, pixmap, **kwargs)
            if text:
                captured[page.number + 1].append(text)
            return text

        def capture_word_ocr(page, pixmap=None, **kwargs):
            words = original_word_ocr(page, pixmap, **kwargs)
            text = processor.ocr._ocr_words_to_text(words).strip()
            if text:
                captured[page.number + 1].append(text)
            return words

        processor.text_extractor._ocr_page = capture_page_ocr
        processor.text_extractor._ocr_page_words = capture_word_ocr
        try:
            extracted, _, _, _, _, _, _ = processor._extract_pdf(str(source_path))
        finally:
            processor.text_extractor._ocr_page = original_page_ocr
            processor.text_extractor._ocr_page_words = original_word_ocr
        cleaned_by_page = _page_texts(extracted, page_numbers)

        with fitz.open(source_path) as document:
            for candidate in candidates:
                page_number = int(candidate["source_page_number"])
                page = document[page_number - 1]
                image_rel = f"images/{candidate['id']}.jpg"
                render_page(page, output / image_rel)
                native_text = extract_native_page_text(page, preserve_layout=True).strip()
                ocr_text = "\n".join(captured.get(page_number, [])).strip()
                cleaned_text = cleaned_by_page[page_number]
                items.append({
                    "id": candidate["id"],
                    "split": candidate["split"],
                    "dataset_id": inventory["dataset_id"],
                    "issuer": candidate["issuer"],
                    "source_file": source_file,
                    "source_page_number": page_number,
                    "image": image_rel,
                    "ocr_path_candidate": candidate["ocr_path_candidate"],
                    "reviewed_native_spans_json": json.dumps(
                        fragments(native_text, "native"), ensure_ascii=False, indent=2,
                    ),
                    "reviewed_ocr_spans_json": json.dumps(
                        fragments(ocr_text, "ocr"), ensure_ascii=False, indent=2,
                    ),
                    "native_text_char_count": len(native_text),
                    "ocr_span_count": len(fragments(ocr_text, "ocr")),
                    "cleaned_output_char_count": len(cleaned_text),
                })
                result_items.append({
                    "id": candidate["id"],
                    "split": candidate["split"],
                    "issuer": candidate["issuer"],
                    "source_file": source_file,
                    "source_page_number": page_number,
                    "native_text": native_text,
                    "ocr_text": ocr_text,
                    "cleaned_text": cleaned_text,
                })

    write_review_page(
        output / "review.html",
        "Production PDF cleaning review",
        "cleaning",
        items,
        [
            (
                "reviewed_native_spans_json",
                "Classify each native span as valid, noise, or page_counter",
            ),
            (
                "reviewed_ocr_spans_json",
                "Classify each OCR span as new_valid, duplicate, or noise",
            ),
        ],
    )
    production_outputs = {
        "dataset_id": inventory["dataset_id"],
        "status": "unreviewed_production_extraction_for_later_scoring",
        "configuration": processor.config,
        "pages": result_items,
    }
    (results_path / "production-output.json").write_text(
        json.dumps(production_outputs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        "dataset_id": inventory["dataset_id"],
        "status": "unreviewed_prediction_blind_review_packet",
        "page_count": len(items),
        "split_counts": {
            split: sum(item["split"] == split for item in items)
            for split in ("development", "validation")
        },
        "review_html": str((output / "review.html").relative_to(ROOT)),
        "ocr_engine": "Tesseract through PDFProcessor production OCR path",
        "production_output": str((results_path / "production-output.json").relative_to(ROOT)),
        "production_cleaned_output_saved_for_later_scoring": True,
    }
    (output / "packet-manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument(
        "--reuse-production-output", type=Path,
        help="Build only the review HTML from saved outputs; do not rerun Tesseract.",
    )
    parser.add_argument("--sample-size", type=int, default=10,
                        help="Pilot pages to review from saved outputs (default: 10).")
    parser.add_argument("--all-pages", action="store_true",
                        help="Include all candidates instead of the default pilot sample.")
    args = parser.parse_args()
    if args.reuse_production_output:
        print(json.dumps(build_review_from_saved_outputs(
            args.inventory, args.reuse_production_output, args.output,
            None if args.all_pages else args.sample_size,
        ), ensure_ascii=False, indent=2))
        return
    summary = build(args.inventory, args.output, args.results)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
