#!/usr/bin/env python3
"""Score real image-only PDF scan regions through the upload document processor."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from core.document_processing.document_processor import DocumentProcessor
from core.document_processing.chunking.processor import ChunkingProcessor  # noqa: E402
from scripts.processing.evaluate_ocr import edit_distance, error_rate, normalize, peak_memory_mb  # noqa: E402


def crop_pdf_page(source_pdf: bytes, page_number: int, clip_rect: list[float]) -> bytes:
    """Copy one source page and crop it without re-rendering its scan image."""
    source = fitz.open(stream=source_pdf, filetype="pdf")
    cropped = fitz.open()
    try:
        if page_number < 1 or page_number > len(source):
            raise ValueError(f"Page {page_number} is outside the source PDF")
        cropped.insert_pdf(source, from_page=page_number - 1, to_page=page_number - 1)
        page = cropped[0]
        crop_box = fitz.Rect(clip_rect) * page.derotation_matrix
        if not page.mediabox.contains(crop_box):
            raise ValueError(f"Clip {clip_rect} maps outside the source page MediaBox")
        page.set_cropbox(crop_box)
        return cropped.tobytes(no_new_id=True)
    finally:
        cropped.close()
        source.close()


def rasterize_for_ocr(pdf_bytes: bytes, dpi: int = 216) -> bytes:
    """Remove hidden PDF text layers so every labeled scan is tested as pixels."""
    source = fitz.open(stream=pdf_bytes, filetype="pdf")
    raster = fitz.open()
    try:
        page = source[0]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        target = raster.new_page(width=page.rect.width, height=page.rect.height)
        target.insert_image(target.rect, stream=pix.tobytes("png"))
        return raster.tobytes(no_new_id=True)
    finally:
        raster.close()
        source.close()


def _normalize_label(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value).casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _normalize_cell(value: str) -> str:
    value = str(value or "").strip()
    if value in {"-", "–", "—"}:
        return "-"
    digits = "".join(char for char in value if char.isdigit())
    if not digits:
        return ""
    negative = value.startswith("-") or value.startswith("−") or (value.startswith("(") and value.endswith(")"))
    return ("-" if negative else "") + digits


def _bbox_iou(left: list[float], right: list[float]) -> float:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def score_table_anchors(expected_columns: list[str], expected_rows: list[dict], tables: list[dict]) -> dict | None:
    """Compare reviewed row/cell anchors, ignoring numeric punctuation but preserving sign."""
    if not expected_rows:
        return None
    if not tables:
        tables = [{}]

    candidates = []
    for table in tables:
        columns = table.get("columns", [])
        value_columns = columns[1:] if columns and columns[0] == "label" else columns
        header_matches = sum(
            re.sub(r"\D", "", actual) == re.sub(r"\D", "", expected)
            for actual, expected in zip(value_columns, expected_columns)
        )
        remaining = list(enumerate(table.get("rows", [])))
        row_matches = []
        exact_cells = 0
        coordinate_matches = 0
        coordinate_total = 0
        for expected in expected_rows:
            best = max(
                ((SequenceMatcher(None, _normalize_label(expected["label"]), _normalize_label(row.get("label", ""))).ratio(), index, row_index, row)
                 for index, (row_index, row) in enumerate(remaining)),
                default=(0.0, -1, -1, {}),
            )
            similarity, index, row_index, row = best
            matched = index >= 0 and similarity >= 0.6
            if matched:
                remaining.pop(index)
            actual_values = [row.get(column, "") for column in value_columns[:len(expected["values"])]] if matched else []
            cell_matches = [
                _normalize_cell(actual) == _normalize_cell(wanted)
                for actual, wanted in zip(actual_values, expected["values"])
            ]
            exact_cells += sum(cell_matches)
            expected_boxes = expected.get("cell_bboxes_pdf_points", {})
            row_boxes = table.get("metadata", {}).get("row_cell_bboxes", [])
            actual_boxes = row_boxes[row_index] if matched and row_index < len(row_boxes) else {}
            cell_locations = {}
            for box_index, (column, expected_box) in enumerate(expected_boxes.items()):
                expected_year = re.search(r"(?:19|20)\d{2}", str(column))
                matching_index = next(
                    (
                        index for index, expected_column in enumerate(expected_columns)
                        if expected_column == column
                        or (
                            expected_year
                            and expected_year.group() in str(expected_column)
                        )
                    ),
                    box_index,
                )
                actual_column = value_columns[matching_index] if matching_index < len(value_columns) else None
                actual_box = actual_boxes.get(actual_column) if actual_column else None
                overlap = _bbox_iou(expected_box, actual_box) if actual_box else 0.0
                cell_locations[column] = {
                    "matched": overlap >= 0.3,
                    "iou": round(overlap, 4),
                    "expected_bbox_pdf_points": expected_box,
                    "extracted_column": actual_column,
                    "extracted_bbox_pdf_points": actual_box,
                }
            coordinate_matches += sum(item["matched"] for item in cell_locations.values())
            coordinate_total += len(cell_locations)
            row_matches.append({
                "expected_label": expected["label"],
                "extracted_label": row.get("label") if matched else None,
                "label_similarity": round(similarity, 4),
                "matched": matched,
                "expected_values": expected["values"],
                "extracted_values": actual_values,
                "exact_value_matches": cell_matches,
                "cell_location_matches": cell_locations,
            })
        candidates.append((len([match for match in row_matches if match["matched"]]), exact_cells, coordinate_matches, header_matches, {
            "expected_headers": expected_columns,
            "extracted_headers": value_columns,
            "comparison": {
                "labels": "accent-folded character similarity; matched at >= 0.6",
                "headers": "digits-only period comparison",
                "numeric_cells": "sign and digit sequence; punctuation ignored",
            },
            "exact_header_matches": header_matches,
            "expected_anchor_rows": len(expected_rows),
            "matched_anchor_rows": sum(match["matched"] for match in row_matches),
            "anchor_row_recall": round(sum(match["matched"] for match in row_matches) / len(expected_rows), 4),
            "exact_numeric_cells": exact_cells,
            "total_numeric_cells": sum(len(row["values"]) for row in expected_rows),
            "exact_numeric_cell_accuracy": round(exact_cells / sum(len(row["values"]) for row in expected_rows), 4),
            "matched_cell_locations": coordinate_matches,
            "annotated_cell_locations": coordinate_total,
            "cell_location_recall": round(coordinate_matches / coordinate_total, 4) if coordinate_total else None,
            "cell_location_comparison": "PDF-point bounding-box IoU >= 0.3",
            "row_matches": row_matches,
        }))
    return max(candidates, default=(0, 0, 0, 0, None), key=lambda candidate: candidate[:4])[4]


def evaluate_region(
    spec: dict, source_pdf: bytes, tesseract_psm: int = 11,
    render_scale: float = 1.5, tesseract_table_psm: int = 3,
    table_render_scale: float = 2.5,
) -> dict:
    cropped_pdf = rasterize_for_ocr(crop_pdf_page(source_pdf, spec["page"], spec["clip_rect"]))
    started = time.perf_counter()
    processor = DocumentProcessor({
        "tesseract_psm": tesseract_psm,
        "tesseract_table_psm": tesseract_table_psm,
        "ocr_render_scale": render_scale,
        "ocr_table_render_scale": table_render_scale,
    })
    parsed = processor.process(
        Path(spec["file"]).name,
        cropped_pdf,
        {"document_id": spec["document_id"]},
    )
    parsed = ChunkingProcessor(processor.config).process(parsed)
    elapsed = time.perf_counter() - started
    chunks = sorted(parsed["chunks"], key=lambda item: item["metadata"]["chunk_index"])
    extracted_text = "\n".join(chunk["text"] for chunk in chunks)
    reference = normalize(spec.get("reference_text", ""))
    hypothesis = normalize(extracted_text)
    reference_words = reference.split()
    hypothesis_words = hypothesis.split()
    methods = sorted({chunk["metadata"].get("text_extraction_method", "unknown") for chunk in chunks})
    return {
        "id": spec["id"],
        "document_id": spec["document_id"],
        "source_page_number": spec["page"],
        "language": spec["language"],
        "layout_type": spec.get("layout_type"),
        "physical_scan": bool(spec.get("physical_scan")),
        "source_pdf_sha256": hashlib.sha256(source_pdf).hexdigest(),
        "cropped_pdf_sha256": hashlib.sha256(cropped_pdf).hexdigest(),
        "text_extraction_methods": methods,
        "tesseract_page_segmentation_mode": tesseract_psm,
        "tesseract_table_segmentation_mode": tesseract_table_psm,
        "ocr_render_scale": render_scale,
        "ocr_table_render_scale": table_render_scale,
        "ocr_used": any("tesseract" in method for method in methods),
        "chunk_count": len(chunks),
        "table_count": len(parsed["tables"]),
        "extracted_tables": parsed["tables"],
        "table_anchor_score": score_table_anchors(
            spec.get("table_columns", []), spec.get("table_rows", []), parsed["tables"],
        ),
        "text_reference_scored": bool(reference),
        "reference_characters": len(reference) if reference else None,
        "reference_words": len(reference_words) if reference else None,
        "hypothesis_characters": len(hypothesis),
        "character_edit_distance": edit_distance(reference, hypothesis),
        "word_edit_distance": edit_distance(reference_words, hypothesis_words),
        "cer": round(error_rate(reference, hypothesis), 6) if reference else None,
        "wer": round(error_rate(reference_words, hypothesis_words), 6) if reference else None,
        "latency_seconds": round(elapsed, 3),
        "pages_per_minute": round(60 / elapsed, 3) if elapsed else None,
        "extracted_text": extracted_text,
    }


def select_cases(pages: list[dict], case_ids: list[str], all_pages: bool = False) -> list[dict]:
    if all_pages and case_ids:
        raise ValueError("--all-pages cannot be combined with --case-id")
    if all_pages:
        return pages
    if not case_ids:
        return [page for page in pages if page.get("physical_scan")]
    by_id = {page["id"]: page for page in pages}
    missing = sorted(set(case_ids) - by_id.keys())
    if missing:
        raise ValueError(f"Unknown case ID(s): {', '.join(missing)}")
    return [by_id[case_id] for case_id in dict.fromkeys(case_ids)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path,
        default=ROOT / "data/evaluation/vinamilk_ocr_ground_truth_v4.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "artifacts/evaluation/vinamilk-scan-document-processor-v1.json",
    )
    parser.add_argument(
        "--case-id", action="append", default=[],
        help="Evaluate this dataset case instead of the default physical scans; repeat to select multiple cases.",
    )
    parser.add_argument(
        "--all-pages", action="store_true",
        help="Evaluate every labeled region, including born-digital pages rasterized as OCR input.",
    )
    parser.add_argument("--tesseract-psm", type=int, choices=(3, 6, 11, 12), default=11)
    parser.add_argument("--tesseract-table-psm", type=int, choices=(3, 4, 6, 11, 12), default=3)
    parser.add_argument("--render-scale", type=float, choices=(1.5, 2.5), default=1.5)
    parser.add_argument("--table-render-scale", type=float, choices=(1.5, 2.5), default=2.5)
    args = parser.parse_args()
    dataset_bytes = args.dataset.read_bytes()
    dataset = json.loads(dataset_bytes)
    try:
        selected_specs = select_cases(dataset["pages"], args.case_id, args.all_pages)
    except ValueError as error:
        parser.error(str(error))
    if not selected_specs:
        parser.error("Dataset has no pages labeled physical_scan")

    results = []
    for spec in selected_specs:
        source_pdf = (ROOT / spec["file"]).read_bytes()
        result = evaluate_region(
            spec, source_pdf, args.tesseract_psm, args.render_scale,
            args.tesseract_table_psm, args.table_render_scale,
        )
        results.append(result)
        print(
            f"{result['id']}: OCR={result['ocr_used']} CER={result['cer']} "
            f"WER={result['wer']} in {result['latency_seconds']:.2f}s",
            file=sys.stderr,
            flush=True,
        )

    valid = [result for result in results if result["ocr_used"]]
    text_scored = [result for result in valid if result["text_reference_scored"]]
    coordinate_scores = [
        result["table_anchor_score"] for result in results
        if result.get("table_anchor_score")
    ]
    annotated_cell_locations = sum(score["annotated_cell_locations"] for score in coordinate_scores)
    matched_cell_locations = sum(score["matched_cell_locations"] for score in coordinate_scores)
    try:
        tesseract_version = subprocess.run(
            ["tesseract", "--version"], capture_output=True, check=True, text=True, timeout=10,
        ).stdout.splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        tesseract_version = None
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": dataset["dataset_id"],
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "reference_quality": dataset["reference_quality"],
        "reference_method": dataset["reference_method"],
        "protocol": "Copy each selected region from its source PDF page, rasterize it at 216 DPI to remove any embedded OCR text layer, then run the existing DocumentProcessor PDF upload path (PyMuPDF/Tesseract fallback) with separate page-text and numeric-table render scales. Score manually transcribed text and reviewed financial row/value anchors.",
        "limitations": (
            "Production-parser OCR path only. This supplemental set contains pages from one third-party Vietnamese scan packet and manually reviewed financial anchors; it is diagnostic, not representative model-selection evidence or safe automatic financial publication. "
            + (
                f"The selected regions include {annotated_cell_locations} explicit cell-box labels, with {matched_cell_locations} meeting PDF-point bounding-box IoU >= 0.3; labels are limited to reviewed anchors and are not a multi-annotator gold standard. "
                if annotated_cell_locations else
                "This run has no explicitly annotated cell coordinates. "
            )
            + "There is no paired OCR-engine comparison. Throughput includes parser/OCR invocation but excludes application embedding and database persistence."
        ),
        "render_dpi": 72 * args.render_scale,
        "ocr_render_scale": args.render_scale,
        "table_ocr_render_dpi": 72 * args.table_render_scale,
        "ocr_table_render_scale": args.table_render_scale,
        "tesseract_page_segmentation_mode": args.tesseract_psm,
        "tesseract_table_segmentation_mode": args.tesseract_table_psm,
        "tesseract_language": "vie+eng",
        "software": {
            "python": platform.python_version(),
            "pymupdf": fitz.VersionBind,
            "tesseract": tesseract_version,
        },
        "process_memory": peak_memory_mb(),
        "aggregate": {
            "ocr_pages": len(valid),
            "text_scored_pages": len(text_scored),
            "annotated_cell_locations": annotated_cell_locations,
            "matched_cell_locations": matched_cell_locations,
            "cell_location_recall": round(matched_cell_locations / annotated_cell_locations, 4) if annotated_cell_locations else None,
            "micro_cer": round(sum(x["character_edit_distance"] for x in text_scored) / sum(x["reference_characters"] for x in text_scored), 6) if text_scored else None,
            "micro_wer": round(sum(x["word_edit_distance"] for x in text_scored) / sum(x["reference_words"] for x in text_scored), 6) if text_scored else None,
            "mean_latency_seconds": round(sum(x["latency_seconds"] for x in valid) / len(valid), 3) if valid else None,
            "mean_pages_per_minute": round(sum(x["pages_per_minute"] for x in valid) / len(valid), 3) if valid else None,
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "aggregate": payload["aggregate"]}, ensure_ascii=False, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
