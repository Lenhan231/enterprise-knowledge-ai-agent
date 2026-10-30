import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from document_processing.docling_adapter.scanned.postprocessing import (
    clean_ocr_elements,
    recover_empty_cell_dashes,
)
from document_processing.docling_adapter.scanned.vietocr import VietOcrModel


class VietOcrPostprocessingTest(unittest.TestCase):
    @staticmethod
    def _cell(text, box):
        left, top, right, bottom = box
        return SimpleNamespace(
            text=text,
            rect=SimpleNamespace(
                r_x0=left, r_y0=top, r_x1=right, r_y1=top,
                r_x2=right, r_y2=bottom, r_x3=left, r_y3=bottom,
            ),
        )

    def test_deduplicates_same_line_only_across_overlapping_regions(self):
        first = self._cell("Báo cáo", [10, 10, 70, 20])
        duplicate = self._cell("  BÁO   CÁO ", [11, 10, 71, 20])
        same_region = self._cell("Báo cáo", [10, 10, 70, 20])
        result = VietOcrModel._deduplicate_overlapping_cells(
            [first, duplicate, same_region], [1, 2, 1]
        )
        self.assertEqual(result, [first, same_region])

    def test_dash_fallback_fills_only_an_empty_single_cell_with_visible_dash(self):
        cells = []
        for row, y in enumerate((10, 30)):
            for column, x in enumerate((10, 50)):
                cells.append(SimpleNamespace(
                    text="" if (row, column) == (1, 1) else "x",
                    start_row_offset_idx=row,
                    start_col_offset_idx=column,
                    row_span=1,
                    col_span=1,
                    bbox=SimpleNamespace(l=x, t=y, r=x + 40, b=y + 10, coord_origin="TOPLEFT"),
                ))
        image = np.full((100, 100, 3), 255, dtype=np.uint8)
        image[34, 75:83] = 0
        grid = [["x", "x"], ["x", ""]]

        recovered = recover_empty_cell_dashes(cells, grid, image, 100, 100)

        self.assertEqual(recovered, [[1, 1]])
        self.assertEqual(grid[1][1], "-")

    def test_cleanup_removes_long_separator_but_keeps_table_content(self):
        image = np.full((100, 100, 3), 255, dtype=np.uint8)
        elements = [
            {"text": "- - - - - - - - -", "metadata": {
                "page_number": 1, "bbox": [10, 10, 60, 15],
                "text_extraction_method": "docling.vietocr",
            }},
            {"text": "- - - - - - - - -", "metadata": {
                "page_number": 1, "bbox": [10, 30, 60, 35],
                "text_extraction_method": "docling.vietocr",
            }},
        ]
        tables = [{"page_number": 1, "metadata": {"bbox": [5, 25, 70, 40]}}]

        cleaned, diagnostics = clean_ocr_elements(
            elements, tables, {1: image}, {1: (100, 100)}, "vietocr"
        )

        self.assertEqual([item["text"] for item in cleaned], [elements[1]["text"]])
        self.assertEqual(diagnostics[0]["reason"], "long_separator_outside_table")


if __name__ == "__main__":
    unittest.main()
