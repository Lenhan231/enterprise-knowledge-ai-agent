"""Evaluate normalized predictions against the references produced by data/review.html."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

TRACK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TRACK_ROOT / "tools"))

from metrics.text_metrics import character_error_count, token_error_count  # noqa: E402
from metrics.iou_metrics import iou, matched_pairs  # noqa: E402
from metrics.table_metrics import score_tables  # noqa: E402

IOU_THRESHOLD = 0.5
CLASSES = ("title", "text", "table", "figure")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def key(row: dict) -> tuple[str, int]:
    return row["document_id"], int(row["source_page_number_1based"])


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).casefold()).strip()


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
            if element.get("label") not in {"text", "title", "figure", "other"}:
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


def rotate_box_for_reading(box: list[float], clockwise: int) -> list[float]:
    left, top, right, bottom = box
    if clockwise == 90:
        return [1 - bottom, left, 1 - top, right]
    if clockwise == 180:
        return [1 - right, 1 - bottom, 1 - left, 1 - top]
    if clockwise == 270:
        return [top, 1 - right, bottom, 1 - left]
    return box


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


def score_ocr(
    references: list[dict], predictions: dict,
    reading_order_rotations: dict[tuple[str, int], int] | None = None,
) -> dict:
    from pyvi import ViTokenizer

    char_edits = ref_chars = word_edits = ref_words = whitespace_edits = ref_syllables = 0
    page_scores = []
    for reference in references:
        page_key = key(reference)
        prediction = predictions[page_key]
        predicted_tables = prediction.get("tables", [])
        blocks = []
        for element in prediction.get("elements", []):
            text, box = str(element.get("text", "")).strip(), element.get("bbox_norm")
            if not text or not box or any(iou(box, table["bbox_norm"]) > IOU_THRESHOLD for table in predicted_tables):
                continue
            blocks.append((box, text))
        for table in predicted_tables:
            serialized = "\n".join([" | ".join(table.get("columns", []))] + [" | ".join(row) for row in table.get("rows", [])])
            if serialized.strip():
                blocks.append((table["bbox_norm"], serialized))
        rotation = (reading_order_rotations or {}).get(page_key, 0)
        if rotation:
            blocks = [(rotate_box_for_reading(box, rotation), text) for box, text in blocks]
        blocks.sort(key=lambda item: (item[0][1], item[0][0]))
        expected, actual = normalize(reference["ocr_reference_text"]), normalize("\n".join(text for _, text in blocks))
        ce, nc = character_error_count(expected, actual)
        ref_tokens, pred_tokens = ViTokenizer.tokenize(expected).split(), ViTokenizer.tokenize(actual).split()
        we, nw = token_error_count(ref_tokens, pred_tokens)
        ref_syl, pred_syl = expected.split(), actual.split()
        se, ns = token_error_count(ref_syl, pred_syl)
        char_edits += ce; ref_chars += nc; word_edits += we; ref_words += nw
        whitespace_edits += se; ref_syllables += ns
        page_scores.append({"document_id": page_key[0], "source_page_number_1based": page_key[1], "text_order_rotation_clockwise": rotation, "cer": ce / nc if nc else None, "wer_pyvi": we / nw if nw else None, "whitespace_error": se / ns if ns else None})
    return {"pages": len(references), "micro_cer": char_edits / ref_chars if ref_chars else None,
            "micro_wer_pyvi": word_edits / ref_words if ref_words else None,
            "micro_whitespace_error": whitespace_edits / ref_syllables if ref_syllables else None,
            "character_edits": char_edits, "reference_characters": ref_chars,
            "word_edits": word_edits, "reference_words": ref_words, "page_scores": page_scores}


def score_layout(references: list[dict], predictions: dict) -> dict:
    counts = {label: [0, 0, 0] for label in CLASSES}  # TP, predicted, reference
    page_count = 0
    for reference in references:
        prediction = predictions[key(reference)]
        pred = [(e["label"], e["bbox_norm"]) for e in prediction.get("elements", []) if e["label"] != "other"]
        pred += [("table", table["bbox_norm"]) for table in prediction.get("tables", [])]
        gold = [(r["label"], r["bbox_norm"]) for r in reference.get("regions", [])]
        for label in CLASSES:
            p = [{"box": box} for cls, box in pred if cls == label]
            g = [{"box": box} for cls, box in gold if cls == label]
            matches = matched_pairs(p, g, lambda x: x["box"], lambda x: x["box"], IOU_THRESHOLD)
            counts[label][0] += len(matches); counts[label][1] += len(p); counts[label][2] += len(g)
        page_count += 1
    tp = sum(v[0] for v in counts.values()); predicted = sum(v[1] for v in counts.values()); gold = sum(v[2] for v in counts.values())
    precision = tp / predicted if predicted else 0; recall = tp / gold if gold else 0
    per_class = {}
    for label, (class_tp, class_pred, class_ref) in counts.items():
        p = class_tp / class_pred if class_pred else 0; r = class_tp / class_ref if class_ref else 0
        per_class[label] = {"true_positive": class_tp, "predicted_regions": class_pred, "reference_regions": class_ref,
                            "precision": p, "recall": r, "f1": 2*p*r/(p+r) if p+r else 0}
    return {"pages": page_count, "iou_threshold": IOU_THRESHOLD,
            "micro": {"true_positive": tp, "predicted_regions": predicted, "reference_regions": gold,
                      "precision": precision, "recall": recall, "f1": 2*precision*recall/(precision+recall) if precision+recall else 0},
            "per_class": per_class}


def score_cohort(
    ocr_refs: list[dict], layout_refs: list[dict], table_refs: list[dict],
    predictions: dict, reading_order_rotations: dict[tuple[str, int], int] | None = None,
) -> dict:
    keys = set(map(key, ocr_refs)) | set(map(key, layout_refs)) | {key(x) for x in table_refs}
    missing = keys - predictions.keys()
    if missing:
        raise ValueError(f"Missing predictions for {sorted(missing)}")
    return {"pages": len(keys), "ocr": score_ocr(ocr_refs, predictions, reading_order_rotations),
            "layout": score_layout(layout_refs, predictions),
            "table": score_tables(table_refs, predictions, key, IOU_THRESHOLD)}


def evaluate(args: argparse.Namespace) -> dict:
    refs = {track: read_jsonl(TRACK_ROOT / f"data/{track}/reference.jsonl") for track in ("ocr", "layout", "table", "end-to-end")}
    if args.page_id:
        target = next((row for row in refs["ocr"] if row.get("reference_id") == args.page_id), None)
        if target is None:
            raise SystemExit(f"No OCR reference found for page: {args.page_id}")
        page_key = key(target)
        refs = {track: [row for row in rows if key(row) == page_key] for track, rows in refs.items()}
    predictions = validate(read_jsonl(args.predictions))
    meta_path = args.predictions.parent / "run-metadata.json"
    metadata = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    reading_order_rotations = text_order_rotations(metadata)
    layer_scores = score_cohort(
        refs["ocr"], refs["layout"], refs["table"], predictions,
        reading_order_rotations,
    )
    e2e_ocr = [{"document_id": r["document_id"], "source_page_number_1based": r["source_page_number_1based"], "ocr_reference_text": r["ocr_reference_text"]} for r in refs["end-to-end"]]
    e2e_layout = [{"document_id": r["document_id"], "source_page_number_1based": r["source_page_number_1based"], "regions": r["layout_regions"]} for r in refs["end-to-end"]]
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
                         "prediction_pages": len(predictions), "inference_successful_pages": metadata.get("successful_pages")},
            "runtime": {"device": metadata.get("device"),
                        "inference_wall_seconds": metadata.get("inference_wall_seconds", metadata.get("wall_seconds")),
                        "peak_process_rss_mib": metadata.get("inference_peak_process_rss_mib", metadata.get("peak_process_rss_mib"))},
            "caveats": ["Owner-reviewed working references from the shared HTML review flow.",
                         "OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.",
                         "Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.",
                         "End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True, help="predictions.jsonl from run_shared_benchmark.py")
    parser.add_argument("--output-dir", type=Path, help="Defaults to the predictions directory")
    parser.add_argument("--page-id", help="Score one page from a focused runner invocation")
    args = parser.parse_args()
    result = evaluate(args)
    output_dir = args.output_dir or args.predictions.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(render_report(result), encoding="utf-8")
    print(f"Saved {output_dir / 'report.md'} and {output_dir / 'evaluation.json'}")


def render_report(result: dict) -> str:
    def pct(value): return "n/a" if value is None else f"{value:.2%}"
    lines = [f"# {result['engine']} benchmark: {result['dataset']}", "",
             f"**Run:** `{result['run_id']}` · **Predictions:** {result['coverage']['prediction_pages']} pages · **Inference success:** {result['coverage']['inference_successful_pages']}",
             f"**Runtime:** {result['runtime']['inference_wall_seconds']}s on {result['runtime']['device']}" +
             (f" · peak process RSS {result['runtime']['peak_process_rss_mib']} MiB" if result['runtime']['peak_process_rss_mib'] is not None else " · peak inference RSS unavailable"), "",
             "## Independent layer scores", "",
             "| Layer | Cohort | Metrics |", "|---|---:|---|",
             f"| OCR | {result['layer_scores']['ocr']['pages']} pages | CER {pct(result['layer_scores']['ocr']['micro_cer'])}; WER (PyVi) {pct(result['layer_scores']['ocr']['micro_wer_pyvi'])}; whitespace error {pct(result['layer_scores']['ocr']['micro_whitespace_error'])} |",
             f"| Layout | {result['layer_scores']['layout']['pages']} pages | micro P/R/F1 {pct(result['layer_scores']['layout']['micro']['precision'])} / {pct(result['layer_scores']['layout']['micro']['recall'])} / {pct(result['layer_scores']['layout']['micro']['f1'])} |",
             f"| Table | {result['layer_scores']['table']['reference_tables']} tables on {result['layer_scores']['table']['pages_with_reviewed_tables']} pages | detection P/R/F1 {pct(result['layer_scores']['table']['detection_precision'])} / {pct(result['layer_scores']['table']['detection_recall'])} / {pct(result['layer_scores']['table']['detection_f1'])}; cell CER {pct(result['layer_scores']['table']['micro_cell_cer'])}; cell WER (whitespace) {pct(result['layer_scores']['table']['micro_cell_wer_whitespace'])}; exact grids {pct(result['layer_scores']['table']['exact_grid_rate'])} |", "",
             "## End-to-end cohort", "",
             f"{result['end_to_end_scores']['pages']} pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.", "",
             "| Layer | Metrics |", "|---|---|",
             f"| OCR | CER {pct(result['end_to_end_scores']['ocr']['micro_cer'])}; WER (PyVi) {pct(result['end_to_end_scores']['ocr']['micro_wer_pyvi'])} |",
             f"| Layout | micro P/R/F1 {pct(result['end_to_end_scores']['layout']['micro']['precision'])} / {pct(result['end_to_end_scores']['layout']['micro']['recall'])} / {pct(result['end_to_end_scores']['layout']['micro']['f1'])} |",
             f"| Table | detection P/R {pct(result['end_to_end_scores']['table']['detection_precision'])} / {pct(result['end_to_end_scores']['table']['detection_recall'])}; cell CER {pct(result['end_to_end_scores']['table']['micro_cell_cer'])}; cell WER (whitespace) {pct(result['end_to_end_scores']['table']['micro_cell_wer_whitespace'])} |", "",
             "## Notes", ""]
    lines.extend(f"- {note}" for note in result["caveats"])
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
