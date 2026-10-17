"""Inventory development/validation pages for production PDF text cleaning."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from core.document_processing.processors.pdf.scanned.ocr import PDFOCRProcessor

BASE = ROOT / "artifacts/evaluation/document-pipelines"
DEFAULT_INPUT = BASE / "layout/inputs/manifest.json"
DEFAULT_OUTPUT = BASE / "results/follow-up-metrics/cleaning-candidates-v1.json"
PAGE_COUNTER = re.compile(r"\b(?:page|trang)\s+\d+\s*(?:/|of|trên)\s*\d+\s*$", re.IGNORECASE)
SPLITS = {"development", "validation"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def trailing_page_counter(text: str) -> str | None:
    lines = text.splitlines()
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        return line if len(line) <= 180 and PAGE_COUNTER.search(line) else None
    return None


def inventory(input_path: Path, output_path: Path) -> dict:
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite candidate inventory: {output_path}")
    source_manifest = json.loads(input_path.read_text(encoding="utf-8"))
    rows = [row for row in source_manifest["pages"] if row.get("split") in SPLITS]
    pages = []
    source_hashes = {}
    page_counter_candidates = 0

    by_source: dict[str, list[dict]] = {}
    for row in rows:
        by_source.setdefault(row["source_file"], []).append(row)

    for source_file, source_rows in sorted(by_source.items()):
        source_path = ROOT / source_file
        actual_hash = file_sha256(source_path)
        expected = {row["source_pdf_sha256"] for row in source_rows}
        if expected != {actual_hash}:
            raise ValueError(f"Source hash mismatch: {source_path}")
        with fitz.open(source_path) as document:
            for row in source_rows:
                page_number = int(row["page_number_source"])
                page = document[page_number - 1]
                native_text = page.get_text("text").strip()
                footer = trailing_page_counter(native_text)
                if footer:
                    page_counter_candidates += 1

                # Match the production branch: pages with native text use
                # full-page OCR when _needs_ocr is true, otherwise large
                # embedded-image regions are eligible for OCR.
                if len(native_text) < 50:
                    continue
                regions = PDFOCRProcessor._embedded_image_regions(page)
                if not regions:
                    continue
                full_page_ocr = PDFOCRProcessor._needs_ocr(page, native_text)
                pages.append({
                    "id": row["id"],
                    "source_file": source_file,
                    "source_pdf_sha256": actual_hash,
                    "source_page_number": page_number,
                    "issuer": row["issuer"],
                    "split": row["split"],
                    "native_text_char_count": len(native_text),
                    "ocr_path_candidate": "full_page" if full_page_ocr else "embedded_image_regions",
                    "embedded_image_regions": [
                        {
                            "bbox": [round(value, 2) for value in rect],
                            "page_area_fraction": round(rect.get_area() / max(page.rect.get_area(), 1), 4),
                        }
                        for rect in regions
                    ],
                    "candidate_status": "requires_visual_review_for_actual_text_and_cleaning_labels",
                })
        source_hashes[source_file] = actual_hash

    split_counts = Counter(page["split"] for page in pages)
    result = {
        "dataset_id": "vietnam-enterprise-cleaning-candidates-v1",
        "status": "unreviewed_candidate_inventory_no_pipeline_predictions",
        "source_manifest": str(input_path.relative_to(ROOT)),
        "source_pdf_count": len(source_hashes),
        "candidate_page_count": len(pages),
        "split_counts": {split: split_counts[split] for split in sorted(SPLITS)},
        "issuer_count": len({page["issuer"] for page in pages}),
        "candidate_rule": "Native text length >= 50 and at least one region returned by the production PDFOCRProcessor._embedded_image_regions helper; locked-test pages excluded.",
        "production_helpers": [
            "PDFOCRProcessor._needs_ocr",
            "PDFOCRProcessor._embedded_image_regions",
        ],
        "trailing_page_counter_candidates_in_dev_validation": page_counter_candidates,
        "pages": pages,
        "source_pdfs": source_hashes,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = inventory(args.input, args.output)
    print(json.dumps({
        "status": result["status"],
        "candidate_page_count": result["candidate_page_count"],
        "split_counts": result["split_counts"],
        "issuer_count": result["issuer_count"],
        "trailing_page_counter_candidates_in_dev_validation": result["trailing_page_counter_candidates_in_dev_validation"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
