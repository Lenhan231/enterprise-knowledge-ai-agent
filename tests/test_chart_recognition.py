import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from document_processing.docling_adapter.chart_recognition import (
    _chart_blocks,
    _top_left_bbox,
    recognize_chart_regions,
)


class ChartRecognitionTest(unittest.TestCase):
    def test_extracts_only_chart_block_text(self):
        output = SimpleNamespace(json={"res": {"parsing_res_list": [
            {"block_label": "figure_title", "block_content": "Revenue"},
            {"block_label": "chart", "block_content": "Year | Revenue\n2025 | 10"},
            {"block_label": "text", "block_content": "Source: report"},
        ]}})

        self.assertEqual(_chart_blocks(output), "Year | Revenue\n2025 | 10")

    def test_converts_bottom_left_box_to_top_left(self):
        box = SimpleNamespace(
            l=10, t=20, r=110, b=70,
            coord_origin="BOTTOMLEFT",
        )

        self.assertEqual(_top_left_bbox(box, 100), (10.0, 30.0, 110.0, 80.0))

    def test_recognizes_exact_detected_crop_without_padding(self):
        bbox = SimpleNamespace(l=10, t=20, r=40, b=60, coord_origin="TOPLEFT")
        item = SimpleNamespace(
            label="chart", prov=[SimpleNamespace(page_no=1, bbox=bbox)]
        )
        page = SimpleNamespace(
            size=SimpleNamespace(width=100, height=100),
            get_image=lambda scale: Image.new("RGB", (100, 100), "white"),
        )
        document = SimpleNamespace(
            pages={1: page}, iterate_items=lambda: [(item, 0)]
        )

        class FakePipeline:
            def predict(self, path):
                with Image.open(path) as crop:
                    self.crop_size = crop.size
                return [SimpleNamespace(json={"res": {"parsing_res_list": [
                    {"block_label": "chart", "block_content": "Year | Value"},
                ]}})]

        fake_pipeline = FakePipeline()
        with patch(
            "document_processing.docling_adapter.chart_recognition._get_pipeline",
            return_value=fake_pipeline,
        ):
            result = recognize_chart_regions(document, {})

        self.assertEqual(fake_pipeline.crop_size, (30, 40))
        self.assertEqual(result[id(item)]["text"], "Year | Value")


if __name__ == "__main__":
    unittest.main()
