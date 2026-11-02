import sys
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from document_processing.docling_adapter.chart_recognition import (
    _chart_blocks,
    _correct_chart_text,
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

    def test_recognizes_chart_from_three_x_page_crop(self):
        page = SimpleNamespace(
            size=SimpleNamespace(width=100, height=100),
            image=SimpleNamespace(pil_image=Image.new("RGB", (100, 100), "white")),
        )
        document = SimpleNamespace(pages={1: page})

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
            result = recognize_chart_regions(
                document,
                {},
                [{"page_no": 1, "bbox": [10, 20, 40, 60]}],
            )

        self.assertEqual(fake_pipeline.crop_size, (90, 120))
        self.assertEqual(result[0]["text"], "Year | Value")

    @patch.dict(os.environ, {"GROQ_API_KEY": "test-secret"})
    @patch("document_processing.docling_adapter.chart_recognition._get_groq_client")
    def test_groq_corrects_text_without_changing_numeric_cells(self, get_client):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"corrections": [
                {"row": 0, "column": 0, "text": "Doanh thu"},
                {"row": 1, "column": 0, "text": "Lợi nhuận sau thuế"},
                {"row": 1, "column": 1, "text": "999"},
                {"row": 2, "column": 1, "text": "không có"},
            ]})
        ))])
        get_client.return_value.chat.completions.create.return_value = response

        result = _correct_chart_text(
            Image.new("RGB", (16, 16), "white"),
            "Doanh thu toản | Thực hiện\nLợi nhuận sau thuế | 10.100\nKỳ | —",
            ["Doanh thu toàn", "Lợi nhuận sau thuế"],
        )

        self.assertEqual(
            result,
            "Doanh thu | Thực hiện\nLợi nhuận sau thuế | 10.100\nKỳ | —",
        )


if __name__ == "__main__":
    unittest.main()
