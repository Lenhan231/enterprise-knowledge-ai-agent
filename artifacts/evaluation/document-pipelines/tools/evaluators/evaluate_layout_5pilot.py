"""Rescore saved layout detector predictions against a frozen 5-page review set."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

TRACK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TRACK_ROOT / "tools"))

from metrics.iou_metrics import iou, matched_pairs  # noqa: E402
from metrics.layout_metrics import LAYOUT_BENCHMARK_LABEL_MAP  # noqa: E402

PRIORITY = ("table", "text", "title")
SECONDARY = ("figure", "page_furniture")


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def page_key(row: dict) -> tuple[str, int]:
    return row["document_id"], int(row["source_page_number_1based"])


def mapped_regions(items: list[dict], box_key: str) -> list[dict]:
    result = []
    for item in items:
        label = LAYOUT_BENCHMARK_LABEL_MAP.get(item["label"])
        if label:
            result.append({"label": label, "bbox_norm": item[box_key], "source_label": item["label"]})
    return result


def score(references: list[dict], predictions: dict, threshold: float) -> dict:
    labels = (*PRIORITY, *SECONDARY)
    totals = {label: [0, 0, 0] for label in labels}
    false_positives = []
    unmapped = []
    location_counts = [0, 0, 0]
    label_confusions: Counter[str] = Counter()
    for reference in references:
        key = page_key(reference)
        pred_row = predictions[key]
        pred_items = pred_row.get("layout_detections", [])
        pred = mapped_regions(pred_items, "bbox_norm")
        gold = reference["benchmark_regions"]
        for label in labels:
            p = [r for r in pred if r["label"] == label]
            g = [r for r in gold if r["label"] == label]
            matches = matched_pairs(p, g, lambda x: x["bbox_norm"], lambda x: x["bbox_norm"], threshold)
            totals[label][0] += len(matches)
            totals[label][1] += len(p)
            totals[label][2] += len(g)
            matched_pred = {pi for pi, _, _ in matches}
            for i, item in enumerate(p):
                if i in matched_pred:
                    continue
                nearest = max((iou(item["bbox_norm"], gbox["bbox_norm"]) for gbox in g), default=0.0)
                false_positives.append({
                    "page": reference["reference_id"], "label": label,
                    "source_label": item["source_label"], "bbox_norm": item["bbox_norm"],
                    "nearest_same_class_iou": round(nearest, 4),
                })
        for item in pred_items:
            if item["label"] == "other":
                unmapped.append({"page": reference["reference_id"], "label": item["label"], "bbox_norm": item["bbox_norm"]})
        priority_pred = [item for item in pred if item["label"] in PRIORITY]
        priority_gold = [item for item in gold if item["label"] in PRIORITY]
        location_matches = matched_pairs(
            priority_pred, priority_gold,
            lambda x: x["bbox_norm"], lambda x: x["bbox_norm"], threshold,
        )
        location_counts[0] += len(location_matches)
        location_counts[1] += len(priority_pred)
        location_counts[2] += len(priority_gold)
        for pred_i, gold_i, _ in location_matches:
            predicted_label = priority_pred[pred_i]["label"]
            gold_label = priority_gold[gold_i]["label"]
            if predicted_label != gold_label:
                label_confusions[f"{predicted_label}->{gold_label}"] += 1

    per_class = {}
    for label, (tp, predicted, reference_count) in totals.items():
        precision = tp / predicted if predicted else 0.0
        recall = tp / reference_count if reference_count else 0.0
        per_class[label] = {
            "tp": tp, "predicted": predicted, "reference": reference_count,
            "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        }

    tp = sum(totals[label][0] for label in PRIORITY)
    predicted = sum(totals[label][1] for label in PRIORITY)
    reference_count = sum(totals[label][2] for label in PRIORITY)
    precision = tp / predicted if predicted else 0.0
    recall = tp / reference_count if reference_count else 0.0
    location_tp, location_predicted, location_reference = location_counts
    location_precision = location_tp / location_predicted if location_predicted else 0.0
    location_recall = location_tp / location_reference if location_reference else 0.0
    return {
        "pages": len(references), "iou_threshold": threshold,
        "priority_labels": list(PRIORITY), "secondary_labels": list(SECONDARY),
        "priority_micro": {
            "tp": tp, "predicted": predicted, "reference": reference_count,
            "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        },
        "priority_macro_f1": sum(per_class[label]["f1"] for label in PRIORITY) / len(PRIORITY),
        "priority_localization_only": {
            "tp": location_tp, "predicted": location_predicted, "reference": location_reference,
            "precision": location_precision, "recall": location_recall,
            "f1": 2 * location_precision * location_recall / (location_precision + location_recall)
            if location_precision + location_recall else 0.0,
            "cross_label_matches": dict(label_confusions),
        },
        "per_class": per_class,
        "false_positives": false_positives,
        "false_positive_counts": dict(Counter(item["label"] for item in false_positives)),
        "unclassified_other_count": len(unmapped),
        "unclassified_other": unmapped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate", action="append", required=True, metavar="NAME=PATH",
                        help="Saved predictions.jsonl; repeat once per model candidate")
    parser.add_argument("--iou", type=float, default=0.5)
    args = parser.parse_args()

    references = rows(args.references)
    ref_keys = {page_key(row) for row in references}
    if len(ref_keys) != 5:
        raise SystemExit(f"Expected exactly five reference pages, got {len(ref_keys)}")
    if any("benchmark_regions" not in row for row in references):
        raise SystemExit("Every reference row must have frozen benchmark_regions")

    candidates = {}
    candidate_metadata = {}
    for value in args.candidate:
        name, separator, path_value = value.partition("=")
        if not separator or not name or not path_value:
            raise SystemExit(f"Invalid --candidate {value!r}; expected NAME=PATH")
        pred_rows = rows(Path(path_value))
        pred_by_key = {page_key(row): row for row in pred_rows}
        if set(pred_by_key) != ref_keys:
            raise SystemExit(f"{name}: prediction pages differ from the five reference pages")
        candidates[name] = score(references, pred_by_key, args.iou)
        metadata_path = Path(path_value).parent / "run-metadata.json"
        candidate_metadata[name] = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}

    best_macro = max(result["priority_macro_f1"] for result in candidates.values())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": args.output_dir.name.rsplit("-", 1)[0],
        "reference_file": str(args.references),
        "iou_threshold": args.iou,
        "candidate_order": sorted(candidates, key=lambda name: candidates[name]["priority_macro_f1"], reverse=True),
        "candidate_metadata": candidate_metadata,
        "expansion_gate": {
            "criterion": "best five-pilot macro-F1 over table/text/title > 85%",
            "best_macro_f1": best_macro,
            "passed": best_macro > 0.85,
            "decision": "run_next_5_page_batch" if best_macro > 0.85 else "continue_diagnosis_without_expanding",
        },
        "candidates": candidates,
    }
    (args.output_dir / "evaluation.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [f"# Layout detector comparison — {payload['benchmark']}", "",
             "Same five source pages, saved detector outputs, and IoU 0.50. No post-processing or heuristic was applied.", "",
             "Primary score is macro-F1 over table, text, and title; micro precision/recall/F1 are shown alongside per-class scores. Figure and page-furniture scores and unmatched predictions are reported separately.", "",
             "| Candidate | Priority macro-F1 | Priority micro P/R/F1 | Table F1 | Text F1 | Title F1 | Priority FP | Figure/page-furniture FP | Other |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name in payload["candidate_order"]:
        source_meta = candidate_metadata[name]
        result = candidates[name]
        micro = result["priority_micro"]
        cls = result["per_class"]
        fp = result["false_positive_counts"]
        primary_fp = sum(fp.get(label, 0) for label in PRIORITY)
        secondary_fp = sum(fp.get(label, 0) for label in SECONDARY)
        lines.append(f"| {name} | {result['priority_macro_f1']:.1%} | {micro['precision']:.1%}/{micro['recall']:.1%}/{micro['f1']:.1%} | {cls['table']['f1']:.1%} | {cls['text']['f1']:.1%} | {cls['title']['f1']:.1%} | {primary_fp} | {secondary_fp} | {result['unclassified_other_count']} |")
    lines += ["", "## Localization vs label diagnosis", "", "Diagnostic only: one-to-one box matching across table/text/title regardless of class, at the same IoU. Cross-label pairs indicate localization that succeeded but classification disagreed; these do not count as true positives in the benchmark score.", "", "| Candidate | Localization matches / references | Localization precision / recall | Cross-label pairs |", "|---|---:|---:|---:|"]
    for name in payload["candidate_order"]:
        diag = candidates[name]["priority_localization_only"]
        confusions = ", ".join(f"{k}: {v}" for k, v in sorted(diag["cross_label_matches"].items())) or "none"
        lines.append(f"| {name} | {diag['tp']} / {diag['reference']} | {diag['precision']:.1%} / {diag['recall']:.1%} | {confusions} |")
    best_name = payload["candidate_order"][0]
    best = candidates[best_name]
    best_diag = best["priority_localization_only"]
    lines += ["", "## Findings and 5-page expansion gate", "",
              f"Best priority macro-F1 is **{best['priority_macro_f1']:.1%}** (`{best_name}`), below the **85%** gate; the next five-page batch is therefore not opened.",
              f"For `{best_name}`, label-agnostic matching localizes {best_diag['tp']}/{best_diag['reference']} priority regions, while label-aware scoring accepts fewer. Cross-label pairs: {', '.join(f'{k} {v}' for k, v in sorted(best_diag['cross_label_matches'].items())) or 'none'}. Its table F1 is {best['per_class']['table']['f1']:.1%}, but it emits {best['false_positive_counts'].get('text', 0)} unmatched text boxes.",
              "The audited boxes show the main remaining errors are title regions classified as text and surplus text regions on table contents/marginal clutter. The p24 reference was tightened to visible text extents; labels and IoU threshold remained fixed."]
    lines += ["", "## Per-class counts", "", "TP / predictions / references; unmatched detector boxes are false positives.", ""]
    for name in payload["candidate_order"]:
        source_meta = candidate_metadata[name]
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"Source run: `{source_meta.get('run_id', 'unknown')}`; model: `{source_meta.get('layout_model', source_meta.get('model', name))}`; device: `{source_meta.get('device', 'unknown')}`; confidence/score threshold: `{source_meta.get('confidence_threshold', source_meta.get('score_threshold', 'not recorded'))}`.")
        lines.append("")
        lines.append("| Label | TP / predicted / reference | Precision | Recall | F1 | False positives |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for label in (*PRIORITY, *SECONDARY):
            metric = candidates[name]["per_class"][label]
            lines.append(f"| {label} | {metric['tp']} / {metric['predicted']} / {metric['reference']} | {metric['precision']:.1%} | {metric['recall']:.1%} | {metric['f1']:.1%} | {candidates[name]['false_positive_counts'].get(label, 0)} |")
        lines.append("")
        lines.append("False positive summary (all coordinates and nearest IoU values are in `evaluation.json`):")
        lines.append("")
        if candidates[name]["false_positives"]:
            for label in (*PRIORITY, *SECONDARY):
                items = [item for item in candidates[name]["false_positives"] if item["label"] == label]
                if not items:
                    continue
                examples = "; ".join(f"`{item['page']}` `{item['bbox_norm']}` IoU `{item['nearest_same_class_iou']:.2f}`" for item in items[:2])
                lines.append(f"- `{label}`: {len(items)} FP. Examples: {examples}")
        else:
            lines.append("- None")
        lines.append(f"- Unclassified `other` boxes: {candidates[name]['unclassified_other_count']}")
        lines.append("")
    (args.output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved {args.output_dir / 'report.md'} and evaluation.json")


if __name__ == "__main__":
    main()
