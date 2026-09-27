import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.main import CORPUS_COMPANY, ROLE_PERMISSIONS, AskRequest, _referenced_citation_ids, _role_accounts, _roles_with_permission, access_matrix, app, require_permission, upload_capability


class AskRequestTest(unittest.TestCase):
    def test_supported_retrieval_methods_are_validated(self):
        for method in ("dense", "bm25", "hybrid", "parent"):
            with self.subTest(method=method):
                request = AskRequest(question="Revenue for 2024?", retrieval_method=method)
                self.assertEqual(request.retrieval_method, method)

    def test_unknown_retrieval_method_is_rejected(self):
        with self.assertRaises(ValidationError):
            AskRequest(question="Revenue for 2024?", retrieval_method="unfiltered")

    def test_access_matrix_matches_actual_role_capabilities(self):
        matrix = access_matrix({"sub": "admin"})
        permissions = {row["role"]: set(row["permissions"]) for row in matrix["roles"]}
        self.assertEqual(permissions, ROLE_PERMISSIONS)
        self.assertIn("view_agent_monitoring", permissions["admin"])
        self.assertNotIn("view_agent_monitoring", permissions["employee"])
        self.assertNotIn("view_agent_monitoring", permissions["document_uploader"])
        self.assertEqual(set(_roles_with_permission("view_analytics")), {"finance_analyst", "sustainability_analyst", "executive", "admin"})
        self.assertNotIn("view_analytics", permissions["employee"])

    def test_uploader_can_upload_without_analytics_or_admin_review(self):
        self.assertTrue(upload_capability({"role": "document_uploader"})["can_upload"])
        self.assertNotIn("view_analytics", ROLE_PERMISSIONS["document_uploader"])
        self.assertNotIn("review_metrics", ROLE_PERMISSIONS["document_uploader"])
        self.assertNotIn("manage_access", ROLE_PERMISSIONS["document_uploader"])
        self.assertNotIn("document_uploader", _roles_with_permission("review_metrics"))

    def test_sustainability_analyst_has_a_configurable_demo_identity(self):
        with patch.dict("os.environ", {
            "DEMO_SUSTAINABILITY_ANALYST_USERNAME": "esg-reviewer",
            "DEMO_SUSTAINABILITY_ANALYST_PASSWORD": "test-password",
        }, clear=False):
            accounts = _role_accounts()

        self.assertEqual(accounts["esg-reviewer"], ("test-password", "sustainability_analyst"))
        self.assertIn("view_analytics", ROLE_PERMISSIONS[accounts["esg-reviewer"][1]])

    def test_employee_is_denied_by_authenticated_upload_http_route(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_VIEWER_USERNAME": "employee-test",
            "DEMO_VIEWER_PASSWORD": "employee-password",
        }
        with patch.dict("os.environ", environment, clear=False), TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "employee-test", "password": "employee-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.post(
                "/api/documents/upload",
                data={
                    "title": "Should be denied",
                    "document_type": "internal_report",
                    "domain": "finance",
                    "allowed_roles": "employee",
                },
                files={"file": ("denied.txt", b"No database write should occur.", "text/plain")},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Your role cannot access this feature")

    def test_dashboard_endpoint_uses_manifest_company_scope(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ANALYST_USERNAME": "analyst-test",
            "DEMO_ANALYST_PASSWORD": "analyst-password",
        }
        repository = Mock()
        repository.corpus_dashboard.return_value = {"documents": []}
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "analyst-test", "password": "analyst-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.get("/api/dashboard")

        self.assertEqual(response.status_code, 200)
        repository.corpus_dashboard.assert_called_once_with(
            "finance_analyst", "analyst-test", company=CORPUS_COMPANY,
        )

    def test_admin_can_inspect_paginated_parsed_chunks_in_manifest_scope(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
        }
        parsed = Mock()
        parsed.get_document.return_value = [{"chunk_index": 0, "content": "extracted OCR text", "metadata": {}}]
        with patch.dict("os.environ", environment, clear=False), \
             patch("core.database.processed_chunks_repository.ProcessedChunksRepository", return_value=parsed), \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.get("/api/admin/processing/UPLOAD-1/chunks?offset=5&limit=10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["chunks"][0]["content"], "extracted OCR text")
        parsed.get_document.assert_called_once_with(
            "UPLOAD-1", limit=10, offset=5, company=CORPUS_COMPANY,
        )
        parsed.close.assert_called_once()

    def test_unknown_permission_fails_closed(self):
        with self.assertRaises(ValueError):
            require_permission("manage_everything")

    def test_citation_filter_accepts_only_ids_referenced_by_final_answer(self):
        self.assertEqual(
            _referenced_citation_ids(
                "Revenue [S2], profit 【M1】, source [Nguồn: S3], "
                "zero-width [\u200bS4]; ignore S5."
            ),
            {"S2", "M1", "S3", "S4"},
        )


if __name__ == "__main__":
    unittest.main()
