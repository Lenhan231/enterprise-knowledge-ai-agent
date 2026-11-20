import unittest
from pathlib import Path
import sys
from unittest.mock import MagicMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.database.document_repository import DocumentRepository
from core.models.agents import AgentRequest, AgentResult, Evidence


class DocumentDashboardTest(unittest.TestCase):
    def test_knowledge_document_list_reports_saved_parser_chunks_for_retry_ui(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []

        repository.list_knowledge_documents()

        query = " ".join(cursor.execute.call_args.args[0].lower().split())
        self.assertIn("exists ( select 1 from public.document_parser_chunks parser_chunk", query)
        self.assertIn("parser_chunk.document_id = d.document_id ) as has_parser_chunks", query)

    def test_uploaded_source_lookup_requires_ready_upload_in_company_scope(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {
            "title": "Annual report", "format": "PDF", "storage_path": "UPLOAD-1/report.pdf",
        }

        result = repository.uploaded_source("UPLOAD-1", "Vinamilk", "admin", "admin-user")

        self.assertEqual(result["storage_path"], "UPLOAD-1/report.pdf")
        query, params = cursor.execute.call_args.args
        normalized = " ".join(query.lower().split())
        self.assertIn("source_type = 'user_upload'", normalized)
        self.assertIn("processing_status = 'ready'", normalized)
        self.assertIn("storage_path is not null", normalized)
        self.assertEqual(params, ("UPLOAD-1", "admin", "admin", "admin", "admin-user"))

    def test_manifest_upsert_persists_processing_status(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        document = {"document_id": "DOC-1", "processing_status": "processing"}

        repository.upsert_document(document)

        cursor = repository.conn.cursor.return_value.__enter__.return_value
        query = " ".join(cursor.execute.call_args.args[0].lower().split())
        self.assertIn("allowed_roles, storage_path, processing_status", query)
        self.assertIn("processing_status = excluded.processing_status", query)
        self.assertEqual(cursor.execute.call_args.args[1], {
            **document, "storage_path": None, "knowledge_base_active": True,
        })
        repository.conn.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
