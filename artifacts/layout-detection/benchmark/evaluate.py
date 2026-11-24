"""Score layout predictions and build a browsable overlay report."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import statistics
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[1]
SOURCE_ROOT = REPO_ROOT / "artifacts/evaluation/document-pipelines/data"
CLASSES = ("text", "table", "figure")
MODELS = (
    "pp_doclayout_v3_production",
    "heron_101",
    "doclayout_yolo_docstructbench",
)
COLORS = {"text": "#4ba3ff", "title": "#c77dff", "table": "#35c99a", "figure": "#ff9b54"}
FOUR_CLASSES = ("text", "title", "table", "figure")
TITLE_LABELS = {
    "pp_doclayout_v3_production": {"doc_title", "paragraph_title", "table_title", "figure_title", "chart_title"},
    "heron_101": {"title", "section_header"},
    "doclayout_yolo_docstructbench": {"title", "table_caption", "figure_caption"},
}
IOU_THRESHOLD = 0.5


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def box_iou(a: list[float], b: list[float]) -> float:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def maximum_iou_matches(reference: list[dict], predictions: list[dict], threshold: float = IOU_THRESHOLD) -> list[tuple[int, int, float]]:
    """Return a maximum-cardinality one-to-one matching above the fixed IoU gate."""
    edges = {
        pred_index: sorted(
            ((ref_index, box_iou(ref["bbox_norm"], pred["bbox_norm"]))
             for ref_index, ref in enumerate(reference)
             if box_iou(ref["bbox_norm"], pred["bbox_norm"]) >= threshold),
            key=lambda pair: (-pair[1], pair[0]),
        )
        for pred_index, pred in enumerate(predictions)
    }
    assigned: dict[int, int] = {}

    def augment(pred_index: int, seen: set[int]) -> bool:
        for ref_index, _iou in edges[pred_index]:
            if ref_index in seen:
                continue
            seen.add(ref_index)
            if ref_index not in assigned or augment(assigned[ref_index], seen):
                assigned[ref_index] = pred_index
                return True
        return False

    for pred_index in sorted(edges):
        augment(pred_index, set())
    return sorted(
        ((ref_index, pred_index, box_iou(reference[ref_index]["bbox_norm"], predictions[pred_index]["bbox_norm"]))
         for ref_index, pred_index in assigned.items()),
        key=lambda item: item[0],
    )


def union_area(boxes: list[list[float]]) -> float:
    """Measure rectangles once even when several boxes overlap."""
    boundaries = sorted({x for left, _, right, _ in boxes for x in (left, right)})
    area = 0.0
    for start, end in zip(boundaries, boundaries[1:]):
        intervals = sorted(
            (top, bottom) for left, top, right, bottom in boxes
            if left < end and right > start
        )
        covered_height = 0.0
        last_bottom = 0.0
        for top, bottom in intervals:
            covered_height += max(0.0, bottom - max(top, last_bottom))
            last_bottom = max(last_bottom, bottom)
        area += (end - start) * covered_height
    return area


def score(reference_rows: list[dict], prediction_rows: list[dict], classes: tuple[str, ...] = CLASSES) -> tuple[dict, list[dict]]:
    references = {row["sample_id"]: row for row in reference_rows}
    predictions = {(row["model"], row["sample_id"]): row for row in prediction_rows}
    expected = {(model, sample_id) for model in MODELS for sample_id in references}
    missing = sorted(expected - predictions.keys())
    if missing:
        raise ValueError(f"Missing {len(missing)} model/page outputs; first: {missing[:5]}")

    model_reports = {}
    mismatches = []
    for model in MODELS:
        totals = {label: {"tp": 0, "fp": 0, "fn": 0} for label in classes}
        matched_ious = {label: [] for label in classes}
        strict_matches = dict.fromkeys(classes, 0)
        text_gt_area = text_pred_area = text_overlap = 0.0
        latencies = []
        for sample_id, reference in references.items():
            pred_row = predictions[(model, sample_id)]
            latencies.append(float(pred_row.get("inference_seconds", 0.0)))
            for label in classes:
                gt = [
                    {"bbox_norm": region["bbox_norm"], "region_id": region.get("region_id"),
                     "original_label": region.get("label")}
                    for region in reference["regions"] if region["benchmark_label"] == label
                ]
                pred = [
                    {"bbox_norm": item["bbox_norm"], "raw_label": item.get("raw_label"),
                     "confidence": item.get("confidence")}
                    for item in pred_row.get("predictions", []) if item["label"] == label
                ]
                if label == "text":
                    gt_boxes = [item["bbox_norm"] for item in gt]
                    pred_boxes = [item["bbox_norm"] for item in pred]
                    gt_area = union_area(gt_boxes)
                    pred_area = union_area(pred_boxes)
                    overlap = gt_area + pred_area - union_area(gt_boxes + pred_boxes)
                    text_gt_area += gt_area
                    text_pred_area += pred_area
                    text_overlap += min(gt_area, pred_area, max(0.0, overlap))
                matches = maximum_iou_matches(gt, pred)
                if classes == FOUR_CLASSES:
                    matched_ious[label].extend(overlap for _, _, overlap in matches)
                    strict_matches[label] += len(maximum_iou_matches(gt, pred, 0.75))
                ref_matched = {item[0] for item in matches}
                pred_matched = {item[1] for item in matches}
                counts = {"tp": len(matches), "fp": len(pred) - len(matches), "fn": len(gt) - len(matches)}
                for key, value in counts.items():
                    totals[label][key] += value
                for ref_index, pred_index, overlap in matches:
                    if overlap < 0.65:
                        mismatches.append({
                            "model": model, "sample_id": sample_id, "label": label,
                            "kind": "weak_match", "iou": round(overlap, 4),
                            "reference": gt[ref_index], "prediction": pred[pred_index],
                        })
                for ref_index, item in enumerate(gt):
                    if ref_index not in ref_matched:
                        mismatches.append({"model": model, "sample_id": sample_id, "label": label,
                                           "kind": "missed_reference", "reference": item})
                for pred_index, item in enumerate(pred):
                    if pred_index not in pred_matched:
                        mismatches.append({"model": model, "sample_id": sample_id, "label": label,
                                           "kind": "false_positive", "prediction": item})
        per_class = {}
        f1_values = []
        for label, counts in totals.items():
            precision = counts["tp"] / (counts["tp"] + counts["fp"]) if counts["tp"] + counts["fp"] else 0.0
            recall = counts["tp"] / (counts["tp"] + counts["fn"]) if counts["tp"] + counts["fn"] else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            f1_values.append(f1)
            per_class[label] = {**counts, "precision": precision, "recall": recall, "f1": f1}
            if classes == FOUR_CLASSES:
                denominator = 2 * counts["tp"] + counts["fp"] + counts["fn"]
                per_class[label].update(
                    f1_iou_075=2 * strict_matches[label] / denominator if denominator else 0.0,
                    median_matched_iou=statistics.median(matched_ious[label]) if matched_ious[label] else None,
                )
        aggregate = {key: sum(counts[key] for counts in totals.values()) for key in ("tp", "fp", "fn")}
        micro_p = aggregate["tp"] / (aggregate["tp"] + aggregate["fp"]) if aggregate["tp"] + aggregate["fp"] else 0.0
        micro_r = aggregate["tp"] / (aggregate["tp"] + aggregate["fn"]) if aggregate["tp"] + aggregate["fn"] else 0.0
        micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if micro_p + micro_r else 0.0
        model_reports[model] = {
            "page_count": len(references),
            "per_class": per_class,
            "macro_f1": statistics.mean(f1_values),
            "micro": {**aggregate, "precision": micro_p, "recall": micro_r, "f1": micro_f1},
            "text_area": {
                "precision": text_overlap / text_pred_area if text_pred_area else 0.0,
                "recall": text_overlap / text_gt_area if text_gt_area else 0.0,
                "dice": 2 * text_overlap / (text_pred_area + text_gt_area)
                if text_pred_area + text_gt_area else 0.0,
            },
            "latency_seconds_per_page": {
                "mean": statistics.mean(latencies) if latencies else 0.0,
                "median": statistics.median(latencies) if latencies else 0.0,
                "total": sum(latencies),
            },
        }
    report = {
        "cohort": {"pages": len(references), "documents": len({r["document_id"] for r in reference_rows}),
                   "regions": sum(len(r["regions"]) for r in reference_rows)},
        "matching": {"class_aware": True, "minimum_iou": IOU_THRESHOLD,
                     "one_to_one": True, "assignment": "maximum-cardinality bipartite matching"},
        "confidence_threshold": 0.25,
        "text_area_method": "Intersection of box unions per page, summed in normalized page area units",
        "classes": list(classes),
        "models": model_reports,
    }
    return report, mismatches


def rects(items: list[dict], *, predicted: bool) -> str:
    pieces = []
    for item in items:
        label = item.get("benchmark_label", item.get("label"))
        box = item["bbox_norm"]
        x, y, width, height = box[0], box[1], box[2] - box[0], box[3] - box[1]
        color = COLORS.get(label, "#fff")
        dash = ' stroke-dasharray="0.008 0.005"' if predicted else ""
        confidence = f" · {float(item['confidence']):.2f}" if predicted and item.get("confidence") is not None else ""
        raw_label = f" · {html.escape(str(item['raw_label']))}" if predicted and item.get("raw_label") else ""
        pieces.append(
            f'<rect x="{x:.6f}" y="{y:.6f}" width="{width:.6f}" height="{height:.6f}" '
            f'fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="0.0025" '
            f'vector-effect="non-scaling-stroke"{dash}><title>{label}{raw_label}{confidence}</title></rect>'
        )
    return "".join(pieces)


def render_html(reference_rows: list[dict], prediction_rows: list[dict], report: dict, output: Path) -> None:
    refs = {row["sample_id"]: row for row in reference_rows}
    preds = {(row["model"], row["sample_id"]): row for row in prediction_rows}
    image_root = SOURCE_ROOT
    lines = ["""
<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Layout Detection Benchmark</title><style>
body{font:14px/1.45 system-ui,sans-serif;margin:24px;background:#10151c;color:#e7edf5}h1{margin:0 0 8px}p{color:#adbacb}.metrics{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}.metric{background:#1b2530;padding:12px 16px;border-radius:8px}.metric b{display:block;font-size:18px}.legend{display:flex;gap:16px;margin:16px 0}.swatch{display:inline-block;width:12px;height:12px;margin-right:6px}.page{border:1px solid #344252;border-radius:10px;margin:14px 0;background:#151d27}.page summary{cursor:pointer;padding:14px;font-weight:600}.panels{display:grid;grid-template-columns:repeat(4,minmax(220px,1fr));gap:12px;padding:0 12px 14px;overflow:auto}.panel{min-width:220px}.panel h3{font-size:13px;margin:8px 0}.image{position:relative;width:100%;background:#080b0e}.image img{display:block;width:100%;height:100%;object-fit:fill}.image svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}.small{font-size:12px;color:#aab8c8}.top{max-width:1200px;margin:auto}table{border-collapse:collapse;width:100%;margin:18px 0;background:#151d27}th,td{padding:8px 10px;border:1px solid #344252;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#1b2530}@media(max-width:900px){.panels{grid-template-columns:repeat(2,minmax(220px,1fr))}}@media(max-width:500px){.panels{grid-template-columns:1fr}}
</style><body><main class="top"><h1>Layout detection · ground truth vs model output</h1>
<p>Solid outlines are reference boxes. Dashed outlines are model boxes. Box matching uses the same class, one-to-one assignment and IoU ≥ 0.50.</p>
"""]
    classes = report["classes"]
    lines.append('<div class="legend">' + "".join(
        f'<span><i class="swatch" style="background:{COLORS[label]}"></i>{label.title()}</span>'
        for label in classes
    ) + '</div>')
    lines.append(
        '<table><thead><tr><th>Model</th><th>Macro F1</th>'
        + "".join(f'<th>{label.title()} F1</th>' for label in classes)
        + '<th>Micro F1</th><th>Mean sec/page</th></tr></thead><tbody>'
    )
    for model in MODELS:
        scores = report["models"][model]
        lines.append(
            f'<tr><td>{html.escape(model)}</td><td>{scores["macro_f1"]:.1%}</td>'
            + "".join(f'<td>{scores["per_class"][label]["f1"]:.1%}</td>' for label in classes)
            + f'<td>{scores["micro"]["f1"]:.1%}</td>'
            f'<td>{scores["latency_seconds_per_page"]["mean"]:.3f}</td></tr>'
        )
    lines.append("</tbody></table>")
    if classes == list(FOUR_CLASSES):
        lines.append('<h2>Box localization</h2><table><thead><tr><th>Model</th><th>Class</th>'
                     '<th>F1 at IoU 0.75</th><th>Median IoU of matches at 0.50</th></tr></thead><tbody>')
        for model, scores in report["models"].items():
            for label, values in scores["per_class"].items():
                median = values["median_matched_iou"]
                median_display = f"{median:.1%}" if median is not None else "—"
                lines.append(f'<tr><td>{html.escape(model)}</td><td>{label}</td>'
                             f'<td>{values["f1_iou_075"]:.1%}</td><td>{median_display}</td></tr>')
        lines.append("</tbody></table>")
    lines.append(
        '<h2>Text area overlap</h2><p>Computed from the union of text boxes on each page. '
        'Area recall is the share of reference area covered by predictions. Area precision is the share '
        'of predicted area overlapping the reference. Dice combines both.</p>'
        '<table><thead><tr><th>Model</th><th>Area precision</th><th>Area recall</th><th>Dice</th></tr></thead><tbody>'
    )
    for model in MODELS:
        area = report["models"][model]["text_area"]
        lines.append(
            f'<tr><td>{html.escape(model)}</td><td>{area["precision"]:.1%}</td>'
            f'<td>{area["recall"]:.1%}</td><td>{area["dice"]:.1%}</td></tr>'
        )
    lines.append("</tbody></table>")
    for index, (sample_id, reference) in enumerate(refs.items()):
        image_rel = Path(__import__("os").path.relpath(image_root / reference["source_image"], output.parent)).as_posix()
        title = (f"{sample_id} · {reference['document_id']} · PDF p.{reference['source_page_number_1based']} "
                 f"· {len(reference['regions'])} reference boxes")
        lines.append(f'<details class="page"{" open" if index == 0 else ""}><summary>{html.escape(title)}</summary><div class="panels">')
        model_specs = [("Ground truth", None), *((name, name) for name in MODELS)]
        for title_text, model in model_specs:
            if model is None:
                boxes = reference["regions"]
                count = len(boxes)
                svg_boxes = rects(boxes, predicted=False)
            else:
                boxes = preds[(model, sample_id)].get("predictions", [])
                count = len(boxes)
                svg_boxes = rects(boxes, predicted=True)
            lines.append(
                f'<section class="panel"><h3>{html.escape(title_text)} <span class="small">({count})</span></h3>'
                f'<div class="image" style="aspect-ratio:{reference["width"]}/{reference["height"]}">'
                f'<img loading="lazy" src="{html.escape(image_rel, quote=True)}" alt="{html.escape(sample_id)}">'
                f'<svg viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">{svg_boxes}</svg>'
                '</div></section>'
            )
        lines.append("</div></details>")
    lines.append("</main></body></html>")
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--references", type=Path, default=PACKAGE_ROOT / "references/layout.jsonl")
    parser.add_argument("--predictions", type=Path, required=True,
                        help="Kaggle output directory containing predictions-*.jsonl")
    parser.add_argument("--output", type=Path, default=PACKAGE_ROOT / "results/current")
    parser.add_argument("--four-classes", action="store_true", help="Score text, title, table and figure separately")
    args = parser.parse_args()
    references = read_jsonl(args.references)
    prediction_rows = []
    for path in sorted(args.predictions.rglob("predictions-*.jsonl")):
        prediction_rows.extend(read_jsonl(path))
    if not prediction_rows:
        raise ValueError(f"No predictions-*.jsonl found in {args.predictions}")
    if args.four_classes:
        for row in prediction_rows:
            for prediction in row["predictions"]:
                raw_label = prediction["raw_label"].strip().lower().replace(" ", "_").replace("-", "_")
                if raw_label in TITLE_LABELS[row["model"]]:
                    prediction["label"] = "title"
    classes = FOUR_CLASSES if args.four_classes else CLASSES
    unknown_labels = {region["benchmark_label"] for row in references for region in row["regions"]} - set(classes)
    if unknown_labels:
        parser.error(f"Reference labels do not match scoring classes: {sorted(unknown_labels)}")
    report, mismatches = score(references, prediction_rows, classes)
    provenance_path = args.references.with_name(args.references.stem + "-provenance.json")
    if not provenance_path.is_file():
        provenance_path = PACKAGE_ROOT / "references/provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.is_file() else {}
    report["provenance"] = {
        "scoring_reference": str(args.references),
        "scoring_reference_sha256": hashlib.sha256(args.references.read_bytes()).hexdigest(),
        "source_reference": provenance.get("source_reference"),
        "source_reference_sha256": provenance.get("source_reference_sha256"),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "metrics.json", report)
    write_json(args.output / "mismatches.json", mismatches)
    render_html(references, prediction_rows, report, args.output / "comparison.html")
    metadata_files = list(args.predictions.rglob("run_metadata.json"))
    if metadata_files:
        shutil_copy = args.output / "run_metadata.json"
        shutil_copy.write_bytes(metadata_files[0].read_bytes())
    print(json.dumps({
        "pages": report["cohort"]["pages"],
        "macro_f1": {model: round(values["macro_f1"], 4) for model, values in report["models"].items()},
        "comparison_html": str(args.output / "comparison.html"),
        "mismatches": len(mismatches),
    }, indent=2))


if __name__ == "__main__":
    main()
