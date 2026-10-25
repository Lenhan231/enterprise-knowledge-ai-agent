"""Pairwise reading-order scoring over matched page regions."""

from __future__ import annotations

from metrics import page_key
from metrics.iou_metrics import iou


def score_reading_order(references: list[dict], predictions: dict, iou_threshold: float = 0.5) -> dict:
    """Pairwise order accuracy over geometrically matched regions."""
    concordant = compared = matched_regions = reference_regions = 0
    page_scores = []
    for reference in references:
        ordered_ids = reference.get("reading_order", [])
        by_id = {region.get("region_id"): region for region in reference.get("regions", [])}
        gold = [by_id[region_id] for region_id in ordered_ids if region_id in by_id]
        reference_regions += len(gold)
        page = predictions[page_key(reference)]
        candidates = list(page.get("elements", [])) + [
            {**table, "label": "table"} for table in page.get("tables", [])
        ]
        pairs = []
        used = set()
        for gold_index, region in enumerate(gold):
            options = [
                (iou(region["bbox_norm"], candidate["bbox_norm"]), index, candidate)
                for index, candidate in enumerate(candidates)
                if index not in used and candidate.get("bbox_norm")
            ]
            if not options:
                continue
            overlap, pred_index, candidate = max(options, key=lambda item: item[0])
            if overlap < iou_threshold:
                continue
            used.add(pred_index)
            order = candidate.get("order", pred_index)
            pairs.append((gold_index, float(order)))
        pair_count = len(pairs) * (len(pairs) - 1) // 2
        correct = sum(
            (pairs[i][0] - pairs[j][0]) * (pairs[i][1] - pairs[j][1]) > 0
            for i in range(len(pairs)) for j in range(i + 1, len(pairs))
        )
        concordant += correct
        compared += pair_count
        matched_regions += len(pairs)
        page_scores.append({"document_id": page_key(reference)[0], "source_page_number_1based": page_key(reference)[1],
                            "matched_regions": len(pairs), "reference_regions": len(gold),
                            "compared_pairs": pair_count, "pairwise_accuracy": correct / pair_count if pair_count else None})
    return {"pages": len(references), "micro_pairwise_accuracy": concordant / compared if compared else None,
            "concordant_pairs": concordant, "compared_pairs": compared,
            "matched_regions": matched_regions, "reference_regions": reference_regions,
            "matched_region_recall": matched_regions / reference_regions if reference_regions else None,
            "page_scores": page_scores}
