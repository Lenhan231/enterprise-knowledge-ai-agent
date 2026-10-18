"""Native-text and OCR-word-box table reconstruction for PDFs."""

from __future__ import annotations

import logging
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple

from .scanned.table_recovery import ScannedTableExtractor


logger = logging.getLogger(__name__)


class PDFTableExtractor:
    """Extract structured PDF tables while preserving the original coordinates."""

    @staticmethod
    def _extract_page_tables(
        page, page_number: int, ocr_words=None, ocr_metadata=None, ocr_page_rect=None,
    ) -> List[Dict[str, Any]]:
        """Return detected page tables as column names and row dictionaries."""
        words = page.get_text("words")
        numeric_rows: Dict[float, List[Tuple[float, float]]] = {}
        for word in words:
            x0, y0, x1, y1, value = word[:5]
            value = str(value).strip().replace("−", "-")
            if re.fullmatch(r"(?:\(?[-+]?\d[\d.,]*\)?|[-–—])%?", value):
                numeric_rows.setdefault(round((y0 + y1) / 2, 1), []).append((x0, x1))
        aligned_rows = sum(
            any(right[0] - left[1] >= 40 for left, right in zip(sorted(row), sorted(row)[1:]))
            for row in numeric_rows.values()
        )
        line_starts: Dict[Tuple[int, int], float] = {}
        for word in words:
            line_id = (
                (int(word[5]), int(word[6]))
                if len(word) >= 7
                else (0, round((float(word[1]) + float(word[3])) / 2))
            )
            line_starts[line_id] = min(line_starts.get(line_id, float("inf")), float(word[0]))
        start_clusters: List[List[float]] = []
        for start in sorted(line_starts.values()):
            if not start_clusters or start - start_clusters[-1][-1] > 18:
                start_clusters.append([start])
            else:
                start_clusters[-1].append(start)
        repeated_text_columns = sum(len(cluster) >= 3 for cluster in start_clusters)
        # find_tables is costly on long born-digital reports. Only run it on
        # pages with repeated numeric or text columns; scanned-page OCR has its
        # own word-box path below.
        if aligned_rows < 3 and repeated_text_columns < 3 and not ocr_words:
            return []
        try:
            found_tables = page.find_tables().tables
        except Exception as e:
            logger.warning("Table detection failed on page %d: %s", page_number, e)
            return []

        extracted = []
        for table_index, table in enumerate(found_tables):
            matrix = table.extract()
            if not matrix:
                continue

            width = max((len(row) for row in matrix), default=0)
            header = getattr(table, "header", None)
            header_names = getattr(header, "names", None) or []
            columns = [str(name).strip() for name in header_names]
            columns = [name or f"column_{i + 1}" for i, name in enumerate(columns)]
            if len(columns) < width:
                columns.extend(
                    f"column_{i + 1}" for i in range(len(columns), width)
                )

            if not columns:
                columns = [f"column_{i + 1}" for i in range(width)]
                data_rows = matrix
            else:
                data_rows = matrix if getattr(header, "external", False) else matrix[1:]

            # PyMuPDF can mistake slide labels, screenshot footers, and aligned
            # prose for tables. The text/OCR table paths also require at least
            # three populated rows; apply the same floor here so weak native
            # candidates do not block OCR fallback or become empty table records.
            populated_rows = sum(
                sum(value is not None and bool(str(value).strip()) for value in row) >= 2
                for row in data_rows
            )
            if populated_rows < 3:
                continue

            table_context = {}
            header_cells = getattr(header, "cells", None) or (
                getattr(getattr(table, "rows", [None])[0], "cells", None)
                if getattr(table, "rows", None) else None
            )
            table_bbox = getattr(table, "bbox", None)
            first_header_cell = next((cell for cell in header_cells or [] if cell), None)
            merged_title_row = (
                len(columns) > 1
                and len(matrix) > 2
                and len([name for name in header_names if name]) == 1
                and first_header_cell is not None
                and table_bbox is not None
                and abs(first_header_cell[0] - table_bbox[0]) <= 1
                and abs(first_header_cell[2] - table_bbox[2]) <= 1
                and sum(bool(value and str(value).strip()) for value in matrix[1]) >= 2
            )
            if merged_title_row:
                title = str(header_names[0]).strip()
                subheaders = list(matrix[1]) + [None] * max(0, width - len(matrix[1]))
                rows = getattr(table, "rows", [])
                subheader_cells = getattr(rows[1], "cells", []) if len(rows) > 1 else []
                data_cells = getattr(rows[2], "cells", []) if len(rows) > 2 else []
                columns = []
                for column_index in range(width):
                    label = str(subheaders[column_index] or "").strip()
                    if not label and column_index < len(data_cells) and data_cells[column_index]:
                        target = data_cells[column_index]
                        label = next((
                            str(subheaders[parent_index]).strip()
                            for parent_index in range(column_index - 1, -1, -1)
                            if parent_index < len(subheader_cells)
                            and subheader_cells[parent_index]
                            and str(subheaders[parent_index] or "").strip()
                            and subheader_cells[parent_index][0] <= target[0] + 1
                            and subheader_cells[parent_index][2] >= target[2] - 1
                        ), "")
                    label = label or f"column_{column_index + 1}"
                    duplicate_number = 2
                    unique_label = label
                    while unique_label in columns:
                        unique_label = f"{label} ({duplicate_number})"
                        duplicate_number += 1
                    columns.append(unique_label)
                table_context["table_title"] = title
                data_rows = []
                for row_index, row in enumerate(matrix[2:], start=2):
                    values = [str(value).strip() for value in row if value and str(value).strip()]
                    row_cells = getattr(rows[row_index], "cells", []) if row_index < len(rows) else []
                    full_width_note = len(values) == 1 and any(
                        cell
                        and abs(cell[0] - table_bbox[0]) <= 1
                        and abs(cell[2] - table_bbox[2]) <= 1
                        for cell in row_cells
                    )
                    if full_width_note:
                        table_context.setdefault("notes", []).extend(values)
                    else:
                        data_rows.append(row)

            rows = []
            for row in data_rows:
                values = list(row) + [None] * max(0, len(columns) - len(row))
                rows.append(dict(zip(columns, values)))

            extracted.append({
                "page_number": page_number,
                "table_index": table_index,
                "columns": columns,
                "rows": rows,
                **({"context": table_context} if table_context else {}),
                "metadata": {
                    "element_type": "table",
                    "layout_type": "table",
                    "table_extraction_method": "pymupdf.find_tables",
                },
            })
        if not extracted:
            if aligned_rows >= 3:
                try:
                    text_tables = page.find_tables(strategy="text").tables
                except Exception as e:
                    logger.warning("Text-based table detection failed on page %d: %s", page_number, e)
                else:
                    for table in text_tables:
                        extracted.extend(
                            PDFTableExtractor._split_aligned_text_table(
                                table, page, page_number, len(extracted), words,
                            )
                        )
        if not extracted:
            try:
                text_tables = page.find_tables(strategy="text").tables
            except Exception as e:
                logger.warning("Text-based table detection failed on page %d: %s", page_number, e)
            else:
                for table in text_tables:
                    extracted.extend(
                        PDFTableExtractor._split_aligned_text_table(
                            table, page, page_number, len(extracted), words,
                        )
                    )
        if not extracted and ocr_words:
            extracted = ScannedTableExtractor._tables_from_aligned_words(
                ocr_words, ocr_page_rect or page.rect, page_number, ocr_metadata=ocr_metadata,
            )
        return extracted

    _tables_from_aligned_words = staticmethod(ScannedTableExtractor._tables_from_aligned_words)
    _ocr_text_column_headers = staticmethod(ScannedTableExtractor._ocr_text_column_headers)
    _ocr_period_header = staticmethod(ScannedTableExtractor._ocr_period_header)

    @staticmethod
    def _split_aligned_text_table(
        table, page, page_number: int, first_index: int, words=None,
    ) -> List[Dict[str, Any]]:
        """Rebuild borderless numeric tables from text grids."""
        matrix = table.extract()
        if not matrix:
            return []
        width = max((len(row) for row in matrix), default=0)
        if width < 3:
            return []
        matrix = [list(row) + [None] * (width - len(row)) for row in matrix]
        cells = getattr(table, "cells", [])
        if len(cells) != width * len(matrix):
            return []
        words = words if words is not None else page.get_text("words")

        def is_number(value: Any) -> bool:
            text = str(value or "").strip().replace("−", "-")
            return bool(re.fullmatch(r"(?:\(?[-+]?\d[\d.,]*\)?|[-–—])%?", text))

        numeric_columns = [
            column for column in range(width)
            if sum(is_number(row[column]) for row in matrix) >= 3
        ]
        groups: List[List[int]] = []
        for column in numeric_columns:
            if groups and column - groups[-1][-1] <= 2:
                groups[-1].append(column)
            else:
                groups.append([column])
        groups = [group for group in groups if len(group) >= 2]
        if not groups:
            return []

        result = []
        for group_index, numeric_group in enumerate(groups):
            previous_end = groups[group_index - 1][-1] + 1 if group_index else 0
            previous_numeric = groups[group_index - 1][-1] if group_index else None
            rows = []
            row_indices = []
            for row_index, matrix_row in enumerate(matrix):
                values = [matrix_row[column] for column in numeric_group]
                if sum(is_number(value) for value in values) < 2:
                    continue
                first_cell = cells[numeric_group[0] * len(matrix) + row_index]
                if not first_cell:
                    continue
                left = (
                    cells[previous_numeric * len(matrix) + row_index][2]
                    if previous_numeric is not None
                    and cells[previous_numeric * len(matrix) + row_index]
                    else table.bbox[0]
                )
                right = first_cell[0]
                center_y = (first_cell[1] + first_cell[3]) / 2
                label_words = [
                    word for word in words
                    if left - 1 <= word[0] and word[2] <= right + 1
                    and abs((word[1] + word[3]) / 2 - center_y) <= 4
                ]
                label = " ".join(word[4] for word in sorted(label_words, key=lambda word: word[0]))
                if not label:
                    continue
                rows.append([label, *values])
                row_indices.append(row_index)
            if len(rows) < 3:
                continue

            value_columns = []
            for value_index, column in enumerate(numeric_group, start=1):
                header = next((
                    str(row[column]).strip()
                    for row in matrix
                    if row[column] is not None
                    and re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", str(row[column]).strip())
                ), f"value_{value_index}")
                value_columns.append(header)
            columns = ["label", *value_columns]
            records = [dict(zip(columns, row)) for row in rows]
            label_cell = cells[previous_end * len(matrix) + row_indices[0]]
            last_value_cell = cells[numeric_group[-1] * len(matrix) + row_indices[-1]]
            bbox = (
                label_cell[0],
                cells[numeric_group[0] * len(matrix) + row_indices[0]][1],
                last_value_cell[2],
                last_value_cell[3],
            ) if label_cell and last_value_cell else table.bbox
            result.append({
                "page_number": page_number,
                "table_index": first_index + len(result),
                "columns": columns,
                "rows": records,
                "metadata": {
                    "element_type": "table",
                    "layout_type": "table",
                    "table_extraction_method": "pymupdf.find_tables_text_aligned_columns",
                    "table_detection_strategy": "text",
                    "numeric_columns": numeric_group,
                    "bbox": bbox,
                    "bbox_coordinate_system": "pdf_points",
                },
            })
        return result
