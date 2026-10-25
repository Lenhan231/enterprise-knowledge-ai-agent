"""Table detection and cell-grid scoring for normalized page predictions."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from metrics.iou_metrics import matched_pairs
from metrics.text_metrics import character_error_count, token_error_count


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).casefold()).strip()


def as_grid(table: dict) -> list[list[str]]:
    return [list(map(str, table.get("columns", [])))] + [list(map(str, row)) for row in table.get("rows", [])]


def score_tables(references: list[dict], predictions: dict, key, iou_threshold: float = 0.5) -> dict:
    by_page: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for ref in references:
        by_page[key(ref)].append(ref)
    detected = pred_count = ref_count = 0
    edits = ref_chars = word_edits = ref_words = cell_matches = cell_positions = body_matches = ref_body_cells = pred_body_cells = 0
    shape_exact = exact_grids = 0
    items = []
    for page_key, gold in by_page.items():
        predicted = predictions[page_key].get("tables", [])
        pairs = matched_pairs(predicted, gold, lambda x: x["bbox_norm"], lambda x: x["table_bbox_norm"], iou_threshold)
        pred_count += len(predicted); ref_count += len(gold); detected += len(pairs)
        pair_by_gold = {gi: (pi, overlap) for pi, gi, overlap in pairs}
        for gi, reference in enumerate(gold):
            pi, overlap = pair_by_gold[gi] if gi in pair_by_gold else (None, 0.0)
            ref_grid = reference["cell_grid"]
            pred_grid = as_grid(predicted[pi]) if pi is not None else []
            rows = max(len(ref_grid), len(pred_grid))
            cols = max(max(map(len, ref_grid), default=0), max(map(len, pred_grid), default=0))
            page_edits = page_chars = page_word_edits = page_ref_words = matches = positions = body_matches_page = 0
            for ri in range(rows):
                for ci in range(cols):
                    expected = normalize(str(ref_grid[ri][ci])) if ri < len(ref_grid) and ci < len(ref_grid[ri]) else ""
                    actual = normalize(str(pred_grid[ri][ci])) if ri < len(pred_grid) and ci < len(pred_grid[ri]) else ""
                    ce, nc = character_error_count(expected, actual)
                    we, nw = token_error_count(expected.split(), actual.split())
                    page_edits += ce; page_chars += nc; page_word_edits += we; page_ref_words += nw
                    matches += int(expected == actual and ri < len(ref_grid) and ci < len(ref_grid[ri]))
                    positions += int(ri < len(ref_grid) and ci < len(ref_grid[ri]))
                    body_matches_page += int(ri > 0 and expected == actual and ri < len(ref_grid) and ci < len(ref_grid[ri]))
            edits += page_edits; ref_chars += page_chars; word_edits += page_word_edits; ref_words += page_ref_words
            cell_matches += matches; cell_positions += positions; body_matches += body_matches_page
            ref_body_cells += sum(len(row) for row in ref_grid[1:])
            if pi is not None:
                pred_body_cells += sum(len(row) for row in predicted[pi].get("rows", []))
            exact = pi is not None and ref_grid == pred_grid
            exact_grids += int(exact)
            exact_shape = pi is not None and len(ref_grid) == len(pred_grid) and len(ref_grid[0]) == len(pred_grid[0])
            shape_exact += int(exact_shape)
            items.append({"reference_id": reference["reference_id"], "matched": pi is not None, "bbox_iou": overlap,
                          "cell_cer": page_edits / page_chars if page_chars else None,
                          "cell_wer_whitespace": page_word_edits / page_ref_words if page_ref_words else None,
                          "cell_accuracy": matches / positions if positions else None,
                          "shape_exact": exact_shape, "exact_grid": exact})
    precision = detected / pred_count if pred_count else 0; recall = detected / ref_count if ref_count else 0
    cell_p = body_matches / pred_body_cells if pred_body_cells else 0; cell_r = body_matches / ref_body_cells if ref_body_cells else 0
    return {"pages_with_reviewed_tables": len(by_page), "reference_tables": ref_count, "predicted_tables": pred_count,
            "matched_tables_iou50": detected, "detection_precision": precision, "detection_recall": recall,
            "detection_f1": 2*precision*recall/(precision+recall) if precision+recall else 0,
            "micro_cell_cer": edits/ref_chars if ref_chars else None,
            "micro_cell_wer_whitespace": word_edits/ref_words if ref_words else None,
            "positional_cell_accuracy": cell_matches/cell_positions if cell_positions else None,
            "exact_cell_body_precision": cell_p, "exact_cell_body_recall": cell_r,
            "exact_cell_body_f1": 2*cell_p*cell_r/(cell_p+cell_r) if cell_p+cell_r else 0,
            "shape_exact_rate": shape_exact/ref_count if ref_count else 0,
            "exact_grid_rate": exact_grids/ref_count if ref_count else 0, "items": items}
