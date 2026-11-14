import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.database.document_processing_outputs_repository import (  # noqa: E402
    DocumentProcessingOutputsRepository,
)
from core.database.document_processing_output_repository import (  # noqa: E402
    DocumentProcessingOutputRepository,
)


class DocumentProcessingOutputsRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.repository = DocumentProcessingOutputsRepository(self.connection)

    def test_replace_document_stores_normalized_output_separately(self):
        parsed = {
            "metadata": {"pipeline_id": "docling", "format": "PDF"},
            "elements": [{"text": "Revenue", "metadata": {"page_number": 1}}],
            "tables": [{"columns": ["Year"], "rows": [{"Year": "2024"}]}],
        }

        self.repository.replace_document("DOC-1", parsed)

        query, params = self.cursor.execute.call_args.args
        self.assertIn("public.document_processing_outputs", query)
        self.assertIn("elements", query)
        self.assertIn("structured_tables", query)
        self.assertEqual(params[0:2], ("DOC-1", "docling"))
        self.assertEqual(params[2].obj, parsed["elements"])
        self.assertEqual(params[3].obj, parsed["tables"])
        self.assertEqual(params[4].obj, parsed["metadata"])

    def test_get_document_output_reconstructs_chunker_input(self):
        self.cursor.fetchone.return_value = {
            "pipeline_id": "docling",
            "text_elements": [{"text": "Revenue", "metadata": {"element_type": "text", "layout_type": "text"}}],
            "figures": [],
            "structured_tables": [{"columns": ["Year"], "rows": []}],
            "document_metadata": {"format": "PDF"},
        }

        output = self.repository.get_document_output("DOC-1", company="Example")

        self.assertEqual(output, {
            "metadata": {"format": "PDF"},
            "elements": [{"text": "Revenue", "metadata": {"element_type": "text", "layout_type": "text"}}],
            "tables": [{"columns": ["Year"], "rows": []}],
        })
        self.assertEqual(self.cursor.execute.call_args.args[1], ("DOC-1", "Example"))

    def test_rejects_output_without_pipeline_metadata_before_database_write(self):
        with self.assertRaises(ValueError):
            self.repository.replace_document("DOC-1", {"elements": [], "tables": []})

        self.cursor.execute.assert_not_called()

class DocumentProcessingOutputReviewTest(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.repository = DocumentProcessingOutputRepository(self.connection)

    def test_get_document_output_returns_elements_and_tables_for_review(self):
        self.cursor.fetchone.return_value = {
            "pipeline_id": "docling",
            "elements": [{"text": "Revenue 100", "metadata": {"page_number": 1}}],
            "tables": [{"columns": ["Year"], "rows": [{"Year": "2024"}]}],
            "document_metadata": {"company": "Example"},
        }

        output = self.repository.get_document_output("DOC-1", company="Example")

        self.assertEqual(output["pipeline_id"], "docling")
        self.assertEqual(output["elements"][0]["text"], "Revenue 100")
        self.assertEqual(output["tables"][0]["rows"], [{"Year": "2024"}])
        query = self.cursor.execute.call_args.args[0]
        self.assertIn("o.document_metadata->>'company'", query)
        self.assertEqual(self.cursor.execute.call_args.args[1], ("DOC-1", "Example"))

if __name__ == "__main__":
    unittest.main()
