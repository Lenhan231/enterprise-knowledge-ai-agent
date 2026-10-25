"""Full-page OCR transcript scoring for normalized page predictions."""

from __future__ import annotations

import re
import unicodedata

from metrics import page_key
from metrics.iou_metrics import iou
from metrics.text_metrics import character_error_count, token_error_count


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).casefold()).strip()


def rotate_box_for_reading(box: list[float], clockwise: int) -> list[float]:
    left, top, right, bottom = box
    if clockwise == 90:
        return [1 - bottom, left, 1 - top, right]
    if clockwise == 180:
        return [1 - right, 1 - bottom, 1 - left, 1 - top]
    if clockwise == 270:
        return [top, 1 - right, bottom, 1 - left]
    return box


def score_ocr(
    references: list[dict], predictions: dict,
    reading_order_rotations: dict[tuple[str, int], int] | None = None,
    iou_threshold: float = 0.5,
) -> dict:
    from pyvi import ViTokenizer

    char_edits = ref_chars = word_edits = ref_words = whitespace_edits = ref_syllables = 0
    page_scores = []
    for reference in references:
        page_id = page_key(reference)
        prediction = predictions[page_id]
        predicted_tables = prediction.get("tables", [])
        blocks = []
        for element in prediction.get("elements", []):
            text, box = str(element.get("text", "")).strip(), element.get("bbox_norm")
            if not text or not box or any(iou(box, table["bbox_norm"]) > iou_threshold for table in predicted_tables):
                continue
            blocks.append((box, text))
        for table in predicted_tables:
            serialized = "\n".join([" | ".join(table.get("columns", []))] + [" | ".join(row) for row in table.get("rows", [])])
            if serialized.strip():
                blocks.append((table["bbox_norm"], serialized))
        rotation = (reading_order_rotations or {}).get(page_id, 0)
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
        page_scores.append({"document_id": page_id[0], "source_page_number_1based": page_id[1], "text_order_rotation_clockwise": rotation, "cer": ce / nc if nc else None, "wer_pyvi": we / nw if nw else None, "whitespace_error": se / ns if ns else None})
    return {"pages": len(references), "micro_cer": char_edits / ref_chars if ref_chars else None,
            "micro_wer_pyvi": word_edits / ref_words if ref_words else None,
            "micro_whitespace_error": whitespace_edits / ref_syllables if ref_syllables else None,
            "character_edits": char_edits, "reference_characters": ref_chars,
            "word_edits": word_edits, "reference_words": ref_words, "page_scores": page_scores}
