import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from document_processing.docling_adapter.result_mapper import _get_page_image, _merge_text_layout_elements
from document_processing.docling_adapter.orientation import (
    detect_paddle_orientation,
    preload_paddle_page_orientation_model,
)
from document_processing.docling_adapter.scanned.postprocessing import (
    clean_ocr_elements,
    recover_empty_cell_dashes,
)
from document_processing.docling_adapter.scanned.vietocr import VietOcrModel


class VietOcrPostprocessingTest(unittest.TestCase):
    def test_preload_initializes_cached_page_orientation_model(self):
        with patch("document_processing.docling_adapter.orientation._paddle_orientation_model") as page_model:
            preload_paddle_page_orientation_model()
        page_model.assert_called_once_with()

    def test_vietocr_recognizes_bounded_batches_in_order(self):
        from document_processing.docling_adapter.scanned import vietocr as vietocr_module

        model = VietOcrModel.__new__(VietOcrModel)
        batch_sizes = []

        def predict_batch(images):
            batch_sizes.append(len(images))
            return [f"text-{len(batch_sizes)}-{index}" for index in range(len(images))]

        model.recognizer = SimpleNamespace(predict_batch=predict_batch)
        lines = [np.zeros((4, 8, 3), dtype=np.uint8) for _ in range(
            vietocr_module._VIETOCR_BATCH_SIZE + 2
        )]

        results = model._recognize_lines(lines)

        self.assertEqual(batch_sizes, [vietocr_module._VIETOCR_BATCH_SIZE, 2])
        self.assertEqual([route for _text, route in results], ["default"] * len(lines))
        self.assertEqual(results[0][0], "text-1-0")
        self.assertEqual(results[-1][0], "text-2-1")

    def test_vietocr_batch_recognition_falls_back_to_single_predictions(self):
        model = VietOcrModel.__new__(VietOcrModel)
        model.recognizer = SimpleNamespace(predict=lambda _image: "  recognized  ")
        lines = [np.zeros((4, 8, 3), dtype=np.uint8) for _ in range(2)]

        self.assertEqual(model._recognize_lines(lines), [
            ("recognized", "default"), ("recognized", "default")
        ])

    def test_merges_only_ocr_fragments_inside_raw_text_region(self):
        def element(text, bbox, page=1):
            return {"text": text, "metadata": {"page_number": page, "bbox": bbox,
                    "element_type": "text", "text_extraction_method": "docling.vietocr"}}

        elements = [element("MAR", [22, 2, 48, 12]), element("31", [2, 3, 18, 13]),
                    element("2009", [52, 2, 88, 12]), element("footer", [2, 22, 30, 30]),
                    element("other page", [2, 3, 18, 13], page=2)]
        detections = [{"page_number": 1, "label": "text", "bbox": [0, 0, 100, 16]},
                      {"page_number": 1, "label": "footer", "bbox": [0, 20, 100, 35]}]
        merged = _merge_text_layout_elements(elements, detections)
        self.assertEqual([item["text"] for item in merged], ["31 MAR 2009", "footer", "other page"])
        self.assertEqual(merged[0]["metadata"]["bbox"], [0, 0, 100, 16])

    def test_non_text_region_wins_when_more_specific_and_lines_remain_separate(self):
        def element(text, bbox):
            return {"text": text, "metadata": {"page_number": 1, "bbox": bbox,
                    "element_type": "text", "text_extraction_method": "docling.tesseract"}}

        elements = [element("first", [1, 1, 20, 9]), element("line", [23, 2, 40, 10]),
                    element("second", [1, 15, 22, 23]), element("footer", [1, 30, 20, 38])]
        detections = [{"page_number": 1, "label": "text", "bbox": [0, 0, 100, 40]},
                      {"page_number": 1, "label": "footer", "bbox": [0, 28, 30, 40]}]
        merged = _merge_text_layout_elements(elements, detections)
        self.assertEqual([item["text"] for item in merged], ["first line\nsecond", "footer"])

    def test_paddle_orientation_maps_prediction_to_clockwise_correction(self):
        from PIL import Image

        for angle, correction in ((0, 0), (90, 270), (180, 180), (270, 90)):
            with self.subTest(angle=angle):
                prediction = SimpleNamespace(json={"res": {"label_names": [str(angle)], "scores": [0.9]}})
                model = SimpleNamespace(predict=lambda *_args, **_kwargs: iter([prediction]))
                with patch("document_processing.docling_adapter.orientation._paddle_orientation_model", return_value=model):
                    self.assertEqual(detect_paddle_orientation(Image.new("RGB", (4, 4))), (correction, angle, 0.9))

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



    def test_page_image_loader_uses_preview_when_get_image_is_unavailable(self):
        from PIL import Image

        pil_image = Image.new("RGB", (4, 3), color=(255, 0, 0))
        page = SimpleNamespace(
            image=SimpleNamespace(pil_image=pil_image),
            get_image=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("no rendered image")),
        )
        cache = {}

        image = _get_page_image(page, cache, 1)

        self.assertEqual(image.shape, (3, 4, 3))
        self.assertEqual(image[0, 0].tolist(), [0, 0, 255])
        self.assertIs(cache[1], image)

    def test_repeated_word_ocr_is_removed_only_inside_detected_edge_strip(self):
        image = np.full((100, 100, 3), 255, dtype=np.uint8)
        repeated = "Nghi thi thi thi đị thị đị " + "được " * 16
        elements = [
            {"text": repeated, "metadata": {
                "page_number": 1, "bbox": [0, 0, 8, 100],
                "text_extraction_method": "docling.vietocr",
            }},
            {"text": repeated, "metadata": {
                "page_number": 1, "bbox": [30, 20, 90, 30],
                "text_extraction_method": "docling.vietocr",
            }},
        ]
        with patch(
            "document_processing.docling_adapter.scanned.postprocessing.detect_repeated_edge_strips",
            return_value=[[0.0, 0.0, 0.1, 1.0]],
        ):
            cleaned, diagnostics = clean_ocr_elements(
                elements, [], {1: image}, {1: (100, 100)}, "vietocr"
            )

        self.assertEqual(cleaned, [elements[1]])
        self.assertEqual(diagnostics[0]["reason"], "repeated_edge_artifact")

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
