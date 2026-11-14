import sys
import json
import os
import unittest
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

if any(importlib.util.find_spec(module) is None for module in ("docling", "docling_core", "PIL")):
    raise unittest.SkipTest("Docling and Pillow are optional document-processing dependencies")

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from document_processing.docling_adapter.chart_recognition import (
    _correct_chart_text,
    _openparser_table,
    _recognize_with_groq,
    recognize_chart_regions,
)


class ChartRecognitionTest(unittest.TestCase):
    def test_maps_openparser_chart_cells_to_pipe_rows(self):
        element = {"cells": [
            {"row_index": 1, "column_index": 1, "text": "10.100"},
            {"row_index": 0, "column_index": 0, "text": "Year"},
            {"row_index": 1, "column_index": 0, "text": "2025"},
            {"row_index": 0, "column_index": 1, "text": "Revenue"},
        ]}

        self.assertEqual(_openparser_table(element), "Year | Revenue\n2025 | 10.100")

    def test_recognizes_chart_from_three_x_page_crop(self):
        page = SimpleNamespace(
            size=SimpleNamespace(width=100, height=100),
            image=SimpleNamespace(pil_image=Image.new("RGB", (100, 100), "white")),
        )
        document = SimpleNamespace(pages={1: page})

        fake_openparser = SimpleNamespace(crop_size=None)

        def recognize(crop):
            fake_openparser.crop_size = crop.size
            return "Year | Value"

        with patch(
            "document_processing.docling_adapter.chart_recognition._recognize_with_openparser",
            side_effect=recognize,
        ):
            result = recognize_chart_regions(
                document,
                {},
                [{"page_no": 1, "bbox": [10, 20, 40, 60]}],
            )

        self.assertEqual(fake_openparser.crop_size, (90, 120))
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

    @patch.dict(os.environ, {"GROQ_API_KEY": "test-secret"})
    @patch("document_processing.docling_adapter.chart_recognition._get_groq_client")
    def test_groq_direct_extraction_uses_structured_result(self, get_client):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"charts": [{
                "title": "Doanh thu",
                "headers": ["Thực hiện", "Kế hoạch"],
                "rows": [{"label": "Năm 2025", "values": ["10.100", "9.400"]}],
            }]})
        ))])
        get_client.return_value.chat.completions.create.return_value = response

        text = _recognize_with_groq(Image.new("RGB", (16, 16), "white"), ["Doanh thu toàn"])

        self.assertEqual(
            text,
            "Chart title: Doanh thu\nThực hiện | Kế hoạch\nNăm 2025 | 10.100 | 9.400",
        )


if __name__ == "__main__":
    unittest.main()
