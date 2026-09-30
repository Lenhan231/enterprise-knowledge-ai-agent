#!/usr/bin/env python3
"""Extract reviewable financial metric candidates from parsed report pages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
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
    parser.add_argument("--llm", action="store_true", help="Extract candidate KPIs from parser-selected pages with GROQ_API_KEY")
    parser.add_argument("--page-selection-only", action="store_true", help="Print selected-page evidence and make no LLM calls")
    parser.add_argument("--max-pages", type=int, default=10, help="Maximum financial pages sent to the LLM per report (1-10)")
    parser.add_argument("--ids", nargs="+", help="Optional manifest document IDs to process")
    args = parser.parse_args()
    if args.page_selection_only and args.llm:
        parser.error("--page-selection-only and --llm cannot be used together")
    if not 1 <= args.max_pages <= 10:
        parser.error("--max-pages must be between 1 and 10")
    manifest = json.loads((REPO_ROOT / "data/vietnam_enterprises/manifest.json").read_text())
    reports = [doc for doc in manifest["documents"] if doc["document_type"] in {"annual_report", "financial_statements_section"}]
    if args.ids:
        known_ids = {doc["document_id"] for doc in reports}
        unknown_ids = set(args.ids) - known_ids
        if unknown_ids:
            parser.error(f"Unknown or unsupported report IDs: {', '.join(sorted(unknown_ids))}")
        reports = [doc for doc in reports if doc["document_id"] in set(args.ids)]
    rows = []
    selection_runs = []
    llm = None
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
        if args.page_selection_only or args.llm:
            from core.analytics.financial_extraction import (
                extract_financial_candidates, merge_candidate_sources, select_financial_pages,
            )
            import fitz
        else:
            from core.analytics.financial_extraction import (
                merge_candidate_sources, select_financial_pages,
            )

        selected = select_financial_pages(pages, tables, args.max_pages)
        if args.page_selection_only or args.llm:
            with fitz.open(raw_pdf) as source_pdf:
                total_pages = len(source_pdf)
            selection_runs.append({
                "document_id": document["document_id"],
                "total_pages": total_pages,
                "selected_pages": [
                    {
                        "page_number": page["page_number"],
                        "text_preview": page["text"][:500],
                        **page["selection_signals"],
                    }
                    for page in selected
                ],
            })
            if args.page_selection_only:
                continue
        selected_page_numbers = {page["page_number"] for page in selected}
        text_evidence_page_numbers = {
            page["page_number"] for page in selected
            if page["selection_signals"]["summary_area_with_metric"]
        }
        selected_chunks = [
            chunk for chunk in pages
            if int(chunk["metadata"].get("page_number") or 0) in selected_page_numbers
        ]
        selected_tables = [
            table for table in tables
            if int(table.get("page_number") or 0) in selected_page_numbers
        ]
        selected_visual_pages = [
            page for page in visual_pages
            if int(page.get("page_number") or 0) in selected_page_numbers
        ]
        parser_candidates = candidates(
            selected_chunks, document, selected_tables, selected_visual_pages,
            text_evidence_page_numbers=text_evidence_page_numbers,
        )
        if args.llm:
            if llm is None:
                from core.llm.groq_provider import GroqProvider

                llm = GroqProvider()
            extracted, selected = extract_financial_candidates(
                pages, tables,
                {**document, "rbac": document.get("rbac", {})},
                llm,
                max_pages=args.max_pages,
            )
            rows.extend(merge_candidate_sources(parser_candidates, extracted))
            selection_runs[-1]["extraction"] = [
                {
                    "page_number": page["page_number"],
                    "metrics_returned": page.get("llm_metrics_returned"),
                    "metrics_accepted": page.get("llm_metrics_accepted", 0),
                    "metrics_rejected": page.get("llm_metrics_rejected", 0),
                    "validation_rejections": page.get("validation_rejections", {}),
                    "status": page.get("extraction_status", "provider_error" if page.get("extraction_error") else "ok"),
                }
                for page in selected
            ]
        else:
            rows.extend(parser_candidates)
    if args.page_selection_only:
        print(json.dumps(selection_runs, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    if args.llm:
        print(json.dumps({"page_selection_and_extraction": selection_runs}, ensure_ascii=False), file=sys.stderr)
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
