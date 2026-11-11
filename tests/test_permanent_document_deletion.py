import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app import main as app_main  # noqa: E402
from core.database.document_repository import DocumentRepository  # noqa: E402


class PermanentDocumentDeletionTest(unittest.TestCase):
    def setUp(self):
        self.repository = DocumentRepository.__new__(DocumentRepository)
        self.repository.conn = MagicMock()
        self.cursor = self.repository.conn.cursor.return_value.__enter__.return_value

    def test_delete_cleans_related_data_for_removed_upload(self):
        self.cursor.fetchone.side_effect = [
            {"storage_path": "UPLOAD-1/source.pdf"},
            {"has_metric_evidence": True, "has_financial_metrics": True},
            {"document_id": "UPLOAD-1"},
        ]

        storage_path = self.repository.delete_removed_upload("UPLOAD-1")

        self.assertEqual(storage_path, "UPLOAD-1/source.pdf")
        queries = [" ".join(call.args[0].lower().split()) for call in self.cursor.execute.call_args_list]
        self.assertIn("knowledge_base_active is false", queries[0])
        self.assertIn("source_type = 'user_upload'", queries[0])
        self.assertTrue(any("delete from public.business_metric_evidence" in query for query in queries))
        self.assertTrue(any("delete from public.extracted_financial_metrics" in query for query in queries))
        self.assertTrue(any("delete from public.document_chunks" in query for query in queries))
        self.assertIn("delete from public.documents", queries[-1])

    def test_delete_rejects_active_or_missing_source(self):
        self.cursor.fetchone.return_value = None

        self.assertIsNone(self.repository.delete_removed_upload("UPLOAD-1"))
        self.assertEqual(self.cursor.execute.call_count, 1)

    def test_admin_delete_removes_private_source_after_database_rows(self):
        repository = MagicMock()
        repository.delete_removed_upload.return_value = "UPLOAD-1/source.pdf"
        storage = MagicMock()
        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "DocumentRepository", return_value=repository),
            patch.object(app_main, "_storage_client", return_value=(storage, "private")),
        ):
            result = app_main.delete_removed_knowledge_document(
                "UPLOAD-1", request=None, user={"role": "admin"},
            )

        self.assertEqual(result["deleted"], True)
        self.assertTrue(result["source_file_removed"])
        storage.storage.from_.return_value.remove.assert_called_once_with(["UPLOAD-1/source.pdf"])
        repository.close.assert_called_once()

    def test_admin_delete_refuses_a_source_still_in_knowledge_base(self):
        repository = MagicMock()
        repository.delete_removed_upload.return_value = None
        with (
            patch.object(app_main, "_require_same_origin"),
            patch.object(app_main, "DocumentRepository", return_value=repository),
            self.assertRaises(HTTPException) as raised,
        ):
            app_main.delete_removed_knowledge_document(
                "UPLOAD-1", request=None, user={"role": "admin"},
            )

        self.assertEqual(raised.exception.status_code, 409)
        repository.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
