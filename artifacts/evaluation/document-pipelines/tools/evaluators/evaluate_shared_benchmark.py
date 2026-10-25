"""Evaluate normalized predictions against references produced by data/review.html."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TRACK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TRACK_ROOT / "tools"))

from metrics.layout_metrics import CLASSES, score_layout  # noqa: E402
from metrics.ocr_metrics import score_ocr  # noqa: E402
from metrics.reading_order_metrics import score_reading_order  # noqa: E402
from metrics.table_metrics import score_tables  # noqa: E402

IOU_THRESHOLD = 0.5


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def key(row: dict) -> tuple[str, int]:
    return row["document_id"], int(row["source_page_number_1based"])


def validate(predictions: list[dict]) -> dict[tuple[str, int], dict]:
    by_page = {}
    run_ids = {(row.get("engine"), row.get("run_id")) for row in predictions}
    if len(run_ids) != 1:
        raise ValueError("Predictions must contain one engine and run_id")
    for row in predictions:
        page_key = key(row)
        if page_key in by_page:
            raise ValueError(f"Duplicate prediction for {page_key}")
        for element in row.get("elements", []):
            if element.get("label") not in {*CLASSES, "other"}:
                raise ValueError(f"Invalid element label on {page_key}: {element.get('label')}")
            validate_box(element.get("bbox_norm"), page_key)
        for table in row.get("tables", []):
            validate_box(table.get("bbox_norm"), page_key)
            if any(len(line) != len(table.get("columns", [])) for line in table.get("rows", [])):
                raise ValueError(f"Inconsistent predicted table row width on {page_key}")
        by_page[page_key] = row
    return by_page


def validate_box(box: object, page_key: tuple[str, int]) -> None:
    if not isinstance(box, list) or len(box) != 4 or any(not isinstance(x, (int, float)) or not 0 <= x <= 1 for x in box):
        raise ValueError(f"Invalid normalized box on {page_key}: {box}")
    if box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError(f"Degenerate normalized box on {page_key}: {box}")


def text_order_rotations(metadata: dict) -> dict[tuple[str, int], int]:
    """Use high-confidence page OSD, falling back to OCR-region OSD."""
    rotations = {}
    for detection in metadata.get("page_orientation_detections", []):
        if detection.get("osd_confidence", 0) < 5.0:
            continue
        page_id = detection.get("reference_id")
        if not page_id:
            continue
        document_id, page_number = page_id.rsplit("-p", 1)
        rotations[(document_id, int(page_number))] = int(detection["rotation_clockwise"])

    grouped: dict[str, list[dict]] = {}
    for detection in metadata.get("ocr_orientation_detections", []):
        page_id = detection.get("reference_id")
        if page_id:
            grouped.setdefault(page_id, []).append(detection)

    for page_id, detections in grouped.items():
        confident = [
            item for item in detections
            if item.get("osd_confidence") is not None
            and item["osd_confidence"] >= 5.0
        ]
        if not confident:
            continue
        best = max(confident, key=lambda item: item["osd_confidence"])
        document_id, page_number = page_id.rsplit("-p", 1)
        rotations.setdefault(
            (document_id, int(page_number)), int(best["correction_clockwise"])
        )
    return rotations


def score_cohort(
    ocr_refs: list[dict], layout_refs: list[dict], table_refs: list[dict],
    predictions: dict, reading_order_rotations: dict[tuple[str, int], int] | None = None,
) -> dict:
    keys = set(map(key, ocr_refs)) | set(map(key, layout_refs)) | {key(x) for x in table_refs}
    missing = keys - predictions.keys()
    if missing:
        raise ValueError(f"Missing predictions for {sorted(missing)}")
    return {"pages": len(keys), "ocr": score_ocr(ocr_refs, predictions, reading_order_rotations, IOU_THRESHOLD),
            "reading_order": score_reading_order(layout_refs, predictions, IOU_THRESHOLD),
            "layout": score_layout(layout_refs, predictions, IOU_THRESHOLD),
            "table": score_tables(table_refs, predictions, key, IOU_THRESHOLD)}


def evaluate(args: argparse.Namespace) -> dict:
    refs = {track: read_jsonl(TRACK_ROOT / f"data/{track}/reference.jsonl") for track in ("ocr", "layout", "table", "end-to-end")}
    selected_page_ids = args.page_id or []
    if selected_page_ids:
        if len(selected_page_ids) != len(set(selected_page_ids)):
            raise SystemExit("Duplicate --page-id values are not allowed")
        ocr_by_id = {row["reference_id"]: row for row in refs["ocr"]}
        missing_ids = sorted(set(selected_page_ids) - ocr_by_id.keys())
        if missing_ids:
            raise SystemExit(f"No OCR reference found for page(s): {', '.join(missing_ids)}")
        page_keys = {key(ocr_by_id[page_id]) for page_id in selected_page_ids}
        refs = {track: [row for row in rows if key(row) in page_keys] for track, rows in refs.items()}
    predictions = validate(read_jsonl(args.predictions))
    if selected_page_ids:
        selected_keys = {key(row) for row in refs["ocr"]}
        predictions = {page_key: row for page_key, row in predictions.items() if page_key in selected_keys}
    meta_path = args.predictions.parent / "run-metadata.json"
    metadata = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    successful_pages = metadata.get("successful_pages")
    source_run_inference_seconds = metadata.get("inference_wall_seconds", metadata.get("wall_seconds"))
    inference_seconds = source_run_inference_seconds
    if selected_page_ids and metadata.get("pages"):
        selected_ids = set(selected_page_ids)
        successful_pages = sum(
            page.get("status") != "failed"
            for page in metadata["pages"]
            if page.get("reference_id") in selected_ids
        )
        page_seconds = metadata.get("inference_page_seconds", {})
        selected_times = [page_seconds.get(page_id) for page_id in selected_page_ids]
        inference_seconds = round(sum(selected_times), 3) if all(isinstance(value, (int, float)) for value in selected_times) else None
    reading_order_rotations = text_order_rotations(metadata)
    layer_scores = score_cohort(
        refs["ocr"], refs["layout"], refs["table"], predictions,
        reading_order_rotations,
    )
    e2e_ocr = [{"document_id": r["document_id"], "source_page_number_1based": r["source_page_number_1based"], "ocr_reference_text": r["ocr_reference_text"]} for r in refs["end-to-end"]]
    e2e_layout = [{"document_id": r["document_id"], "source_page_number_1based": r["source_page_number_1based"], "regions": r["layout_regions"], "reading_order": r.get("reading_order", [])} for r in refs["end-to-end"]]
    e2e_tables = []
    for row in refs["end-to-end"]:
        for table in row.get("table_references", []):
            e2e_tables.append({"document_id": row["document_id"], "source_page_number_1based": row["source_page_number_1based"], **table})
    e2e_keys = {key(r) for r in refs["end-to-end"]}
    e2e_predictions = {k: v for k, v in predictions.items() if k in e2e_keys}
    e2e_scores = score_cohort(
        e2e_ocr, e2e_layout, e2e_tables, e2e_predictions,
        reading_order_rotations,
    )
    return {"dataset": "shared-html-owner-reviewed", "engine": next(iter(predictions.values())).get("engine"),
            "run_id": next(iter(predictions.values())).get("run_id"), "layer_scores": layer_scores,
            "end_to_end_scores": e2e_scores,
            "coverage": {"owner_reviewed_pages": len(refs["ocr"]), "pages_with_reviewed_table_grids": layer_scores["table"]["pages_with_reviewed_tables"],
                         "end_to_end_pages_with_ocr_layout_and_tables": len(refs["end-to-end"]),
                         "prediction_pages": len(predictions), "inference_successful_pages": successful_pages},
            "selected_reference_ids": selected_page_ids or None,
            "runtime": {"device": metadata.get("device"),
                        "inference_wall_seconds": inference_seconds,
                        "source_run_inference_wall_seconds": source_run_inference_seconds if selected_page_ids else None,
                        "peak_process_rss_mib": metadata.get("inference_peak_process_rss_mib", metadata.get("peak_process_rss_mib"))},
            "caveats": ["Owner-reviewed working references from the shared HTML review flow.",
                         "OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.",
                         "Full-page CER/WER compare the complete assembled page transcript in reading order and therefore include recognition, detection, table extraction, and ordering errors.",
                         "Reading-order pairwise accuracy is evaluated separately over regions matched by box IoU 0.50 regardless of label; matched-region recall reports how much of the reference order was scorable.",
                         "End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True, help="predictions.jsonl from run_shared_benchmark.py")
    parser.add_argument("--output-dir", type=Path, help="Defaults to the predictions directory")
    parser.add_argument("--page-id", action="append", help="Score a selected reference page; repeat to evaluate a cohort")
    args = parser.parse_args()
    result = evaluate(args)
    output_dir = args.output_dir or args.predictions.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(render_report(result), encoding="utf-8")
    print(f"Saved {output_dir / 'report.md'} and {output_dir / 'evaluation.json'}")


def render_report(result: dict) -> str:
    def pct(value): return "n/a" if value is None else f"{value:.2%}"
    runtime = result["runtime"]
    if result.get("selected_reference_ids"):
        runtime_line = (
            f"**Runtime:** {runtime['inference_wall_seconds']}s summed selected-page inference on {runtime['device']} "
            f"(source full-run total: {runtime['source_run_inference_wall_seconds']}s; excludes initialization)"
        )
    else:
        runtime_line = f"**Runtime:** {runtime['inference_wall_seconds']}s on {runtime['device']}"
    lines = [f"# {result['engine']} benchmark: {result['dataset']}", "",
             f"**Run:** `{result['run_id']}` · **Predictions:** {result['coverage']['prediction_pages']} pages · **Inference success:** {result['coverage']['inference_successful_pages']}",
             runtime_line +
             (f" · peak process RSS {runtime['peak_process_rss_mib']} MiB" if runtime['peak_process_rss_mib'] is not None else " · peak inference RSS unavailable"), ""]
    if result.get("selected_reference_ids"):
        lines.append("**Scored pilot pages:** " + ", ".join(f"`{page_id}`" for page_id in result["selected_reference_ids"]))
        lines.append("")
    lines.extend([
             "## Independent layer scores", "",
             "| Layer | Cohort | Metrics |", "|---|---:|---|",
             f"| OCR | {result['layer_scores']['ocr']['pages']} pages | full-page CER {pct(result['layer_scores']['ocr']['micro_cer'])}; full-page WER (PyVi) {pct(result['layer_scores']['ocr']['micro_wer_pyvi'])} |",
             f"| Reading order | {result['layer_scores']['reading_order']['pages']} pages | pairwise accuracy {pct(result['layer_scores']['reading_order']['micro_pairwise_accuracy'])}; matched-region recall {pct(result['layer_scores']['reading_order']['matched_region_recall'])} |",
             f"| Layout | {result['layer_scores']['layout']['pages']} pages | micro P/R/F1 {pct(result['layer_scores']['layout']['micro']['precision'])} / {pct(result['layer_scores']['layout']['micro']['recall'])} / {pct(result['layer_scores']['layout']['micro']['f1'])} |",
             f"| Table | {result['layer_scores']['table']['reference_tables']} tables on {result['layer_scores']['table']['pages_with_reviewed_tables']} pages | detection P/R/F1 {pct(result['layer_scores']['table']['detection_precision'])} / {pct(result['layer_scores']['table']['detection_recall'])} / {pct(result['layer_scores']['table']['detection_f1'])}; cell CER {pct(result['layer_scores']['table']['micro_cell_cer'])}; cell WER (whitespace) {pct(result['layer_scores']['table']['micro_cell_wer_whitespace'])}; exact grids {pct(result['layer_scores']['table']['exact_grid_rate'])} |", "",
             "### Layout per-class scores", "",
             "| Class | Precision | Recall | F1 | Reference regions | Predicted regions |", "|---|---:|---:|---:|---:|---:|"])
    for label, scores in result["layer_scores"]["layout"]["per_class"].items():
        lines.append(
            f"| {label} | {pct(scores['precision'])} | {pct(scores['recall'])} | {pct(scores['f1'])} | "
            f"{scores['reference_regions']} | {scores['predicted_regions']} |"
        )
    lines.extend([
             "",
             "## End-to-end cohort", "",
             f"{result['end_to_end_scores']['pages']} pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.", "",
             "| Layer | Metrics |", "|---|---|",
             f"| OCR | full-page CER {pct(result['end_to_end_scores']['ocr']['micro_cer'])}; full-page WER (PyVi) {pct(result['end_to_end_scores']['ocr']['micro_wer_pyvi'])} |",
             f"| Reading order | pairwise accuracy {pct(result['end_to_end_scores']['reading_order']['micro_pairwise_accuracy'])}; matched-region recall {pct(result['end_to_end_scores']['reading_order']['matched_region_recall'])} |",
             f"| Layout | micro P/R/F1 {pct(result['end_to_end_scores']['layout']['micro']['precision'])} / {pct(result['end_to_end_scores']['layout']['micro']['recall'])} / {pct(result['end_to_end_scores']['layout']['micro']['f1'])} |",
             f"| Table | detection P/R {pct(result['end_to_end_scores']['table']['detection_precision'])} / {pct(result['end_to_end_scores']['table']['detection_recall'])}; cell CER {pct(result['end_to_end_scores']['table']['micro_cell_cer'])}; cell WER (whitespace) {pct(result['end_to_end_scores']['table']['micro_cell_wer_whitespace'])} |", "",
             "## Notes", ""])
    lines.extend(f"- {note}" for note in result["caveats"])
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
