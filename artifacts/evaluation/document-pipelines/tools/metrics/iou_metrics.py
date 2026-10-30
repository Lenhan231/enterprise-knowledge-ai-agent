"""Intersection-over-union and one-to-one box matching metrics."""

from __future__ import annotations


def iou(first: list[float], second: list[float]) -> float:
    x1, y1 = max(first[0], second[0]), max(first[1], second[1])
    x2, y2 = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, first[2] - first[0]) * max(0, first[3] - first[1])
    area_b = max(0, second[2] - second[0]) * max(0, second[3] - second[1])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def matched_pairs(predicted: list[dict], reference: list[dict], pred_box, ref_box,
                  threshold: float = 0.5) -> list[tuple[int, int, float]]:
    """Greedily pair boxes by descending IoU, using each box at most once."""
    candidates = sorted(
        ((iou(pred_box(p), ref_box(r)), pi, ri) for pi, p in enumerate(predicted) for ri, r in enumerate(reference)),
        reverse=True,
    )
    used_pred, used_ref, matches = set(), set(), []
    for overlap, pi, ri in candidates:
        if overlap < threshold:
            break
        if pi not in used_pred and ri not in used_ref:
            used_pred.add(pi)
            used_ref.add(ri)
            matches.append((pi, ri, overlap))
    return matches
