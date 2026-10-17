"""PDF table caption, coordinate, and continuation processing."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import fitz

from core.document_processing.processors.pdf.scanned.ocr import PDFOCRProcessor


class PDFTableProcessor:
    """Recover table captions, coordinates, and page continuations."""

    @staticmethod
    def _extract_table_title(page, table: Dict[str, Any], ocr_words=None) -> Optional[str]:
        """Find an explicit table/report caption immediately above its detected bounds."""
        bbox = table.get("metadata", {}).get("bbox")
        if not bbox:
            return None
        table_top = fitz.Rect(bbox).y0
        caption_terms = (
            "bảng", "báo cáo", "balance sheet", "financial position",
            "income statement", "statement of", "results of operations",
        )
        candidates = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                text = " ".join("".join(
                    span.get("text", "") for span in line.get("spans", [])
                ).split())
                if not text or len(text) > 140:
                    continue
                line_rect = fitz.Rect(line.get("bbox", [0, 0, 0, 0]))
                gap = table_top - line_rect.y1
                if 0 <= gap <= 100 and any(term in text.casefold() for term in caption_terms):
                    candidates.append((gap, text))
        native_title = min(candidates, default=(None, None), key=lambda candidate: candidate[0])[1]
        if native_title or not ocr_words:
            return native_title

        header_bbox = table.get("metadata", {}).get("ocr_column_header_bbox")
        if not header_bbox:
            return None
        header_top = fitz.Rect(header_bbox).y0
        lines: Dict[Tuple[int, int], List[Tuple[float, float, float, float, str]]] = {}
        for word in ocr_words:
            lines.setdefault((word[5], word[6]), []).append(word)
        ocr_candidates = []
        for words in lines.values():
            words.sort(key=lambda word: word[0])
            text = " ".join(str(word[4]).strip() for word in words).strip()
            if not 2 <= len(text) <= 120 or text.endswith((".", ";", ",")):
                continue
            line_bottom = max(word[3] for word in words)
            gap = header_top - line_bottom
            if 0 < gap <= 120:
                ocr_candidates.append((gap, text))
        return min(ocr_candidates, default=(None, None), key=lambda item: item[0])[1]

    @staticmethod
    def _restore_table_coordinates(
        table: Dict[str, Any], page_rect, clockwise_degrees: int,
        deskew_correction_degrees: float = 0.0,
    ) -> None:
        """Map OCR boxes from the corrected raster back to the source PDF page."""
        metadata = table.get("metadata", {})
        oriented_rect = PDFOCRProcessor._oriented_page_rect(page_rect, clockwise_degrees)

        def restore(box):
            if not box or len(box) != 4:
                return box
            x0, y0, x1, y1 = map(float, box)
            if deskew_correction_degrees:
                angle = math.radians(deskew_correction_degrees)
                cosine, sine = math.cos(angle), math.sin(angle)
                center_x = oriented_rect.x0 + oriented_rect.width / 2
                center_y = oriented_rect.y0 + oriented_rect.height / 2
                points = []
                for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
                    dx, dy = x - center_x, y - center_y
                    points.append((
                        center_x + cosine * dx - sine * dy,
                        center_y + sine * dx + cosine * dy,
                    ))
                x0 = max(oriented_rect.x0, min(point[0] for point in points))
                x1 = min(oriented_rect.x1, max(point[0] for point in points))
                y0 = max(oriented_rect.y0, min(point[1] for point in points))
                y1 = min(oriented_rect.y1, max(point[1] for point in points))
            if clockwise_degrees == 90:
                points = ((page_rect.width - y, x) for x in (x0, x1) for y in (y0, y1))
            elif clockwise_degrees == 180:
                points = ((page_rect.width - x, page_rect.height - y) for x in (x0, x1) for y in (y0, y1))
            elif clockwise_degrees == 270:
                points = ((y, page_rect.height - x) for x in (x0, x1) for y in (y0, y1))
            else:
                return box
            xs, ys = zip(*points)
            return [
                max(page_rect.x0, min(page_rect.x1, page_rect.x0 + min(xs))),
                max(page_rect.y0, min(page_rect.y1, page_rect.y0 + min(ys))),
                max(page_rect.x0, min(page_rect.x1, page_rect.x0 + max(xs))),
                max(page_rect.y0, min(page_rect.y1, page_rect.y0 + max(ys))),
            ]

        metadata["bbox"] = restore(metadata.get("bbox"))
        if metadata.get("ocr_column_header_bbox"):
            metadata["ocr_column_header_bbox"] = restore(metadata["ocr_column_header_bbox"])
        for row in metadata.get("row_cell_bboxes", []):
            for column, box in row.items():
                if box:
                    row[column] = restore(box)

    @staticmethod
    def _link_continued_tables(tables: List[Dict[str, Any]], pdf_document) -> None:
        """Link unambiguous page-edge table segments without merging their provenance."""
        by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for table in tables:
            by_page[int(table.get("page_number") or 0)].append(table)

        for page_number in sorted(by_page):
            previous_tables = by_page.get(page_number - 1, [])
            current_tables = by_page[page_number]
            if not previous_tables:
                continue
            previous_rect = pdf_document[page_number - 2].rect
            current_rect = pdf_document[page_number - 1].rect
            matches = []
            for previous in previous_tables:
                previous_columns = tuple(
                    " ".join(str(column).casefold().split())
                    for column in previous.get("columns", [])
                )
                previous_bbox = (previous.get("metadata") or {}).get("bbox")
                if not previous_columns or not previous_bbox or previous_bbox[3] < previous_rect.y0 + previous_rect.height * 0.75:
                    continue
                previous_title = str((previous.get("context") or {}).get("table_title") or "").strip().casefold()
                for current in current_tables:
                    current_columns = tuple(
                        " ".join(str(column).casefold().split())
                        for column in current.get("columns", [])
                    )
                    current_bbox = (current.get("metadata") or {}).get("bbox")
                    if current_columns != previous_columns or not current_bbox:
                        continue
                    if current_bbox[1] > current_rect.y0 + current_rect.height * 0.25:
                        continue
                    current_title = str((current.get("context") or {}).get("table_title") or "").strip().casefold()
                    if previous_title and current_title and previous_title != current_title:
                        continue
                    matches.append((previous, current))

            if len(matches) != 1:
                continue
            previous, current = matches[0]
            previous_metadata = previous.setdefault("metadata", {})
            current_metadata = current.setdefault("metadata", {})
            group_id = previous_metadata.get("continuation_group_id") or (
                f"page:{page_number - 1}:table:{previous.get('table_index', 0)}"
            )
            previous_metadata.update({
                "continuation_group_id": group_id,
                "continued_to_page": page_number,
            })
            current_metadata.update({
                "continuation_group_id": group_id,
                "continued_from_page": page_number - 1,
            })
            previous_context = previous.setdefault("context", {})
            current_context = current.setdefault("context", {})
            inherited_title = previous_context.get("table_title") or current_context.get("table_title")
            if inherited_title:
                previous_context.setdefault("table_title", inherited_title)
                current_context.setdefault("table_title", inherited_title)
