#!/usr/bin/env python3
"""Measure manually labeled extraction anchors on real enterprise documents."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.document_processing.processors.document_processor import DocumentProcessor  # noqa: E402


def normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def anchor_present(text: str, label: str, values: list[str]) -> bool:
    """Check that a manually labeled row label and ordered values survive parsing."""
    expected = normalized(" ".join([label, *values]))
    return expected in normalized(text)


def normalized_anchor_present(text: str, label: str, values: list[str]) -> bool:
    """Ignore Unicode accents, spaces and numeric grouping punctuation only."""
    def compact(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        return "".join(
            char for char in decomposed
            if not unicodedata.combining(char) and char.isalnum()
        )

    expected_values = "".join(re.sub(r"\D", "", value) for value in values)
    return (compact(label) + expected_values) in compact(text)


def table_page_text(tables: list[dict], page_number: int) -> str:
    parts = []
    for table in tables:
        if table.get("page_number") != page_number:
            continue
        parts.extend(str(value) for value in table.get("columns", []) if value is not None)
        for row in table.get("rows", []):
            if isinstance(row, dict):
                parts.extend(str(value) for value in row.values() if value is not None)
            elif isinstance(row, (list, tuple)):
                parts.extend(str(value) for value in row if value is not None)
    return " ".join(parts)


def rasterized_single_page_pdf(source_pdf: bytes, page_index: int, dpi: int) -> bytes:
    """Make a scan-like raster PDF from a source page; this is synthetic input."""
    source = fitz.open(stream=source_pdf, filetype="pdf")
    try:
        page = source[page_index]
        pixmap = page.get_pixmap(dpi=dpi, alpha=False)
        page_size = page.rect
        image_bytes = pixmap.tobytes("png")
    finally:
        source.close()
    output = fitz.open()
    raster_page = output.new_page(width=page_size.width, height=page_size.height)
    raster_page.insert_image(raster_page.rect, stream=image_bytes)
    result = output.tobytes()
    output.close()
    return result


def native_single_page_pdf(source_pdf: bytes, page_index: int) -> bytes:
    """Copy one source page without rasterizing, preserving its native text/layout."""
    source = fitz.open(stream=source_pdf, filetype="pdf")
    output = fitz.open()
    try:
        output.insert_pdf(source, from_page=page_index, to_page=page_index)
        return output.tobytes()
    finally:
        output.close()
        source.close()


def rasterized_single_page_png(source_pdf: bytes, page_index: int, dpi: int) -> bytes:
    """Render a real source page to the same synthetic image used by upload OCR."""
    source = fitz.open(stream=source_pdf, filetype="pdf")
    try:
        return source[page_index].get_pixmap(dpi=dpi, alpha=False).tobytes("png")
    finally:
        source.close()


def score_parse(case: dict, parsed: dict, page_number: int | None, condition: str) -> dict:
    page_chunks = [
        chunk for chunk in parsed["chunks"]
        if chunk.get("metadata", {}).get("page_number") == page_number
    ]
    if not page_chunks:
        raise ValueError(f"No parsed chunks found for {case['id']} page {page_number} ({condition})")
    page_text = " ".join(chunk["text"] for chunk in page_chunks)
    # Image uploads have no PDF page metadata on their text chunks, but the
    # image parser records extracted table coordinates on its single page (1).
    table_page_number = 1 if page_number is None else page_number
    table_text = table_page_text(parsed["tables"], table_page_number)
    field_results = [{
        **field,
        "text_anchor_exact_match": anchor_present(page_text, field["label"], field["values"]),
        "text_anchor_normalized_match": normalized_anchor_present(page_text, field["label"], field["values"]),
        "table_anchor_exact_match": anchor_present(table_text, field["label"], field["values"]),
        "table_anchor_normalized_match": normalized_anchor_present(table_text, field["label"], field["values"]),
    } for field in case["fields"]]
    page_tables = [
        table for table in parsed["tables"]
        if table.get("page_number") == table_page_number
    ]
    methods = sorted({
        chunk.get("metadata", {}).get("text_extraction_method", "unknown")
        for chunk in page_chunks
    })
    expected_fields = len(field_results)
    text_matches = sum(field["text_anchor_exact_match"] for field in field_results)
    text_normalized_matches = sum(field["text_anchor_normalized_match"] for field in field_results)
    table_matches = sum(field["table_anchor_exact_match"] for field in field_results)
    table_normalized_matches = sum(field["table_anchor_normalized_match"] for field in field_results)
    expected_regions = case.get("expected_table_regions")
    return {
        "condition": condition,
        "text_extraction_methods": methods,
        "chunk_count": len(page_chunks),
        "extracted_page_text": page_text,
        "extracted_tables": page_tables,
        "expected_table_regions": expected_regions,
        "detected_tables": len(page_tables),
        "table_region_recall": (
            round(min(len(page_tables), expected_regions) / expected_regions, 4)
            if expected_regions else None
        ),
        "expected_field_count": expected_fields,
        "text_anchor_exact_match_count": text_matches,
        "text_anchor_recall": round(text_matches / expected_fields, 4) if expected_fields else None,
        "text_anchor_normalized_match_count": text_normalized_matches,
        "text_anchor_normalized_recall": round(text_normalized_matches / expected_fields, 4) if expected_fields else None,
        "table_anchor_exact_match_count": table_matches,
        "table_anchor_recall": round(table_matches / expected_fields, 4) if expected_fields else None,
        "table_anchor_normalized_match_count": table_normalized_matches,
        "table_anchor_normalized_recall": round(table_normalized_matches / expected_fields, 4) if expected_fields else None,
        "fields": field_results,
    }


def evaluate_table_strategies(page: fitz.Page, case: dict) -> list[dict]:
    """Compare native PyMuPDF table strategies against the same labeled fields."""
    strategies = {
        "default": {},
        "text_text": {"vertical_strategy": "text", "horizontal_strategy": "text"},
        "text_lines": {"vertical_strategy": "text", "horizontal_strategy": "lines"},
        "lines_text": {"vertical_strategy": "lines", "horizontal_strategy": "text"},
    }
    results = []
    for name, options in strategies.items():
        started = time.perf_counter()
        tables = page.find_tables(**options).tables
        extracted = [table.extract() for table in tables]
        latency_seconds = round(time.perf_counter() - started, 6)
        text = " ".join(
            str(cell or "")
            for table in extracted
            for row in table
            for cell in row
        )
        fields = [{
            "id": field["id"],
            "exact_match": anchor_present(text, field["label"], field["values"]),
            "normalized_match": normalized_anchor_present(text, field["label"], field["values"]),
        } for field in case["fields"]]
        results.append({
            "strategy": name,
            "options": options,
            "detected_tables": len(tables),
            "table_shapes": [[table.row_count, table.col_count] for table in tables],
            "expected_table_regions": case["expected_table_regions"],
            "exact_anchor_matches": sum(field["exact_match"] for field in fields),
            "normalized_anchor_matches": sum(field["normalized_match"] for field in fields),
            "expected_anchor_count": len(fields),
            "fields": fields,
            "latency_seconds": latency_seconds,
        })
    return results


def evaluate_case(case: dict, file_bytes: bytes) -> dict:
    processor = DocumentProcessor()
    native_pdf = native_single_page_pdf(file_bytes, case["page_index"])
    native = processor.process(
        Path(case["file"]).name,
        native_pdf,
        {"document_id": case["document_id"]},
    )
    scan_pdf = rasterized_single_page_pdf(file_bytes, case["page_index"], case.get("raster_dpi", 180))
    scan_png = rasterized_single_page_png(file_bytes, case["page_index"], case.get("raster_dpi", 180))
    raster = DocumentProcessor().process(
        Path(case["file"]).name,
        scan_pdf,
        {"document_id": case["document_id"]},
    )
    image = DocumentProcessor().process(
        f"{case['document_id']}.png",
        scan_png,
        {"document_id": case["document_id"]},
    )
    table_strategy_sweep = None
    if case.get("expected_table_regions"):
        source = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            table_strategy_sweep = evaluate_table_strategies(
                source[case["page_index"]], case,
            )
        finally:
            source.close()
    return {
        "id": case["id"],
        "document_id": case["document_id"],
        "file": case["file"],
        "file_sha256": hashlib.sha256(file_bytes).hexdigest(),
        "native_single_page_pdf_sha256": hashlib.sha256(native_pdf).hexdigest(),
        "synthetic_raster_pdf_sha256": hashlib.sha256(scan_pdf).hexdigest(),
        "synthetic_raster_png_sha256": hashlib.sha256(scan_png).hexdigest(),
        "official_url": case["official_url"],
        "page_index": case["page_index"],
        "printed_pages": case.get("printed_pages", []),
        "synthetic_raster_dpi": case.get("raster_dpi", 180),
        "table_strategy_sweep": table_strategy_sweep,
        "conditions": [
            score_parse(case, native, 1, "born_digital_pdf"),
            score_parse(case, raster, 1, "synthetic_raster_pdf_tesseract"),
            score_parse(case, image, None, "synthetic_raster_image_upload_tesseract"),
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path,
        default=REPO_ROOT / "data/evaluation/vinamilk_document_extraction_cases.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=REPO_ROOT / "artifacts/evaluation/vinamilk-document-extraction-smoke.json",
    )
    args = parser.parse_args()
    case_bytes = args.cases.read_bytes()
    dataset = json.loads(case_bytes)
    results = []
    for case in dataset["cases"]:
        source = (REPO_ROOT / case["file"]).read_bytes()
        results.append(evaluate_case(case, source))
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": dataset["dataset_id"],
        "dataset_sha256": hashlib.sha256(case_bytes).hexdigest(),
        "reference_quality": dataset["reference_quality"],
        "reference_method": dataset["reference_method"],
        "limitations": dataset["limitations"],
        "software": {"python": platform.python_version(), "pymupdf": fitz.VersionBind},
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = [{
        "id": result["id"],
        "conditions": [{
            "condition": condition["condition"],
            "text_anchor_recall": condition["text_anchor_recall"],
            "text_anchor_normalized_recall": condition["text_anchor_normalized_recall"],
            "table_anchor_recall": condition["table_anchor_recall"],
            "table_anchor_normalized_recall": condition["table_anchor_normalized_recall"],
            "detected_tables": condition["detected_tables"],
            "expected_table_regions": condition["expected_table_regions"],
        } for condition in result["conditions"]],
    } for result in results]
    print(json.dumps({"output": str(args.output), "results": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
