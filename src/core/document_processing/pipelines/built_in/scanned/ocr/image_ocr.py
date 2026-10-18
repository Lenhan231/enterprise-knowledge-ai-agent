"""Shared OCR operations for image bytes and rendered document pages."""

from __future__ import annotations

import csv
import logging
import re
import subprocess
from typing import Any

from .tesseract import run_tesseract

logger = logging.getLogger(__name__)


def recognize_image_text(
    image_bytes: bytes,
    config: dict[str, Any],
    *,
    page_segmentation_mode: int,
    language: str | None = None,
    timeout: int = 90,
    tessdata_dir=None,
    include_config: bool = True,
) -> str:
    """Recognize text from image bytes using the configured Tesseract engine."""
    return run_tesseract(
        image_bytes, config,
        language=language,
        page_segmentation_mode=page_segmentation_mode,
        timeout=timeout,
        tessdata_dir=tessdata_dir,
        include_config=include_config,
    ).strip()


def looks_like_numeric_table(text: str) -> bool:
    """Detect likely numeric tables in OCR text, including one-cell-per-line output."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    numeric_cell = re.compile(r"(?:[-+]?\d[\d.,]*|[-–—])")
    multi_value_rows = sum(len(numeric_cell.findall(line)) >= 2 for line in lines)
    split_cell_rows = sum(bool(numeric_cell.fullmatch(line)) for line in lines)
    return multi_value_rows >= 3 or split_cell_rows >= 8


def words_to_text(words) -> str:
    """Rebuild lines from Tesseract word boxes."""
    lines = {}
    for word in words:
        lines.setdefault((word[5], word[6]), []).append(word)
    return "\n".join(
        " ".join(item[4] for item in sorted(line, key=lambda item: (item[0], item[7])))
        for _, line in sorted(lines.items())
    )


def exclude_table_words(words, tables):
    """Remove OCR words whose centers lie inside extracted table/header boxes."""
    boxes = []
    for table in tables:
        metadata = table.get("metadata") or {}
        boxes.extend(
            box for box in (metadata.get("bbox"), metadata.get("ocr_column_header_bbox"))
            if isinstance(box, (list, tuple)) and len(box) == 4
        )
    if not boxes:
        return list(words)
    return [
        word for word in words
        if not any(
            box[0] <= (word[0] + word[2]) / 2 <= box[2]
            and box[1] <= (word[1] + word[3]) / 2 <= box[3]
            for box in boxes
        )
    ]


def recognize_image_words(
    image_bytes: bytes,
    config: dict[str, Any],
    *,
    page_segmentation_mode: int,
    image_size: tuple[int, int],
    coordinate_rect: tuple[float, float, float, float],
    tessdata_dir=None,
    timeout: int = 90,
):
    """Return Tesseract TSV word boxes mapped into caller-provided coordinates."""
    try:
        output = run_tesseract(
            image_bytes, config,
            page_segmentation_mode=page_segmentation_mode,
            timeout=timeout,
            output_format="tsv",
            tessdata_dir=tessdata_dir,
        )
        image_width, image_height = image_size
        x0, y0, x1, y1 = coordinate_rect
        scale_x = image_width / (x1 - x0)
        scale_y = image_height / (y1 - y0)
        words = []
        for row in csv.DictReader(output.splitlines(), delimiter="\t"):
            if row.get("level") != "5" or not row.get("text", "").strip():
                continue
            left, top = int(row["left"]), int(row["top"])
            right = left + int(row["width"])
            bottom = top + int(row["height"])
            words.append((
                x0 + left / scale_x,
                y0 + top / scale_y,
                x0 + right / scale_x,
                y0 + bottom / scale_y,
                row["text"],
                int(row["block_num"]),
                int(row["line_num"]),
                int(row["word_num"]),
                float(row.get("conf") or -1),
            ))
        return words
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        logger.warning("Tesseract word-box extraction failed: %s", error)
        return []
