import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.main import CORPUS_COMPANY, ROLE_PERMISSIONS, AskRequest, CandidateReviewRequest, _answer_documents, _referenced_citation_ids, _role_accounts, _roles_with_permission, access_matrix, app, require_permission, upload_capability
from core.agents.intent_classifier import IntentClassifier
from core.models.agents import AgentResult, Evidence


class AskRequestTest(unittest.TestCase):
    def test_translated_hybrid_is_selectable_by_the_app(self):
        request = AskRequest(question="Revenue in 2008?", retrieval_method="translated_hybrid")
        self.assertEqual(request.retrieval_method, "translated_hybrid")
        page = (Path(__file__).resolve().parents[1] / "src/app/static/index.html").read_text()
        self.assertIn('value="translated_hybrid"', page)

    def test_report_route_uses_knowledge_agent_without_running_hybrid_sql(self):
        evidence = Evidence(
            citation_id="S1", source_type="document", source="2024 annual report",
            content="Vinamilk reported its 2024 strategy and risks.",
            metadata={"document_id": "VNM-AR-2024-VI", "page_number": 20,
                      "source_url": "https://example.com/report.pdf"},
        )
        knowledge = Mock()
        analytics = Mock()
        hybrid = Mock()
        dashboard = Mock()
        report = Mock()
        report.run.return_value = AgentResult(
            answer="The annual report discusses its strategy and risks [S1].",
            agent="report", evidence=[evidence],
        )
        classifier = Mock()
        classifier.classify.return_value = IntentClassifier.fallback(
            "Summarize Vinamilk's 2024 strategy and risks for executive decision support"
        )
        with (
            patch("app.main.KnowledgeAgent", return_value=knowledge),
            patch("app.main.SQLAnalyticsAgent", return_value=analytics),
            patch("app.main.HybridAgent", return_value=hybrid),
            patch("app.main.DashboardAgent", return_value=dashboard),
            patch("app.main.IntentClassifier", return_value=classifier),
            patch("app.main.ReportAgent", return_value=report) as report_factory,
            patch("app.main.AgentRunRepository", return_value=Mock()),
        ):
            payload = _answer_documents(
                AskRequest(question="Summarize Vinamilk's 2024 strategy and risks for executive decision support"),
                {"sub": "admin-test", "role": "admin"},
            )

        report_factory.assert_called_once_with(knowledge=knowledge, analytics=analytics)
        report.run.assert_called_once()
        hybrid.run.assert_not_called()
        analytics.run.assert_not_called()
        self.assertEqual(payload["agent"], "report")
        self.assertEqual([item["document_id"] for item in payload["citations"]], ["VNM-AR-2024-VI"])

    def test_ask_api_preserves_dashboard_visualization_and_verified_citations(self):
        answer = AgentResult(
            answer="Revenue trend [M1] [M2]", agent="dashboard",
            evidence=[Evidence(
                citation_id="M1", source_type="verified_metric", source="FY2023 net revenue",
                content="Audited source quote", metadata={"document_id": "AR23", "page_number": 12},
            ), Evidence(
                citation_id="M2", source_type="verified_metric", source="FY2024 net revenue",
                content="Audited source quote", metadata={"document_id": "AR24", "page_number": 12},
            )],
            data={"visualization": {
                "type": "line", "title": "Revenue by year", "unit": "billion VND",
                "categories": [2023, 2024],
                "series": [{"name": "Net revenue", "values": [60322.0, 61524.0]}],
            }},
        )
        dashboard = Mock()
        dashboard.run.return_value = answer
        classifier = Mock()
        classifier.classify.return_value = IntentClassifier.fallback("Show a chart of revenue by year")
        monitor = Mock()
        with (
            patch("app.main.KnowledgeAgent"),
            patch("app.main.SQLAnalyticsAgent"),
            patch("app.main.HybridAgent"),
            patch("app.main.DashboardAgent", return_value=dashboard),
            patch("app.main.IntentClassifier", return_value=classifier),
            patch("app.main.ReportAgent"),
            patch("app.main.AgentRunRepository", return_value=monitor),
        ):
            payload = _answer_documents(
                AskRequest(question="Show a chart of revenue by year"),
                {"sub": "analyst", "role": "finance_analyst"},
            )

        self.assertEqual(payload["agent"], "dashboard")
        self.assertEqual(payload["data"]["visualization"], answer.data["visualization"])
        self.assertEqual({item["id"] for item in payload["citations"]}, {"M1", "M2"})

    def test_metric_review_accepts_vietnamese_grouping_and_decimal_separators(self):
        for entered, expected in (("59723", 59723), ("59.723", 59723), ("59.723,5", 59723.5),
                                 ("59723,5", 59723.5), ("1234.5", 1234.5), ("-1,25", -1.25)):
            with self.subTest(entered=entered):
                self.assertEqual(CandidateReviewRequest(status="verified", normalized_value=entered, unit="billion VND").normalized_value, expected)

    def test_metric_review_stores_whole_numbers_as_integers(self):
        value = CandidateReviewRequest(status="verified", normalized_value="11236").normalized_value
        self.assertEqual(value, 11236)
        self.assertIsInstance(value, int)

    def test_metric_review_rejects_malformed_grouping_and_mixed_locales(self):
        for entered in ("59 723", "1.23.4", "1,234.56"):
            with self.subTest(entered=entered), self.assertRaises(ValidationError):
                CandidateReviewRequest(status="verified", normalized_value=entered)
        self.assertEqual(CandidateReviewRequest(status="verified", normalized_value="1.234,56").normalized_value, 1234.56)
        self.assertEqual(CandidateReviewRequest(status="verified", normalized_value="9007199254740993").normalized_value, 9007199254740993)

    def test_metric_review_rejects_json_float_without_locale_context(self):
        with self.assertRaises(ValidationError):
            CandidateReviewRequest(status="verified", normalized_value=11.236)

    def test_metric_review_rejects_non_finite_values(self):
        for entered in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(entered=entered), self.assertRaises(ValidationError):
                CandidateReviewRequest(status="verified", normalized_value=entered)

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

    def test_admin_metric_review_parses_vietnamese_grouping_before_database_write(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
        }
        repository = Mock()
        repository.review_metric_candidate.return_value = True
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            })
            self.assertEqual(login.status_code, 200)
            accepted = client.post("/api/analytics/candidates/7/review", json={
                "status": "verified", "normalized_value": "11.236,5", "unit": "billion VND",
            })
            rejected = client.post("/api/analytics/candidates/8/review", json={
                "status": "verified", "normalized_value": "11,236.5", "unit": "billion VND",
            })

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(rejected.status_code, 422)
        repository.review_metric_candidate.assert_called_once_with(
            7, "verified", 11236.5, "billion VND", "admin-test", CORPUS_COMPANY,
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

    def test_admin_can_inspect_company_scoped_extracted_tables(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
        }
        store = Mock()
        store.get_document_tables.return_value = [{
            "page_number": 2, "table_index": 0, "columns": ["Metric", "Value"],
            "rows": [{"Metric": "Revenue", "Value": "100"}], "row_count": 1,
            "metadata": {"parser": "test"},
        }]
        with patch.dict("os.environ", environment, clear=False), \
             patch("core.database.structured_store.StructuredDataStore", return_value=store), \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.get(
                "/api/admin/processing/UPLOAD-1/tables?table_offset=1&row_offset=5&row_limit=20"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tables"][0]["rows"][0]["Metric"], "Revenue")
        store.get_document_tables.assert_called_once_with(
            "UPLOAD-1", company=CORPUS_COMPANY, table_offset=1, table_limit=50,
            row_offset=5, row_limit=20,
        )
        store.close.assert_called_once()

    def test_employee_cannot_inspect_extracted_tables(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_VIEWER_USERNAME": "viewer-test",
            "DEMO_VIEWER_PASSWORD": "viewer-password",
        }
        store = Mock()
        with patch.dict("os.environ", environment, clear=False), \
             patch("core.database.structured_store.StructuredDataStore", return_value=store), \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "viewer-test", "password": "viewer-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.get("/api/admin/processing/UPLOAD-1/tables")

        self.assertEqual(response.status_code, 403)
        store.get_document_tables.assert_not_called()

    def test_admin_can_open_private_uploaded_pdf_at_source_review(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
        }
        repository = Mock()
        repository.uploaded_source.return_value = {
            "title": "Annual report", "format": "PDF", "storage_path": "UPLOAD-1/report.pdf",
        }
        storage = Mock()
        storage.storage.from_.return_value.download.return_value = b"%PDF-1.7 test"
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             patch("app.main._storage_client", return_value=(storage, "enterprise-documents")), \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.get("/api/admin/processing/UPLOAD-1/source#page=4")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-1.7 test")
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn("inline; filename*=UTF-8''Annual%20report.pdf", response.headers["content-disposition"])
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        repository.uploaded_source.assert_called_once_with("UPLOAD-1", company=CORPUS_COMPANY)
        storage.storage.from_.return_value.download.assert_called_once_with("UPLOAD-1/report.pdf")
        repository.close.assert_called_once()

    def test_employee_cannot_open_private_uploaded_source(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_VIEWER_USERNAME": "viewer-test",
            "DEMO_VIEWER_PASSWORD": "viewer-password",
        }
        repository = Mock()
        storage = Mock()
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             patch("app.main._storage_client", return_value=(storage, "enterprise-documents")), \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "viewer-test", "password": "viewer-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.get("/api/admin/processing/UPLOAD-1/source")

        self.assertEqual(response.status_code, 403)
        repository.uploaded_source.assert_not_called()
        storage.storage.from_.return_value.download.assert_not_called()

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
