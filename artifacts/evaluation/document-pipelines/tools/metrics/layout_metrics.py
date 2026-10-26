"""Layout region detection and per-class scoring."""

from __future__ import annotations

from metrics import page_key
from metrics.iou_metrics import matched_pairs

CLASSES = ("title", "title_table", "text", "table", "figure", "page_header", "section_header", "page_footer")


def score_layout(references: list[dict], predictions: dict, iou_threshold: float = 0.5) -> dict:
    counts = {label: [0, 0, 0] for label in CLASSES}  # TP, predicted, reference
    page_count = 0
    for reference in references:
        prediction = predictions[page_key(reference)]
        pred = [(e["label"], e["bbox_norm"]) for e in prediction.get("elements", []) if e["label"] != "other"]
        pred += [("table", table["bbox_norm"]) for table in prediction.get("tables", [])]
        gold = [(r["label"], r["bbox_norm"]) for r in reference.get("regions", [])]
        for label in CLASSES:
            p = [{"box": box} for cls, box in pred if cls == label]
            g = [{"box": box} for cls, box in gold if cls == label]
            matches = matched_pairs(p, g, lambda x: x["box"], lambda x: x["box"], iou_threshold)
            counts[label][0] += len(matches); counts[label][1] += len(p); counts[label][2] += len(g)
        page_count += 1
    tp = sum(v[0] for v in counts.values()); predicted = sum(v[1] for v in counts.values()); gold = sum(v[2] for v in counts.values())
    precision = tp / predicted if predicted else 0; recall = tp / gold if gold else 0
    per_class = {}
    for label, (class_tp, class_pred, class_ref) in counts.items():
        p = class_tp / class_pred if class_pred else 0; r = class_tp / class_ref if class_ref else 0
        per_class[label] = {"true_positive": class_tp, "predicted_regions": class_pred, "reference_regions": class_ref,
                            "precision": p, "recall": r, "f1": 2*p*r/(p+r) if p+r else 0}
    return {"pages": page_count, "iou_threshold": iou_threshold,
            "micro": {"true_positive": tp, "predicted_regions": predicted, "reference_regions": gold,
                      "precision": precision, "recall": recall, "f1": 2*precision*recall/(precision+recall) if precision+recall else 0},
            "per_class": per_class}
