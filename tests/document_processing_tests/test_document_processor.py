"""Unit and component-integration tests for the current document parser contract."""

from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from core.chunking.processor import ChunkingProcessor
from document_processing.document_processor import DocumentProcessor
from document_processing.element_taxonomy import normalize_element_label


class DocumentProcessorUnitTest(unittest.TestCase):
    def test_normalize_element_label_maps_aliases_and_unknown_values(self):
        self.assertEqual(normalize_element_label("Section Header"), "title")
        self.assertEqual(normalize_element_label("table-caption"), "title_table")
        self.assertEqual(normalize_element_label("Graphic"), "figure")
        self.assertEqual(normalize_element_label("unknown parser label"), "text")
        self.assertEqual(normalize_element_label(None), "text")

    def test_clean_text_normalizes_line_endings_and_whitespace(self):
        self.assertEqual(
            DocumentProcessor._clean_text("  A\u00a0B\x00\r\n\r\n\r\n C  "),
            "A B\n\nC",
        )

    def test_clean_value_recursively_cleans_strings_without_coercing_numbers(self):
        value = {"  Revenue\u00a0": ["  100  ", 25, {" unit ": " VND "}]}
        self.assertEqual(
            DocumentProcessor._clean_value(value),
            {"Revenue": ["100", 25, {"unit": "VND"}]},
        )

    def test_rejects_unsupported_format_before_loading_parser(self):
        with patch.dict(sys.modules, {"document_processing.docling_adapter.processor": None}):
            with self.assertRaisesRegex(ValueError, "Unsupported document format: .exe"):
                DocumentProcessor().process("report.exe", b"content", {})

    def test_rejects_unsupported_intent_before_loading_parser(self):
        with patch.dict(sys.modules, {"document_processing.docling_adapter.processor": None}):
            with self.assertRaisesRegex(ValueError, "Unsupported document intent: unknown"):
                DocumentProcessor({"intent": "unknown"}).process("report.pdf", b"content", {})


class DocumentProcessingIntegrationTest(unittest.TestCase):
    @staticmethod
    def parser_module(parsed):
        parser = Mock()
        parser.process.return_value = parsed
        module = ModuleType("document_processing.docling_adapter.processor")
        module.DoclingProcessor = Mock(return_value=parser)
        return module, module.DoclingProcessor, parser

    def test_parser_output_is_normalized_then_chunked_with_provenance(self):
        parsed = {
            "elements": [
                {"text": " Revenue\u00a0was 100 VND. ", "metadata": {
                    "layout_type": "section-header", "parser": "docling-test", "page_number": 1,
                }},
                {"element_type": "table", "table_ref": 0, "metadata": {
                    "element_type": "table", "table_index": 0, "page_number": 1,
                }},
            ],
            "tables": [{
                "columns": [" Year ", "Revenue"],
                "rows": [{" Year ": " 2024 ", "Revenue": " 100 VND "}],
                "metadata": {"parser": "docling-table-test", "page_number": 1},
            }],
            "metadata": {},
        }
        module, parser_factory, parser = self.parser_module(parsed)
        metadata = {
            "document_id": "DOC-1", "source_type": "upload_test",
            "title": "Private display title", "uploaded_by": "admin",
        }

        with patch.dict(sys.modules, {"document_processing.docling_adapter.processor": module}):
            normalized = DocumentProcessor().process("annual-report.pdf", b"pdf", metadata)
        result = ChunkingProcessor().process(normalized)

        parser_factory.assert_called_once_with({"parser_engine": "docling"})
        parser.process.assert_called_once()
        element = normalized["elements"][0]
        self.assertEqual(element["text"], "Revenue was 100 VND.")
        self.assertEqual(element["element_type"], "title")
        self.assertEqual(element["metadata"]["document_id"], "DOC-1")
        self.assertNotIn("title", element["metadata"])
        self.assertNotIn("uploaded_by", element["metadata"])
        self.assertEqual(normalized["tables"][0]["columns"], ["Year", "Revenue"])
        self.assertEqual(normalized["tables"][0]["rows"], [
            {"Year": "2024", "Revenue": "100 VND"},
        ])
        self.assertTrue(any("Revenue was 100 VND." in chunk["text"] for chunk in result["chunks"]))
        table_chunks = [chunk for chunk in result["chunks"] if chunk["metadata"].get("element_type") == "table"]
        self.assertEqual(len(table_chunks), 1)
        self.assertIn("2024", table_chunks[0]["text"])
        self.assertEqual(result["metadata"]["document_id"], "DOC-1")

    def test_image_results_drop_page_numbers_from_elements_and_tables(self):
        parsed = {
            "elements": [{"text": "Chart", "metadata": {"page_number": 1}}],
            "tables": [{"columns": [], "rows": [], "page_number": 1,
                        "metadata": {"page_number": 1}}],
            "metadata": {},
        }
        module, _factory, _parser = self.parser_module(parsed)

        with patch.dict(sys.modules, {"document_processing.docling_adapter.processor": module}):
            result = DocumentProcessor().process("chart.png", b"image", {})

        self.assertNotIn("page_number", result["elements"][0]["metadata"])
        self.assertNotIn("page_number", result["tables"][0])
        self.assertNotIn("page_number", result["tables"][0]["metadata"])


if __name__ == "__main__":
    unittest.main()
