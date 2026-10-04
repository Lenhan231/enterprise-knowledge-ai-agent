#!/usr/bin/env python3
"""Measure manually labeled extraction anchors on real enterprise documents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import subprocess
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.document_processing.processors.document_processor import DocumentProcessor  # noqa: E402
from core.analytics.metric_candidates import candidates as extract_metric_candidates  # noqa: E402
from core.analytics.financial_extraction import (  # noqa: E402
    extract_financial_candidates, select_financial_pages,
)


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


def normalize_financial_cell(value: str) -> str:
    value = str(value or "").strip()
    if value in {"-", "–", "—"}:
        return "-"
    digits = "".join(char for char in value if char.isdigit())
    if not digits:
        return ""
    negative = value.startswith(("-", "−")) or (value.startswith("(") and value.endswith(")"))
    return ("-" if negative else "") + digits


def ordered_table_values_match(row: dict | list, columns: list[str], expected: list[str]) -> bool:
    """Match reviewed values in one table row, allowing account/note cells between them."""
    cells = (
        [row.get(column) for column in columns if column != "label"]
        if isinstance(row, dict)
        else list(row[1:])
    )
    actual = [normalize_financial_cell(value) for value in cells]
    actual = [value for value in actual if value]
    wanted = [normalize_financial_cell(value) for value in expected]
    if not wanted:
        return False
    matched = 0
    for value in actual:
        if value == wanted[matched]:
            matched += 1
            if matched == len(wanted):
                return True
    return False


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
        "table_values_ordered_match": any(
            ordered_table_values_match(row, table.get("columns", []), field["values"])
            for table in parsed["tables"] if table.get("page_number") == table_page_number
            for row in table.get("rows", [])
        ),
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
    table_value_matches = sum(field["table_values_ordered_match"] for field in field_results)
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
        "table_values_ordered_match_count": table_value_matches,
        "table_values_ordered_recall": round(table_value_matches / expected_fields, 4) if expected_fields else None,
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


def _score_candidate_rows(case: dict, extracted: list[dict]) -> dict:
    """Compare candidate metric/value pairs with the human-reviewed fields."""
    fields = []
    matched_ids = set()
    for field in case["fields"]:
        expected_digits = {re.sub(r"\D", "", value) for value in field["values"]}
        matching = [
            candidate for candidate in extracted
            if candidate["metric_name"] in field.get("metric_names", [])
            and expected_digits.intersection(
                re.sub(r"\D", "", value) for value in candidate["candidate_values"]
            )
        ]
        matched_ids.update(id(candidate) for candidate in matching)
        fields.append({
            "field_id": field["id"],
            "candidate_found": bool(matching),
            "candidate_count": sum(
                candidate["metric_name"] in field.get("metric_names", []) for candidate in extracted
            ),
            "matched_candidate_count": len(matching),
            "candidates": matching,
        })
    labeled = [
        candidate for candidate in extracted
        if any(candidate["metric_name"] in field.get("metric_names", []) for field in case["fields"])
    ]
    correct = sum(id(candidate) in matched_ids for candidate in labeled)
    return {
        "candidate_count": len(extracted),
        "labeled_metric_candidate_count": len(labeled),
        "correct_labeled_candidate_count": correct,
        "anchor_precision": round(correct / len(labeled), 4) if labeled else None,
        "expected_field_count": len(fields),
        "matched_field_count": sum(field["candidate_found"] for field in fields),
        "anchor_recall": round(sum(field["candidate_found"] for field in fields) / len(fields), 4) if fields else None,
        "fields": fields,
    }


def score_metric_candidates(
    case: dict, parsed: dict, source_url: str, visual_pages: list[dict] | None = None,
) -> dict:
    """Score rule-based review candidates against the same human-reviewed fields."""
    chunks = [{"metadata": chunk["metadata"], "text": chunk["text"]}
              for chunk in parsed["chunks"]]
    selected_pages = select_financial_pages(chunks, parsed.get("tables", []))
    text_evidence_pages = {
        page["page_number"] for page in selected_pages
        if page["selection_signals"]["summary_area_with_metric"]
    }
    document = {
        "company": "Công ty Cổ phần Sữa Việt Nam (Vinamilk)",
        "fiscal_year": int(case["document_id"].split("-")[2]),
        "document_id": case["document_id"],
        "source_url": source_url,
        "rbac": {"allowed_roles": ["finance_analyst", "executive", "admin"]},
    }
    extracted = extract_metric_candidates(
        chunks, document, parsed.get("tables", []), visual_pages=visual_pages,
        text_evidence_page_numbers=text_evidence_pages,
    )
    return _score_candidate_rows(case, extracted)


def score_llm_candidates(case: dict, parsed: dict, llm) -> dict:
    """Run and score the upload's strict page-grounded LLM candidate stage."""
    document = {
        "company": "Công ty Cổ phần Sữa Việt Nam (Vinamilk)",
        "fiscal_year": int(case["document_id"].split("-")[2]),
        "document_id": case["document_id"],
        "source_url": case["source_url"],
        "rbac": {"allowed_roles": ["finance_analyst", "executive", "admin"]},
    }
    extracted, selected_pages = extract_financial_candidates(
        [{"metadata": chunk["metadata"], "text": chunk["text"]}
         for chunk in parsed["chunks"]],
        parsed.get("tables", []), document, llm, max_pages=1,
    )
    return {
        **_score_candidate_rows(case, extracted),
        "page_extraction": [{
            "page_number": page["page_number"],
            "signals": page["selection_signals"],
            "metrics_returned": page.get("llm_metrics_returned"),
            "metrics_accepted": page.get("llm_metrics_accepted", 0),
            "validation_rejections": page.get("validation_rejections", {}),
            "status": page.get("extraction_status", "provider_error" if page.get("extraction_error") else "ok"),
        } for page in selected_pages],
    }


def evaluate_case(
    case: dict,
    file_bytes: bytes,
    tesseract_psm: int = 11,
    render_scale: float = 1.5,
    tesseract_table_psm: int | None = None,
    table_render_scale: float = 2.5,
    llm=None,
) -> dict:
    processor_config = {
        "tesseract_psm": tesseract_psm,
        "ocr_render_scale": render_scale,
        "ocr_table_render_scale": table_render_scale,
    }
    if tesseract_table_psm is not None:
        processor_config["tesseract_table_psm"] = tesseract_table_psm
    processor = DocumentProcessor(processor_config)
    native_pdf = native_single_page_pdf(file_bytes, case["page_index"])
    native = processor.process(
        Path(case["file"]).name,
        native_pdf,
        {"document_id": case["document_id"]},
    )
    scan_pdf = rasterized_single_page_pdf(file_bytes, case["page_index"], case.get("raster_dpi", 180))
    scan_png = rasterized_single_page_png(file_bytes, case["page_index"], case.get("raster_dpi", 180))
    raster = DocumentProcessor(processor_config).process(
        Path(case["file"]).name,
        scan_pdf,
        {"document_id": case["document_id"]},
    )
    image = DocumentProcessor(processor_config).process(
        f"{case['document_id']}.png",
        scan_png,
        {"document_id": case["document_id"]},
    )
    visual_pdf = fitz.open(stream=native_pdf, filetype="pdf")
    try:
        visual_spans = [
            {"text": span["text"], "bbox": span["bbox"], "font_size": span["size"]}
            for block in visual_pdf[0].get_text("dict")["blocks"]
            for line in block.get("lines", [])
            for span in line["spans"]
            if span["text"].strip()
        ]
    finally:
        visual_pdf.close()
    native_kpi_score = score_metric_candidates(
        case, native, case["source_url"], visual_pages=[{"page_number": 1, "spans": visual_spans}],
    )
    source_condition = (
        "real_scanned_source_pdf_upload" if case.get("physical_scan") else "born_digital_pdf"
    )
    conditions = [
        {
            **score_parse(case, native, 1, source_condition),
            "rule_candidate_extraction": native_kpi_score,
        },
        {
            **score_parse(case, raster, 1, "synthetic_raster_pdf_tesseract"),
            "rule_candidate_extraction": score_metric_candidates(case, raster, case["source_url"]),
        },
        {
            **score_parse(case, image, None, "synthetic_raster_image_upload_tesseract"),
            "rule_candidate_extraction": score_metric_candidates(case, image, case["source_url"]),
        },
    ]
    if llm is not None:
        llm_parse = native if case.get("physical_scan") else raster
        llm_condition = 0 if case.get("physical_scan") else 1
        conditions[llm_condition]["llm_candidate_extraction"] = score_llm_candidates(
            case, llm_parse, llm,
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
        "source_url": case["source_url"],
        "page_index": case["page_index"],
        "printed_pages": case.get("printed_pages", []),
        "synthetic_raster_dpi": case.get("raster_dpi", 180),
        "ocr_config": {
            "tesseract_psm": tesseract_psm,
            "tesseract_table_psm": tesseract_table_psm if tesseract_table_psm is not None else {"pdf": 3, "image": 6},
            "render_scale": render_scale,
            "table_render_scale": table_render_scale,
        },
        "table_strategy_sweep": table_strategy_sweep,
        "rule_candidate_extraction": native_kpi_score,
        "conditions": conditions,
    }


def compact_result(result: dict) -> dict:
    """Keep scores and provenance while omitting bulky parser dumps."""
    return {
        **result,
        "conditions": [
            {key: value for key, value in condition.items()
             if key not in {"extracted_page_text", "extracted_tables"}}
            for condition in result["conditions"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path,
        default=REPO_ROOT / "data/evaluation/ocr/vinamilk_document_extraction_cases.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=REPO_ROOT / "artifacts/evaluation/ocr/pipeline/vinamilk-document-extraction-smoke.json",
    )
    parser.add_argument(
        "--compact", action="store_true",
        help="omit full extracted text/table dumps while preserving scores and provenance",
    )
    parser.add_argument("--case-id", action="append", default=[], help="Evaluate only this case ID; repeat to select multiple.")
    parser.add_argument("--llm", action="store_true", help="Run one strict LLM KPI extraction request on each selected synthetic PDF upload page.")
    parser.add_argument("--tesseract-psm", type=int, choices=(3, 6, 11, 12), default=11)
    parser.add_argument(
        "--tesseract-table-psm", type=int, choices=(3, 6, 11), default=None,
        help="Override the format defaults: PDF uses 3 and image uploads use 6.",
    )
    parser.add_argument("--render-scale", type=float, default=1.5)
    parser.add_argument("--table-render-scale", type=float, choices=(1.5, 2.5), default=2.5)
    args = parser.parse_args()
    case_bytes = args.cases.read_bytes()
    dataset = json.loads(case_bytes)
    cases_by_id = {case["id"]: case for case in dataset["cases"]}
    missing_case_ids = sorted(set(args.case_id) - cases_by_id.keys())
    if missing_case_ids:
        parser.error(f"Unknown case ID(s): {', '.join(missing_case_ids)}")
    selected_cases = (
        [cases_by_id[case_id] for case_id in dict.fromkeys(args.case_id)]
        if args.case_id else dataset["cases"]
    )
    llm = None
    if args.llm:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
        from core.llm.groq_provider import GroqProvider

        llm = GroqProvider()
    results = []
    try:
        for case in selected_cases:
            source = (REPO_ROOT / case["file"]).read_bytes()
            results.append(evaluate_case(
                case, source, tesseract_psm=args.tesseract_psm,
                render_scale=args.render_scale,
                tesseract_table_psm=args.tesseract_table_psm,
                table_render_scale=args.table_render_scale,
                llm=llm,
            ))
    finally:
        if llm is not None:
            llm.close()
    tesseract_version = subprocess.run(
        ["tesseract", "--version"], capture_output=True, text=True,
        check=False, timeout=10,
    ).stdout.splitlines()
    tessdata_listing = subprocess.run(
        ["tesseract", "--list-langs"], capture_output=True, text=True,
        check=False, timeout=10,
    )
    tessdata_match = re.search(r'available languages in "([^"]+)"', tessdata_listing.stderr + tessdata_listing.stdout)
    tessdata_dir = Path(os.getenv("TESSDATA_PREFIX") or (tessdata_match.group(1) if tessdata_match else ""))
    traineddata_hashes = {
        language: hashlib.sha256((tessdata_dir / f"{language}.traineddata").read_bytes()).hexdigest()
        for language in ("vie", "eng")
        if (tessdata_dir / f"{language}.traineddata").is_file()
    }
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": dataset["dataset_id"],
        "dataset_sha256": hashlib.sha256(case_bytes).hexdigest(),
        "reference_quality": dataset["reference_quality"],
        "reference_method": dataset["reference_method"],
        "limitations": dataset["limitations"],
        "software": {
            "python": platform.python_version(),
            "pymupdf": fitz.VersionBind,
            "tesseract": tesseract_version[0] if tesseract_version else "unavailable",
            "tesseract_traineddata_sha256": traineddata_hashes,
        },
        "ocr_config": {
            "language": "vie+eng", "tesseract_psm": args.tesseract_psm,
            "tesseract_table_psm": (
                args.tesseract_table_psm if args.tesseract_table_psm is not None
                else {"pdf": 3, "image": 6}
            ),
            "render_scale": args.render_scale,
            "table_render_scale": args.table_render_scale,
        },
        "llm_model": getattr(llm, "model_name", None) if llm is not None else None,
        "results": [compact_result(result) for result in results] if args.compact else results,
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
            "table_values_ordered_recall": condition["table_values_ordered_recall"],
            **({"llm_candidate_extraction": {
                key: condition["llm_candidate_extraction"][key]
                for key in (
                    "candidate_count", "labeled_metric_candidate_count",
                    "correct_labeled_candidate_count", "anchor_precision",
                    "expected_field_count", "matched_field_count", "anchor_recall",
                    "page_extraction",
                )
            }} if "llm_candidate_extraction" in condition else {}),
        } for condition in result["conditions"]],
        "rule_candidate_extraction": {
            key: result["rule_candidate_extraction"][key]
            for key in (
                "candidate_count", "labeled_metric_candidate_count",
                "correct_labeled_candidate_count", "anchor_precision",
                "expected_field_count", "matched_field_count", "anchor_recall",
            )
        },
    } for result in results]
    print(json.dumps({"output": str(args.output), "results": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
