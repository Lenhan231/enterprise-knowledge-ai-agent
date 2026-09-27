#!/usr/bin/env python3
"""Extract reviewable financial metric candidates from parsed report pages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.analytics.metric_candidates import METRICS, candidates  # noqa: E402


def extract_metric_tables(pdf_path: Path) -> list[dict]:
    """Run slower table detection only on pages whose text layer has KPI labels."""
    import fitz

    from core.document_processing.processors.pdf_processor import PDFProcessor

    labels = [label.casefold() for metric in METRICS.values() for label in metric]
    tables = []
    with fitz.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            page_text = page.get_text("text").casefold()
            if any(label in page_text for label in labels):
                tables.extend(PDFProcessor._extract_page_tables(page, page_number))
    return tables


def extract_visual_pages(pdf_path: Path) -> list[dict]:
    """Keep PDF span positions for matching prominent KPI figures to nearby labels."""
    import fitz

    pages = []
    with fitz.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            spans = [
                {"text": span["text"], "bbox": span["bbox"], "font_size": span["size"]}
                for block in page.get_text("dict")["blocks"]
                for line in block.get("lines", [])
                for span in line["spans"]
                if span["text"].strip()
            ]
            pages.append({"page_number": page_number, "spans": spans})
    return pages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--save-candidates", action="store_true")
    parser.add_argument("--ids", nargs="+", help="Optional manifest document IDs to process")
    args = parser.parse_args()
    manifest = json.loads((REPO_ROOT / "data/vietnam_enterprises/manifest.json").read_text())
    reports = [doc for doc in manifest["documents"] if doc["document_type"] in {"annual_report", "financial_statements_section"}]
    if args.ids:
        known_ids = {doc["document_id"] for doc in reports}
        unknown_ids = set(args.ids) - known_ids
        if unknown_ids:
            parser.error(f"Unknown or unsupported report IDs: {', '.join(sorted(unknown_ids))}")
        reports = [doc for doc in reports if doc["document_id"] in set(args.ids)]
    rows = []
    for document in reports:
        raw_pdf = REPO_ROOT / "data/raw/vietnam_enterprises" / document["ticker"].lower() / f"{document['document_id'].lower()}.pdf"
        if not raw_pdf.is_file():
            print(f"missing raw report: {raw_pdf}", file=sys.stderr)
            continue
        from core.document_processing.processors.pdf_processor import PDFProcessor

        processor = PDFProcessor({
            "paddle_layout": False,
            "ocr_fallback": True,
            "ocr_language": "vie+eng",
            "extract_tables": False,
            "chunking_strategy": "fixed",
            "chunk_size": 1200,
            "chunk_overlap": 150,
        })
        processed = processor.process({"metadata": document, "content": raw_pdf.read_bytes()})
        pages = [{"metadata": chunk["metadata"], "text": chunk["text"]} for chunk in processed["chunks"]]
        tables = extract_metric_tables(raw_pdf)
        visual_pages = extract_visual_pages(raw_pdf)
        rows.extend(candidates(pages, document, tables, visual_pages))
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    if rows and args.save_candidates and not args.dry_run:
        from core.database.document_repository import DocumentRepository
        repository = DocumentRepository()
        try:
            for document_id in {row["document_id"] for row in rows}:
                repository.save_metric_candidates(
                    document_id, [row for row in rows if row["document_id"] == document_id]
                )
        finally:
            repository.close()
        print(f"Saved {len(rows)} candidates as needs_review; analytics still uses verified metrics only.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
