import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.database.document_processing_outputs_repository import (  # noqa: E402
    DocumentProcessingOutputsRepository,
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
            "elements": [{"text": "Revenue"}],
            "structured_tables": [{"columns": ["Year"], "rows": []}],
            "document_metadata": {"format": "PDF"},
        }

        output = self.repository.get_document_output("DOC-1", company="Example")

        self.assertEqual(output, {
            "metadata": {"format": "PDF"},
            "elements": [{"text": "Revenue"}],
            "tables": [{"columns": ["Year"], "rows": []}],
        })
        self.assertEqual(self.cursor.execute.call_args.args[1], ("DOC-1", "Example"))

    def test_rejects_output_without_pipeline_metadata_before_database_write(self):
        with self.assertRaises(ValueError):
            self.repository.replace_document("DOC-1", {"elements": [], "tables": []})

        self.cursor.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
