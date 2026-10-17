"""Reconstruct scanned tables from OCR word boxes."""

from __future__ import annotations

import re
import statistics
from typing import Any, Dict, List, Optional


class ScannedTableExtractor:
    """Recover aligned rows and columns from OCR word coordinates."""

    @staticmethod
    def _tables_from_aligned_words(
        words, page_rect, page_number: int, ocr_metadata=None,
    ) -> List[Dict[str, Any]]:
        """Build borderless scanned tables from OCR word boxes and repeated values."""
        def is_number(value: str) -> bool:
            value = str(value or "").strip().replace("−", "-")
            return bool(re.fullmatch(r"(?:\(?[-+]?\d[\d.,]*\)?|[-–—])%?", value))

        ordered = sorted(words, key=lambda word: ((word[1] + word[3]) / 2, word[0]))
        row_groups = []
        for word in ordered:
            center_y = (word[1] + word[3]) / 2
            # Mild page skew shifts cells in one visual row by several PDF points.
            if not row_groups or abs(center_y - row_groups[-1][0]) > 10:
                row_groups.append([center_y, [word]])
            else:
                center, row = row_groups[-1]
                row.append(word)
                row_groups[-1][0] = sum((item[1] + item[3]) / 2 for item in row) / len(row)
        candidates = []
        for center_y, row in row_groups:
            numeric = [word for word in row if is_number(word[4])]
            numeric.sort(key=lambda word: word[0])
            has_measured_value = any(any(character.isdigit() for character in word[4]) for word in numeric)
            if has_measured_value and len(numeric) >= 2 and any(
                right[0] - left[2] >= 40 for left, right in zip(numeric, numeric[1:])
            ):
                candidates.append((center_y, sorted(row, key=lambda word: word[0]), numeric))
        if len(candidates) < 3:
            return []

        alignments = []
        for edge_index in (0, 2):
            edges = sorted(word[edge_index] for _, _, numeric in candidates for word in numeric)
            edge_clusters = []
            for edge in edges:
                if not edge_clusters or edge - edge_clusters[-1][-1] > 15:
                    edge_clusters.append([edge])
                else:
                    edge_clusters[-1].append(edge)
            supported = [cluster for cluster in edge_clusters if len(cluster) >= 3]
            if len(supported) >= 2:
                max_support = max(map(len, supported))
                frequent_columns = [
                    cluster for cluster in supported
                    if len(cluster) >= max(3, max_support * 0.5)
                ]
                if len(frequent_columns) >= 2:
                    supported = frequent_columns
                # Judge each numeric column against labels on its own rows.
                # A single page-wide boundary drops the left-hand table when
                # two financial statements are printed side by side.
                amount_columns = []
                for cluster in supported:
                    edge = sum(cluster) / len(cluster)
                    matched_rows = label_rows = 0
                    for _, row, numeric in candidates:
                        word = min(numeric, key=lambda item: abs(item[edge_index] - edge))
                        if abs(word[edge_index] - edge) > 18:
                            continue
                        matched_rows += 1
                        preceding_labels = [
                            item[2] for item in row
                            if not is_number(item[4]) and item[2] <= word[0]
                        ]
                        if (
                            preceding_labels
                            and word[0] - max(preceding_labels) >= max(8, page_rect.width * 0.02)
                        ):
                            label_rows += 1
                    if matched_rows and label_rows / matched_rows >= 0.5:
                        amount_columns.append(cluster)
                if len(amount_columns) >= 2:
                    supported = amount_columns
                spread = sum(cluster[-1] - cluster[0] for cluster in supported)
                alignments.append((
                    sum(map(len, supported)), -spread, edge_index,
                    [sum(cluster) / len(cluster) for cluster in supported],
                ))
        if not alignments:
            return []
        _, _, alignment_edge, columns = max(alignments)
        gaps = [right - left for left, right in zip(columns, columns[1:])]
        typical_gap = statistics.median(gaps) if gaps else 0
        split_gap = max(page_rect.width * 0.15, typical_gap * 2.5)
        column_groups = []
        for column in columns:
            if column_groups and column - column_groups[-1][-1] <= split_gap:
                column_groups[-1].append(column)
            else:
                column_groups.append([column])
        column_groups = [group for group in column_groups if len(group) >= 2]
        if not column_groups:
            return []

        result = []
        for group_index, column_group in enumerate(column_groups):
            previous_right = column_groups[group_index - 1][-1] if group_index else page_rect.x0
            rows, row_boxes, row_cell_boxes = [], [], []
            table_headers = None
            aligned_candidates = []
            for center_y, row, numeric in candidates:
                aligned = [
                    min(numeric, key=lambda word: abs(word[alignment_edge] - edge))
                    for edge in column_group
                ]
                aligned = [
                    word if abs(word[alignment_edge] - edge) <= 18 else None
                    for word, edge in zip(aligned, column_group)
                ]
                if sum(word is not None for word in aligned) >= 2:
                    aligned_candidates.append((center_y, aligned, row))
            first_data_y = min((center_y for center_y, _, _ in aligned_candidates), default=0)
            centers = [
                statistics.mean(
                    (word[0] + word[2]) / 2
                    for _, aligned, _ in aligned_candidates
                    if (word := aligned[index]) is not None
                )
                for index in range(len(column_group))
            ]
            label_centers = []
            for _, aligned, row in aligned_candidates:
                first_value = next((word for word in aligned if word is not None), None)
                label_words = [
                    word for word in row
                    if first_value and word[2] <= first_value[0] and not is_number(word[4])
                ]
                if label_words:
                    label_centers.append(
                        (min(word[0] for word in label_words) + max(word[2] for word in label_words)) / 2
                    )
            label_center = statistics.median(label_centers) if label_centers else centers[0] - (
                centers[1] - centers[0]
            )
            text_headers, text_header_bbox = ScannedTableExtractor._ocr_text_column_headers(
                row_groups, centers, first_data_y, label_center,
            )
            for center_y, row, numeric in candidates:
                aligned = []
                for edge in column_group:
                    match = min(numeric, key=lambda word: abs(word[alignment_edge] - edge))
                    aligned.append(match if abs(match[alignment_edge] - edge) <= 18 else None)
                if sum(word is not None for word in aligned) < 2:
                    continue
                period_headers = [
                    ScannedTableExtractor._ocr_period_header(word[4]) if word else None
                    for word in aligned
                ]
                if len(period_headers) >= 2 and all(period_headers):
                    table_headers = period_headers
                    row_boxes.extend(word for word in aligned if word is not None)
                    continue
                first_value = next(word for word in aligned if word is not None)
                lower = previous_right + 3 if group_index else page_rect.x0
                label_words = [
                    word for word in row
                    if word[0] >= lower and word[2] <= first_value[0]
                    and not is_number(word[4])
                ]
                label = " ".join(word[4] for word in label_words).strip()
                if not label:
                    continue
                value_words = [word[4] if word is not None else "" for word in aligned]
                rows.append([label, *value_words])
                row_boxes.extend(label_words)
                row_boxes.extend(word for word in aligned if word is not None)
                row_cell_boxes.append([
                    (
                        min(word[0] for word in label_words),
                        min(word[1] for word in label_words),
                        max(word[2] for word in label_words),
                        max(word[3] for word in label_words),
                    ),
                    *[tuple(word[:4]) if word is not None else None for word in aligned],
                ])
            if len(rows) < 3:
                continue
            headers = table_headers or (text_headers[1:] if text_headers else None) or [
                f"value_{index}" for index in range(1, len(column_group) + 1)
            ]
            columns_out = [
                text_headers[0] if text_headers and text_headers[0] else "label",
                *headers,
            ]
            cells_with_boxes = [
                dict(zip(columns_out, [list(box) if box is not None else None for box in boxes]))
                for boxes in row_cell_boxes
            ]
            result.append({
                "page_number": page_number,
                "table_index": len(result),
                "columns": columns_out,
                "rows": [dict(zip(columns_out, row)) for row in rows],
                "metadata": {
                    "element_type": "table",
                    "layout_type": "table",
                    "table_extraction_method": "tesseract.tsv_aligned_columns",
                    "table_detection_strategy": "ocr_word_boxes",
                    **({"ocr": ocr_metadata} if ocr_metadata else {}),
                    "column_alignment": "left" if alignment_edge == 0 else "right",
                    "bbox": (
                        min(word[0] for word in row_boxes),
                        min(word[1] for word in row_boxes),
                        max(word[2] for word in row_boxes),
                        max(word[3] for word in row_boxes),
                    ),
                    "bbox_coordinate_system": "pdf_points",
                    "row_cell_bboxes": cells_with_boxes,
                    **({"ocr_column_header_bbox": text_header_bbox} if text_header_bbox else {}),
                },
            })
        return result

    @staticmethod
    def _ocr_text_column_headers(row_groups, column_centers, first_data_y, label_center):
        """Map the nearest OCR text row above aligned values into table columns."""
        if len(column_centers) < 2 or not first_data_y:
            return None, None
        boundaries = [(label_center + column_centers[0]) / 2]
        boundaries.extend(
            (left + right) / 2 for left, right in zip(column_centers, column_centers[1:])
        )
        candidates = []
        for center_y, row in row_groups:
            gap = first_data_y - center_y
            if not 0 < gap <= 100:
                continue
            text_words = [
                word for word in row
                if not re.fullmatch(r"(?:\(?[-+]?\d[\d.,]*\)?|[-–—])%?", str(word[4]).strip())
            ]
            if len(text_words) < 2:
                continue
            cells = [[] for _ in range(len(column_centers) + 1)]
            for word in sorted(text_words, key=lambda item: item[0]):
                x_center = (word[0] + word[2]) / 2
                column_index = sum(x_center >= boundary for boundary in boundaries)
                cells[column_index].append(word[4])
            populated_values = sum(bool(cell) for cell in cells[1:])
            if populated_values >= 2:
                candidates.append((gap, [" ".join(cell).strip() for cell in cells], row))
        if not candidates:
            return None, None
        _, headers, header_words = min(candidates, key=lambda candidate: candidate[0])
        headers = [re.sub(r"\s+", " ", header) for header in headers]
        if len({header.casefold() for header in headers[1:] if header}) < 2:
            return None, None
        # Preserve the generic schema when OCR only recovers some headings.
        return (
            [header or ("label" if index == 0 else f"value_{index}")
             for index, header in enumerate(headers)],
            (
                min(word[0] for word in header_words),
                min(word[1] for word in header_words),
                max(word[2] for word in header_words),
                max(word[3] for word in header_words),
            ),
        )

    @staticmethod
    def _ocr_period_header(value: str) -> Optional[str]:
        """Normalize OCR'd day/month/year or standalone year table headers."""
        digits = re.sub(r"\D", "", str(value or ""))
        if len(digits) == 4 and 1900 <= int(digits) <= 2100:
            return digits
        if len(digits) == 8:
            day, month, year = int(digits[:2]), int(digits[2:4]), int(digits[4:])
            if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
                return f"{day:02d}/{month:02d}/{year}"
        return None
