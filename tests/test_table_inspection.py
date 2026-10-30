"""HTTP regression checks for company-scoped extracted table inspection."""

from contextlib import ExitStack
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.main import app, CORPUS_COMPANY, _issue_token


class TableInspectionTest(unittest.TestCase):
    def setUp(self):
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.dict(os.environ, {
            "AUTH_SECRET_KEY": "test-only-secret-for-table-inspection-32-chars",
            "EMBEDDING_PRELOAD": "0", "RERANKER_PRELOAD": "0",
        }))
        self.store_type = stack.enter_context(patch(
            "core.database.structured_store.StructuredDataStore", autospec=True,
        ))
        self.store = self.store_type.return_value
        self.store.get_document_tables.return_value = [{"table_index": 0, "rows": [{"value": "100"}]}]
        self.client = stack.enter_context(TestClient(app))
        self.headers = {"Authorization": "Bearer " + _issue_token("processor-test", "document_processing_owner")}

    def test_inspection_passes_server_company_and_pagination(self):
        response = self.client.get(
            "/api/admin/processing/TEST-DOC/tables?table_offset=1&row_offset=5&row_limit=20",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tables"][0]["rows"], [{"value": "100"}])
        self.store.get_document_tables.assert_called_once_with(
            "TEST-DOC", company=CORPUS_COMPANY, table_offset=1, table_limit=50,
            row_offset=5, row_limit=20,
        )
        self.store.close.assert_called_once()

    def test_empty_company_scoped_result_returns_404(self):
        self.store.get_document_tables.return_value = []
        response = self.client.get("/api/admin/processing/TEST-DOC/tables", headers=self.headers)
        self.assertEqual(response.status_code, 404)
        self.store.close.assert_called_once()

    def test_invalid_pagination_returns_422_and_closes_store(self):
        self.store.get_document_tables.side_effect = ValueError("row_limit must be 1-100")
        response = self.client.get("/api/admin/processing/TEST-DOC/tables?row_limit=1000", headers=self.headers)
        self.assertEqual(response.status_code, 422)
        self.store.close.assert_called_once()

    def test_employee_is_denied_before_database_access(self):
        headers = {"Authorization": "Bearer " + _issue_token("viewer-test", "employee")}
        response = self.client.get("/api/admin/processing/TEST-DOC/tables", headers=headers)
        self.assertEqual(response.status_code, 403)
        self.store_type.assert_not_called()

    def test_anonymous_is_denied_before_database_access(self):
        response = self.client.get("/api/admin/processing/TEST-DOC/tables")
        self.assertEqual(response.status_code, 401)
        self.store_type.assert_not_called()
