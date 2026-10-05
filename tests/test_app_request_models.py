import sys
import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import app.main as app_main
from app.main import CORPUS_COMPANY, DOCUMENT_ROLES, ROLE_PERMISSIONS, AskRequest, CandidateReviewRequest, KnowledgeBaseStatusRequest, _answer_documents, _commerce_reference_metadata, _referenced_citation_ids, _role_accounts, _roles_with_permission, access_matrix, app, require_permission, upload_capability
from core.agents.intent_classifier import IntentClassifier
from core.models.agents import AgentResult, Evidence


class AskRequestTest(unittest.TestCase):
    def test_analyst_dashboard_can_request_one_commerce_domain_at_a_time(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ANALYST_USERNAME": "analyst-test",
            "DEMO_ANALYST_PASSWORD": "analyst-password",
        }
        repository = Mock()
        repository.commerce_dashboard.side_effect = lambda keys: {"requested_keys": keys}
        expected = {
            "inventory_allocation": ("sales_by_year", "inventory_by_year", "inventory_year_end_by_category"),
            "promotion_planning": ("sales_by_year", "promotions_by_year"),
            "nationwide_logistics": ("sales_by_year", "logistics_by_year_region"),
        }
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             TestClient(app) as client:
            self.assertEqual(client.post("/api/auth/login", json={
                "username": "analyst-test", "password": "analyst-password",
            }).status_code, 200)
            responses = {
                domain: client.get(f"/api/commerce/dashboard?domain={domain}")
                for domain in expected
            }
            campaigns = client.get("/api/commerce/dashboard?domain=promotion_planning&detail=campaigns")
            invalid = client.get("/api/commerce/dashboard?domain=unknown")
            invalid_detail = client.get("/api/commerce/dashboard?domain=nationwide_logistics&detail=campaigns")

        for domain, response in responses.items():
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["requested_keys"], list(expected[domain]))
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(campaigns.status_code, 200)
        self.assertEqual(campaigns.json()["requested_keys"], ["promotions_by_campaign"])
        self.assertEqual(invalid_detail.status_code, 422)
        self.assertEqual(repository.commerce_dashboard.call_args_list,
                         [unittest.mock.call(keys) for keys in expected.values()]
                         + [unittest.mock.call(("promotions_by_campaign",))])

    def test_commerce_domain_is_accepted_for_questions_and_server_side_suggestions(self):
        question = AskRequest(
            question="Should we rebalance inventory?",
            commerce_decision_support=True,
            business_decision_domain="inventory_allocation",
        )
        suggestions = AskRequest(
            decision_suggestions=True,
            business_decision_domain="promotion_planning",
        )
        self.assertEqual(question.business_decision_domain, "inventory_allocation")
        self.assertTrue(question.commerce_decision_support)
        self.assertTrue(suggestions.decision_suggestions)
        with self.assertRaises(ValidationError):
            AskRequest(question="Should we change inventory?", business_decision_domain="made_up")

    def test_commerce_upload_reference_requires_trusted_classification_and_attribution(self):
        metadata = _commerce_reference_metadata(
            ["inventory_allocation", "nationwide_logistics", "inventory_allocation"],
            " Walmart Inc. ",
            "company_policy_reference",
            " Walmart suppliers only; not Commerce Demo policy ",
        )
        self.assertEqual(metadata["knowledge_domains"], ["inventory_allocation", "nationwide_logistics"])
        self.assertEqual(metadata["source_publisher"], "Walmart Inc.")
        self.assertEqual(metadata["reference_applicability"], "Walmart suppliers only; not Commerce Demo policy")
        self.assertEqual(metadata["evidence_class"], "company_policy_reference")
        self.assertFalse(metadata["external_policy_reference"])
        self.assertFalse(metadata["synthetic_company_policy"])
        self.assertTrue(metadata["commerce_reference_active"])

        synthetic = _commerce_reference_metadata(
            ["inventory_allocation"],
            "Commerce Demo (fictional organization)",
            "company_policy_reference",
            "Fictional Commerce Demo only; not a policy of a real company.",
            True,
        )
        self.assertTrue(synthetic["synthetic_company_policy"])
        self.assertFalse(synthetic["external_business_reference"])
        self.assertEqual(synthetic["evidence_class"], "company_policy_reference")
        self.assertTrue(synthetic["commerce_reference_active"])

        for domains, publisher, reference_type in (
            (["made_up"], "Publisher", "company_policy_reference"),
            (["inventory_allocation"], "", "company_policy_reference"),
            (["inventory_allocation"], "Publisher", ""),
        ):
            with self.subTest(reference_type=reference_type, publisher=publisher):
                with self.assertRaises(HTTPException):
                    _commerce_reference_metadata(domains, publisher, reference_type)

        with self.assertRaises(HTTPException):
            _commerce_reference_metadata(["inventory_allocation"], "Publisher", "company_policy_reference", " ")

        for reference_type, publisher, scope in (
            ("company_practice_reference", "Commerce Demo (fictional organization)", "Fictional demo only"),
            ("company_policy_reference", "Walmart Inc.", "Fictional demo only"),
            ("company_policy_reference", "Commerce Demo (fictional organization)", "Applies to suppliers"),
        ):
            with self.subTest(reference_type=reference_type, publisher=publisher, scope=scope):
                with self.assertRaises(HTTPException):
                    _commerce_reference_metadata(["inventory_allocation"], publisher, reference_type, scope, True)

    def test_document_uploader_cannot_mark_an_upload_as_synthetic_policy(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_UPLOADER_USERNAME": "uploader-test",
            "DEMO_UPLOADER_PASSWORD": "uploader-password",
        }
        with patch.dict("os.environ", environment, clear=False), TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "uploader-test", "password": "uploader-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.post(
                "/api/documents/upload",
                files={"file": ("demo-policy.pdf", b"%PDF-1.4\n", "application/pdf")},
                data={
                    "title": "Synthetic inventory policy",
                    "document_type": "company_policy_reference",
                    "domain": "inventory_allocation",
                    "source_publisher": "Commerce Demo (fictional organization)",
                    "reference_type": "company_policy_reference",
                    "reference_applicability": "Fictional Commerce Demo only",
                    "synthetic_company_policy": "true",
                    "knowledge_domains": "inventory_allocation",
                    "allowed_roles": "admin",
                },
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Only an admin", response.json()["detail"])

    def test_admin_upload_marks_synthetic_policy_metadata_before_indexing(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
        }
        repository = Mock()
        processor = Mock()
        processor.process.side_effect = lambda _name, _content, metadata: {
            "chunks": [{"text": "Fictional inventory policy", "metadata": {**metadata, "page_number": 1}}],
            "tables": [],
        }
        embedding = Mock(model_name="test-embedding", max_sequence_length=128)
        embedding.embed_documents.return_value = [[0.1, 0.2]]
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main._storage_client", return_value=(Mock(), "test-bucket")), \
             patch("app.main.DocumentRepository", return_value=repository), \
             patch("core.document_processing.processors.document_processor.DocumentProcessor", return_value=processor) as processor_class, \
             patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding), \
             patch("core.database.document_chunks_repository.DocumentChunkRepository") as chunks_repo, \
             patch("core.database.processed_chunks_repository.ProcessedChunksRepository"), \
             patch("core.database.structured_store.StructuredDataStore"), \
             patch("core.utils.token_counter.TokenCounter") as token_counter, \
             TestClient(app) as client:
            processor_class.SUPPORTED = {".pdf"}
            token_counter.return_value.split_text.side_effect = lambda text, max_sequence_tokens: [text]
            token_counter.return_value.count.return_value = 1
            self.assertEqual(client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            }).status_code, 200)
            response = client.post(
                "/api/documents/upload",
                files={"file": ("inventory-policy.pdf", b"%PDF-1.4\n", "application/pdf")},
                data={
                    "title": "Synthetic inventory policy",
                    "document_type": "company_policy_reference",
                    "domain": "inventory_allocation",
                    "source_publisher": "Commerce Demo (fictional organization)",
                    "reference_type": "company_policy_reference",
                    "reference_applicability": "Fictional Commerce Demo only; not a policy of a real company.",
                    "synthetic_company_policy": "true",
                    "knowledge_domains": "inventory_allocation",
                    "allowed_roles": "admin",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["searchable"])
        uploaded_metadata = processor.process.call_args.args[2]
        self.assertTrue(uploaded_metadata["synthetic_company_policy"])
        self.assertFalse(uploaded_metadata["external_business_reference"])
        self.assertEqual(uploaded_metadata["source_type"], "synthetic_demo_policy")
        self.assertTrue(uploaded_metadata["commerce_reference_active"])
        indexed_rows = chunks_repo.return_value.replace_document.call_args.args[1]
        self.assertTrue(indexed_rows[0][3]["synthetic_company_policy"])
        self.assertTrue(indexed_rows[0][3]["commerce_reference_active"])

    def test_report_route_uses_knowledge_agent_without_running_hybrid_sql(self):
        evidence = Evidence(
            citation_id="S1", source_type="document", source="2024 annual report",
            content="Vinamilk reported its 2024 strategy and risks.",
            metadata={"document_id": "VNM-AR-2024-VI", "page_number": 20,
                      "source_url": "https://example.com/report.pdf",
                      "source_publisher": "Example Publisher",
                      "evidence_class": "company_practice_reference",
                      "reference_applicability": "External example only."},
        )
        knowledge = Mock()
        analytics = Mock()
        hybrid = Mock()
        dashboard = Mock()
        report = Mock()
        report.run.return_value = AgentResult(
            answer="The annual report discusses its strategy and risks [S1].",
            agent="report", evidence=[evidence],
            metadata={"token_usage": {
                "sql_generation": {"input_tokens": 80, "output_tokens": 14, "total_tokens": 94},
                "answer_generation": {"input_tokens": 140, "output_tokens": 30, "total_tokens": 170},
                "total": {"input_tokens": 220, "output_tokens": 44, "total_tokens": 264},
            }},
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
        self.assertEqual(payload["citations"][0]["source_publisher"], "Example Publisher")
        self.assertEqual(payload["citations"][0]["evidence_class"], "company_practice_reference")
        self.assertEqual(payload["citations"][0]["reference_applicability"], "External example only.")
        self.assertEqual(payload["token_usage"]["total"]["total_tokens"], 264)

    def test_action_suggestion_api_mode_builds_internal_question_and_domain_metadata(self):
        report, classifier = Mock(), Mock()
        report.run.return_value = AgentResult(answer="No recommendation", agent="report")
        with (
            patch("app.main.KnowledgeAgent", return_value=Mock()),
            patch("app.main.SQLAnalyticsAgent", return_value=Mock()),
            patch("app.main.HybridAgent", return_value=Mock()),
            patch("app.main.DashboardAgent", return_value=Mock()),
            patch("app.main.IntentClassifier", return_value=classifier),
            patch("app.main.ReportAgent", return_value=report),
            patch("app.main.AgentRunRepository", return_value=Mock()),
        ):
            payload = _answer_documents(
                AskRequest(decision_suggestions=True, business_decision_domain="inventory_allocation"),
                {"sub": "admin-test", "role": "admin"},
            )

        request = report.run.call_args.args[0]
        self.assertEqual(request.question, "Generate conditional management actions from available Commerce observations.")
        self.assertEqual(request.metadata["business_decision_domain"], "inventory_allocation")
        self.assertTrue(request.metadata["decision_suggestions"])
        classifier.classify.assert_not_called()
        self.assertEqual(payload["agent"], "report")

    def test_commerce_question_api_returns_auto_detected_domain(self):
        report, classifier = Mock(), Mock()
        report.run.return_value = AgentResult(answer="Inventory evidence [C1]", agent="report")
        classifier.classify_commerce_domain.return_value = "inventory_allocation"
        with (
            patch("app.main.KnowledgeAgent", return_value=Mock()),
            patch("app.main.SQLAnalyticsAgent", return_value=Mock()),
            patch("app.main.HybridAgent", return_value=Mock()),
            patch("app.main.DashboardAgent", return_value=Mock()),
            patch("app.main.IntentClassifier", return_value=classifier),
            patch("app.main.ReportAgent", return_value=report),
            patch("app.main.AgentRunRepository", return_value=Mock()),
        ):
            payload = _answer_documents(
                AskRequest(question="Should inventory be reallocated?", commerce_decision_support=True),
                {"sub": "analyst-test", "role": "analyst"},
            )

        self.assertEqual(report.run.call_args.args[0].metadata["business_decision_domain"], "inventory_allocation")
        self.assertEqual(payload["business_decision_domain"], "inventory_allocation")
        self.assertTrue(payload["business_domain_auto_detected"])

    def test_commerce_question_api_returns_clarification_without_running_agents(self):
        report, classifier = Mock(), Mock()
        classifier.classify_commerce_domain.return_value = None
        unused = Mock()
        with (
            patch("app.main.KnowledgeAgent", return_value=unused),
            patch("app.main.SQLAnalyticsAgent", return_value=unused),
            patch("app.main.HybridAgent", return_value=unused),
            patch("app.main.DashboardAgent", return_value=unused),
            patch("app.main.IntentClassifier", return_value=classifier),
            patch("app.main.ReportAgent", return_value=report),
            patch("app.main.AgentRunRepository", return_value=Mock()),
        ):
            payload = _answer_documents(
                AskRequest(question="What should we improve?", commerce_decision_support=True),
                {"sub": "analyst-test", "role": "analyst"},
            )

        self.assertEqual(payload["agent"], "commerce_domain_router")
        self.assertTrue(payload["needs_domain_clarification"])
        report.run.assert_not_called()
        unused.run.assert_not_called()

    def test_ask_api_preserves_dashboard_visualization_and_verified_citations(self):
        answer = AgentResult(
            answer="Revenue trend [M1] [M2]", agent="dashboard",
            metadata={"token_usage": {"total": {"total_tokens": 1}}},
            evidence=[Evidence(
                citation_id="M1", source_type="verified_metric", source="FY2023 net revenue",
                content="Audited source quote", metadata={"document_id": "AR23", "page_number": 12,
                                                          "source_chunk_id": 90, "chunk_index": 4,
                                                          "source_content_hash": "sha256:abc"},
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
        citation = next(item for item in payload["citations"] if item["id"] == "M1")
        self.assertEqual(citation["source_chunk_id"], 90)
        self.assertEqual(citation["chunk_index"], 4)
        self.assertEqual(citation["source_content_hash"], "sha256:abc")
        self.assertNotIn("token_usage", payload)

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

    def test_business_decision_workflow_accepts_only_commerce_domains(self):
        request = AskRequest(
            question="How should we review inventory allocation?",
            business_decision_domain="inventory_allocation",
        )
        self.assertEqual(request.business_decision_domain, "inventory_allocation")
        promotion = AskRequest(
            question="Compare tagged and untagged promotions", business_decision_domain="promotion_planning",
        )
        self.assertEqual(promotion.business_decision_domain, "promotion_planning")
        with self.assertRaises(ValidationError):
            AskRequest(question="Which market needs diligence?", business_decision_domain="milk_supply")

    def test_conditional_suggestion_mode_needs_no_user_question_but_requires_a_domain(self):
        request = AskRequest(decision_suggestions=True, business_decision_domain="inventory_allocation")
        self.assertEqual(request.question, "")
        self.assertTrue(request.decision_suggestions)
        with self.assertRaises(ValidationError):
            AskRequest()
        with self.assertRaises(ValidationError):
            AskRequest(decision_suggestions=True)

    def test_access_matrix_matches_actual_role_capabilities(self):
        matrix = access_matrix({"sub": "admin"})
        permissions = {row["role"]: set(row["permissions"]) for row in matrix["roles"]}
        self.assertEqual(permissions, ROLE_PERMISSIONS)
        self.assertIn("view_agent_monitoring", permissions["admin"])
        self.assertNotIn("view_agent_monitoring", permissions["employee"])
        self.assertNotIn("view_agent_monitoring", permissions["document_uploader"])
        self.assertEqual(set(_roles_with_permission("view_analytics")), {"finance_analyst", "sustainability_analyst", "operations", "executive", "admin"})
        self.assertNotIn("view_analytics", permissions["employee"])
        self.assertIn("manage_knowledge", permissions["admin"])
        self.assertNotIn("manage_knowledge", permissions["finance_analyst"])

    def test_admin_can_remove_and_restore_a_source_from_retrieval(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
        }
        repository = Mock()
        repository.set_knowledge_base_active.return_value = True
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             TestClient(app) as client:
            self.assertEqual(client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            }).status_code, 200)
            response = client.patch("/api/admin/knowledge-documents/SHOPIFY-1", json={"active": False})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"document_id": "SHOPIFY-1", "active": False})
        repository.set_knowledge_base_active.assert_called_once_with("SHOPIFY-1", False)

    def test_analyst_cannot_change_knowledge_base_sources(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ANALYST_USERNAME": "analyst-test",
            "DEMO_ANALYST_PASSWORD": "analyst-password",
        }
        with patch.dict("os.environ", environment, clear=False), TestClient(app) as client:
            self.assertEqual(client.post("/api/auth/login", json={
                "username": "analyst-test", "password": "analyst-password",
            }).status_code, 200)
            response = client.patch("/api/admin/knowledge-documents/SHOPIFY-1", json={"active": False})
        self.assertEqual(response.status_code, 403)

    def test_only_admin_can_open_manifest_registered_synthetic_policy_pdf(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
            "DEMO_ANALYST_USERNAME": "analyst-test",
            "DEMO_ANALYST_PASSWORD": "analyst-password",
        }
        with patch.dict("os.environ", environment, clear=False), TestClient(app) as client:
            self.assertEqual(client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            }).status_code, 200)
            response = client.get("/api/admin/knowledge-documents/CD-POL-INV-001/source")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "application/pdf")
            self.assertIn("inline", response.headers["content-disposition"])
            self.assertTrue(response.content.startswith(b"%PDF-"))
            self.assertEqual(client.get(
                "/api/admin/knowledge-documents/UNKNOWN/source",
            ).status_code, 404)

            client.post("/api/auth/logout")
            self.assertEqual(client.post("/api/auth/login", json={
                "username": "analyst-test", "password": "analyst-password",
            }).status_code, 200)
            self.assertEqual(client.get(
                "/api/admin/knowledge-documents/CD-POL-INV-001/source",
            ).status_code, 403)

    def test_knowledge_status_request_rejects_unknown_fields(self):
        with self.assertRaises(ValidationError):
            KnowledgeBaseStatusRequest(active=False, delete_source=True)

    def test_uploader_can_upload_without_analytics_or_admin_review(self):
        self.assertTrue(upload_capability({"role": "document_uploader"})["can_upload"])
        self.assertNotIn("/api/business-metrics/parser-profiles", {
            route.path for route in app_main.app.routes
        })
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

    def test_tester_is_separate_from_document_acl_and_has_only_ocr_lab_permissions(self):
        self.assertNotIn("tester", DOCUMENT_ROLES)
        self.assertEqual(ROLE_PERMISSIONS["tester"], {"run_ocr_tests", "review_ocr_tests"})
        with patch.dict("os.environ", {
            "DEMO_TESTER_USERNAME": "ocr-tester",
            "DEMO_TESTER_PASSWORD": "test-password",
        }, clear=False):
            self.assertEqual(_role_accounts()["ocr-tester"], ("test-password", "tester"))

    def test_tester_can_run_ocr_without_corpus_access_or_production_ingestion(self):
        from unittest.mock import MagicMock
        import fitz

        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_TESTER_USERNAME": "ocr-tester",
            "DEMO_TESTER_PASSWORD": "test-password",
        }
        pdf = fitz.open()
        for _ in range(43):
            pdf.new_page(width=300, height=400)
        pdf_bytes = pdf.tobytes()
        pdf.close()
        parsed = {"chunks": [{"text": "Sample text", "metadata": {"page_number": 1}}], "tables": []}
        repository = MagicMock()
        with (
            patch("app.main._require_same_origin"),
            patch.dict("os.environ", environment, clear=False),
            patch("core.document_processing.processors.document_processor.DocumentProcessor") as processor,
            patch("core.database.ocr_test_repository.OcrTestRepository", return_value=repository),
        ):
            processor.return_value.process.return_value = parsed
            upload = Mock(filename="scan.pdf")
            upload.read = AsyncMock(return_value=pdf_bytes)
            response = asyncio.run(app_main.create_ocr_test(
                request=None,
                file=upload,
                tesseract_psm=11, tesseract_table_psm=3,
                render_scale=3.5, table_render_scale=3.5,
                user={"sub": "ocr-tester", "role": "tester"},
            ))

        self.assertEqual(response["page_count"], 43)
        self.assertEqual(response["chunk_count"], 1)
        self.assertEqual(processor.call_args.args[0]["ocr_render_scale"], 3.5)
        self.assertEqual(processor.call_args.args[0]["ocr_table_render_scale"], 3.5)
        repository.save_run.assert_called_once()
        self.assertEqual(repository.save_run.call_args.kwargs["chunks"], parsed["chunks"])
        self.assertEqual(len(repository.save_run.call_args.kwargs["page_previews"]), 43)

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

    def test_admin_can_request_exact_indexed_metric_source_chunk(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
        }
        parsed = Mock()
        indexed = Mock()
        indexed.get_document_chunk.return_value = {
            "chunk_index": 413, "content": "Exact linked indexed source passage", "metadata": {},
        }
        with patch.dict("os.environ", environment, clear=False), \
             patch("core.database.processed_chunks_repository.ProcessedChunksRepository", return_value=parsed), \
             patch("core.database.document_chunks_repository.DocumentChunkRepository", return_value=indexed), \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.get("/api/admin/processing/VNM-SR-2025-EN/chunks?stage=indexed&source_chunk_id=9021")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stage"], "indexed")
        self.assertEqual(response.json()["chunks"][0]["content"], "Exact linked indexed source passage")
        parsed.get_document.assert_not_called()
        indexed.get_document_chunk.assert_called_once_with(
            9021, "VNM-SR-2025-EN", company=CORPUS_COMPANY,
        )
        indexed.close.assert_called_once()
        parsed.close.assert_not_called()

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

    def test_admin_can_inspect_company_scoped_metric_extraction_history(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
        }
        repository = Mock()
        repository.business_metric_extraction_runs.return_value = [{
            "id": 1, "document_id": "UPLOAD-1", "decision_domain": "milk_supply",
            "status": "completed", "audit": {"chunk_decisions": []},
        }]
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.get(
                "/api/admin/processing/UPLOAD-1/business-metric-extraction-runs"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["runs"][0]["status"], "completed")
        repository.business_metric_extraction_runs.assert_called_once_with(
            "UPLOAD-1", app_main.CORPUS_COMPANY,
        )
        repository.close.assert_called_once()

    def test_admin_can_replay_saved_chunks_for_a_selected_decision_domain(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
        }
        repository = Mock()
        repository.pdf_for_metric_extraction.return_value = {
            "document_id": "UPLOAD-1", "company": CORPUS_COMPANY,
            "title": "Annual report", "domain": "finance_and_operations",
            "document_type": "annual_report", "fiscal_year": "2024",
            "source_url": None, "allowed_roles": ["admin"],
        }
        repository.save_business_metric_extraction_run.return_value = 42
        parsed = Mock()
        parsed.get_document.return_value = [{
            "chunk_index": 0, "content": "Revenue reached 100 VND in 2024.",
            "metadata": {"page_number": 1, "layout_type": "text"},
        }]
        store = Mock()
        store.get_document_tables.return_value = []
        provider = Mock(model_name="test-provider")
        candidate = {"source_chunk_index": 0, "metric_name": "domestic_consolidated_net_revenue_growth"}
        page = {"page_number": 1, "chunks": [{
            "chunk_index": 0, "selection_signals": {"domain_relevance_score": 1},
        }], "llm_metrics_returned": 1, "llm_metrics_accepted": 1}
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             patch("core.database.processed_chunks_repository.ProcessedChunksRepository", return_value=parsed), \
             patch("core.database.structured_store.StructuredDataStore", return_value=store), \
             patch("core.llm.groq_provider.GroqProvider", return_value=provider), \
             patch("core.analytics.business_metric_extraction.extract_business_metric_candidates", return_value=([candidate], [page])) as extractor, \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.post(
                "/api/admin/processing/UPLOAD-1/business-metric-extraction-runs",
                json={"decision_domain": "milk_supply", "metric_name": "farmer_raw_milk_purchased"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run_id"], 42)
        self.assertEqual(response.json()["candidate_count"], 1)
        repository.pdf_for_metric_extraction.assert_called_once_with("UPLOAD-1", CORPUS_COMPANY)
        parsed.get_document.assert_called_once_with("UPLOAD-1", company=CORPUS_COMPANY)
        repository.save_business_metric_candidates.assert_called_once_with([candidate], entered_by="parser")
        repository.save_business_metric_extraction_run.assert_called_once()
        self.assertEqual(extractor.call_args.kwargs["metric_names"], ["farmer_raw_milk_purchased"])
        repository.close.assert_called_once()

    def test_replay_rejects_metric_that_does_not_belong_to_selected_domain(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
        }
        with patch.dict("os.environ", environment, clear=False), TestClient(app) as client:
            client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            })
            response = client.post(
                "/api/admin/processing/UPLOAD-1/business-metric-extraction-runs",
                json={"decision_domain": "market_performance", "metric_name": "dairy_cattle_herd_size"},
            )

        self.assertEqual(response.status_code, 422)

    def test_employee_cannot_replay_saved_chunks(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_VIEWER_USERNAME": "viewer-test",
            "DEMO_VIEWER_PASSWORD": "viewer-password",
        }
        repository = Mock()
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "viewer-test", "password": "viewer-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.post(
                "/api/admin/processing/UPLOAD-1/business-metric-extraction-runs",
                json={"decision_domain": "milk_supply", "metric_name": "farmer_raw_milk_purchased"},
            )

        self.assertEqual(response.status_code, 403)
        repository.pdf_for_metric_extraction.assert_not_called()

    def test_employee_cannot_inspect_metric_extraction_history(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_VIEWER_USERNAME": "viewer-test",
            "DEMO_VIEWER_PASSWORD": "viewer-password",
        }
        repository = Mock()
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "viewer-test", "password": "viewer-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.get(
                "/api/admin/processing/UPLOAD-1/business-metric-extraction-runs"
            )

        self.assertEqual(response.status_code, 403)
        repository.business_metric_extraction_runs.assert_not_called()

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
        repository.uploaded_source.assert_called_once_with(
            "UPLOAD-1", company=CORPUS_COMPANY, role="admin", username="admin-test",
        )
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

    def test_finance_analyst_can_open_source_when_document_role_allows_it(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ANALYST_USERNAME": "analyst-test",
            "DEMO_ANALYST_PASSWORD": "analyst-password",
        }
        repository = Mock()
        repository.uploaded_source.return_value = {
            "title": "Finance report", "format": "PDF", "storage_path": "UPLOAD-2/report.pdf",
        }
        storage = Mock()
        storage.storage.from_.return_value.download.return_value = b"%PDF-1.7 finance"
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             patch("app.main._storage_client", return_value=(storage, "enterprise-documents")), \
             TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "analyst-test", "password": "analyst-password",
            })
            self.assertEqual(login.status_code, 200)
            response = client.get("/api/documents/UPLOAD-2/source#page=3")

        self.assertEqual(response.status_code, 200)
        repository.uploaded_source.assert_called_once_with(
            "UPLOAD-2", company=CORPUS_COMPANY,
            role="finance_analyst", username="analyst-test",
        )
        storage.storage.from_.return_value.download.assert_called_once_with("UPLOAD-2/report.pdf")

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
