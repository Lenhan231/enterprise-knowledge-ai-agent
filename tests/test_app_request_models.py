import sys
import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import app.main as app_main
from app.main import CORPUS_COMPANY, DOCUMENT_ROLES, ROLE_PERMISSIONS, AskRequest, DocumentAccessRequest, KnowledgeBaseStatusRequest, _answer_documents, _commerce_reference_metadata, _referenced_citation_ids, _role_accounts, _roles_with_permission, access_matrix, app, require_permission, upload_capability
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
        method = _commerce_reference_metadata(
            ["promotion_planning"], "Nielsen Norman Group", "management_cookbook_reference",
            "General experimentation method; not Commerce Demo policy",
        )
        self.assertEqual(method["evidence_class"], "management_cookbook_reference")
        self.assertFalse(method["external_policy_reference"])
        self.assertFalse(method["external_business_reference"])
        self.assertTrue(method["commerce_reference_active"])

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
             patch("core.document_processing.document_processor.DocumentProcessor", return_value=processor) as processor_class, \
             patch("core.embeddings.embedding_service.EmbeddingService", return_value=embedding), \
             patch("core.database.document_chunks_repository.DocumentChunkRepository") as chunks_repo, \
             patch("core.database.processed_chunks_repository.ProcessedChunksRepository"), \
             patch("core.database.structured_store.StructuredDataStore"), \
             patch("core.tokenization.token_counter.TokenCounter") as token_counter, \
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
            content="Example Retailer reported its 2024 strategy and risks.",
            metadata={"document_id": "EXAMPLE-AR-2024-VI", "page_number": 20,
                      "source_url": "https://example.com/report.pdf",
                      "synthetic_company_policy": True,
                      "text_extraction_method": "tesseract",
                      "ocr": {"engine": "tesseract", "language": "vie+eng", "page_psm": 11, "render_scale": 1.5},
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
            "Summarize Example Retailer's 2024 strategy and risks for executive decision support"
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
                AskRequest(question="Summarize Example Retailer's 2024 strategy and risks for executive decision support"),
                {"sub": "admin-test", "role": "admin"},
            )

        report_factory.assert_called_once_with(knowledge=knowledge, analytics=analytics)
        report.run.assert_called_once()
        hybrid.run.assert_not_called()
        analytics.run.assert_not_called()
        self.assertEqual(payload["agent"], "report")
        self.assertEqual([item["document_id"] for item in payload["citations"]], ["EXAMPLE-AR-2024-VI"])
        self.assertEqual(payload["citations"][0]["source_publisher"], "Example Publisher")
        self.assertEqual(payload["citations"][0]["evidence_class"], "company_practice_reference")
        self.assertEqual(payload["citations"][0]["reference_applicability"], "External example only.")
        self.assertTrue(payload["citations"][0]["synthetic_company_policy"])
        self.assertEqual(payload["citations"][0]["text_extraction_method"], "tesseract")
        self.assertEqual(payload["citations"][0]["ocr"]["engine"], "tesseract")
        self.assertEqual(payload["token_usage"]["total"]["total_tokens"], 264)

    def test_action_suggestion_api_mode_builds_internal_question_and_domain_metadata(self):
        report, classifier, hybrid, dashboard = Mock(), Mock(), Mock(), Mock()
        report.run.return_value = AgentResult(
            answer="No recommendation", agent="report",
            metadata={"answer_fallback_reason": "provider_unavailable"},
        )
        with (
            patch("app.main.KnowledgeAgent", return_value=Mock()),
            patch("app.main.SQLAnalyticsAgent", return_value=Mock()),
            patch("app.main.HybridAgent", return_value=hybrid),
            patch("app.main.DashboardAgent", return_value=dashboard),
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
        hybrid.assert_not_called()
        dashboard.assert_not_called()
        self.assertEqual(payload["agent"], "report")
        self.assertEqual(payload["business_decision_domain"], "inventory_allocation")
        self.assertTrue(payload["decision_suggestions_fallback"])

    def test_natural_action_suggestion_response_marks_fallback_for_ui(self):
        report, classifier = Mock(), Mock()
        report.run.return_value = AgentResult(
            answer="One bounded next step [C1][S1]", agent="report",
            metadata={"answer_fallback_reason": "provider_rate_limited", "decision_suggestions": True},
        )
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
                AskRequest(
                    question="Suggest up to three conditional actions for promotion planning.",
                    business_decision_domain="promotion_planning",
                    commerce_decision_support=True,
                ),
                {"sub": "analyst-test", "role": "finance_analyst"},
            )

        self.assertTrue(report.run.call_args.args[0].metadata["decision_suggestions"])
        self.assertTrue(payload["decision_suggestions_fallback"])

    def test_commerce_question_api_returns_auto_detected_domain(self):
        report, classifier = Mock(), Mock()
        report.run.return_value = AgentResult(
            answer="Inventory evidence [C1]", agent="report",
            metadata={"citation_validation_failed": True,
                      "decision_validation_failure": "decision_numeric_claim_not_present_in_cited_evidence",
                      "decision_validation_numeric_tokens": ["0.12", "25"],
                      "answer_fallback_reason": "provider_unavailable"},
        )
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
            admin_payload = _answer_documents(
                AskRequest(question="Should inventory be reallocated?", commerce_decision_support=True),
                {"sub": "admin-test", "role": "admin"},
            )

        self.assertEqual(report.run.call_args.args[0].metadata["business_decision_domain"], "inventory_allocation")
        self.assertEqual(payload["business_decision_domain"], "inventory_allocation")
        self.assertTrue(payload["business_domain_auto_detected"])
        self.assertTrue(payload["citation_validation_failed"])
        self.assertEqual(payload["answer_fallback_reason"], "provider_unavailable")
        self.assertNotIn("decision_validation_failure", payload)
        self.assertNotIn("decision_validation_numeric_tokens", payload)

        self.assertEqual(
            admin_payload["decision_validation_failure"],
            "decision_numeric_claim_not_present_in_cited_evidence",
        )
        self.assertEqual(admin_payload["decision_validation_numeric_tokens"], ["0.12", "25"])

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
                                                          "retrieval_chunk_id": "AR23::chunk::4",
                                                          "source_content_hash": "sha256:abc"},
            ), Evidence(
                citation_id="M2", source_type="verified_metric", source="FY2024 net revenue",
                content="Audited source quote", metadata={"document_id": "AR24", "page_number": 12,
                                                          "chunk_index": 5, "source_sha256": "sha256:def"},
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
        self.assertEqual(citation["retrieval_chunk_id"], "AR23::chunk::4")
        self.assertEqual(citation["chunk_index"], 4)
        self.assertEqual(citation["source_content_hash"], "sha256:abc")
        citation = next(item for item in payload["citations"] if item["id"] == "M2")
        self.assertEqual(citation["source_content_hash"], "sha256:def")
        self.assertNotIn("token_usage", payload)

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
            AskRequest(question="Which market needs diligence?", business_decision_domain="unknown_domain")

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

    def test_admin_can_update_existing_document_reader_roles(self):
        repository = Mock()
        repository.set_document_allowed_roles.return_value = True
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "PATCH", "scheme": "http", "path": "/", "raw_path": b"/",
            "query_string": b"", "root_path": "", "headers": [(b"host", b"testserver")],
            "server": ("testserver", 80), "client": ("testclient", 80),
        }
        with patch("app.main.DocumentRepository", return_value=repository):
            response = app_main.set_knowledge_document_access(
                "SHOPIFY-1", DocumentAccessRequest(allowed_roles=["employee", "procurement"]),
                Request(scope), {"role": "admin"},
            )
        self.assertEqual(response, {
            "document_id": "SHOPIFY-1", "allowed_roles": ["employee", "procurement"],
        })
        repository.set_document_allowed_roles.assert_called_once_with(
            "SHOPIFY-1", ["employee", "procurement"],
        )

    def test_document_reader_role_update_is_admin_only_over_http(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
            "DEMO_ANALYST_USERNAME": "analyst-test",
            "DEMO_ANALYST_PASSWORD": "analyst-password",
        }
        repository = Mock()
        repository.set_document_allowed_roles.return_value = True
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             TestClient(app) as client:
            self.assertEqual(client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            }).status_code, 200)
            allowed = client.patch(
                "/api/admin/knowledge-documents/SHOPIFY-1/access",
                json={"allowed_roles": ["employee", "procurement"]},
            )
            client.post("/api/auth/logout")
            self.assertEqual(client.post("/api/auth/login", json={
                "username": "analyst-test", "password": "analyst-password",
            }).status_code, 200)
            denied = client.patch(
                "/api/admin/knowledge-documents/SHOPIFY-1/access",
                json={"allowed_roles": ["employee"]},
            )

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json(), {
            "document_id": "SHOPIFY-1", "allowed_roles": ["employee", "procurement"],
        })
        self.assertEqual(denied.status_code, 403)
        repository.set_document_allowed_roles.assert_called_once_with(
            "SHOPIFY-1", ["employee", "procurement"],
        )

    def test_document_access_rejects_empty_or_unknown_role_lists(self):
        for roles in ([], ["tester"], ["employee", "employee"]):
            with self.subTest(roles=roles), self.assertRaises(ValidationError):
                DocumentAccessRequest(allowed_roles=roles)

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

    def test_analyst_can_open_allowed_active_synthetic_policy_and_uploader_cannot(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ANALYST_USERNAME": "analyst-test",
            "DEMO_ANALYST_PASSWORD": "analyst-password",
            "DEMO_UPLOADER_USERNAME": "uploader-test",
            "DEMO_UPLOADER_PASSWORD": "uploader-password",
        }
        repository = Mock()
        repository.uploaded_source.return_value = None
        repository.accessible_synthetic_policy_source.side_effect = lambda _id, company, role: (
            {"title": "Inventory policy", "format": "PDF"}
            if role == "finance_analyst" and company == CORPUS_COMPANY else None
        )
        with patch.dict("os.environ", environment, clear=False), \
             patch("app.main.DocumentRepository", return_value=repository), \
             patch("app.main._storage_client") as storage_client, \
             TestClient(app) as client:
            self.assertEqual(client.post("/api/auth/login", json={
                "username": "analyst-test", "password": "analyst-password",
            }).status_code, 200)
            allowed = client.get("/api/documents/CD-POL-INV-001/source")
            client.post("/api/auth/logout")
            self.assertEqual(client.post("/api/auth/login", json={
                "username": "uploader-test", "password": "uploader-password",
            }).status_code, 200)
            denied = client.get("/api/documents/CD-POL-INV-001/source")

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.headers["content-type"], "application/pdf")
        self.assertTrue(allowed.content.startswith(b"%PDF-"))
        self.assertEqual(allowed.headers["cache-control"], "private, no-store")
        self.assertEqual(denied.status_code, 404)
        repository.accessible_synthetic_policy_source.assert_any_call(
            "CD-POL-INV-001", company=CORPUS_COMPANY, role="finance_analyst",
        )
        repository.accessible_synthetic_policy_source.assert_any_call(
            "CD-POL-INV-001", company=CORPUS_COMPANY, role="document_uploader",
        )
        storage_client.assert_not_called()

    def test_knowledge_status_request_rejects_unknown_fields(self):
        with self.assertRaises(ValidationError):
            KnowledgeBaseStatusRequest(active=False, delete_source=True)

    def test_uploader_can_upload_without_analytics_or_admin_review(self):
        self.assertTrue(upload_capability({"role": "document_uploader"})["can_upload"])
        self.assertNotIn("/api/business-metrics/parser-profiles", {
            route.path for route in app_main.app.routes
        })
        self.assertNotIn("view_analytics", ROLE_PERMISSIONS["document_uploader"])
        self.assertNotIn("ask_documents", ROLE_PERMISSIONS["document_uploader"])
        self.assertNotIn("review_metrics", ROLE_PERMISSIONS["document_uploader"])
        self.assertNotIn("manage_access", ROLE_PERMISSIONS["document_uploader"])
        self.assertNotIn("document_uploader", _roles_with_permission("review_metrics"))

    def test_document_uploader_is_denied_document_question_route(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_UPLOADER_USERNAME": "uploader-test",
            "DEMO_UPLOADER_PASSWORD": "uploader-password",
        }
        with patch.dict("os.environ", environment, clear=False), TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "uploader-test", "password": "uploader-password",
            })
            response = client.post("/api/ask", json={"question": "Summarize a document"})

        self.assertEqual(login.status_code, 200)
        self.assertEqual(response.status_code, 403)

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
        self.assertEqual(ROLE_PERMISSIONS["tester"], {"run_upload_tests", "review_upload_tests"})
        with patch.dict("os.environ", {
            "DEMO_TESTER_USERNAME": "ocr-tester",
            "DEMO_TESTER_PASSWORD": "test-password",
        }, clear=False):
            self.assertEqual(_role_accounts()["ocr-tester"], ("test-password", "tester"))

    def test_tester_can_run_upload_test_without_corpus_access_or_production_ingestion(self):
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
            patch("core.document_processing.document_processor.DocumentProcessor") as processor,
            patch("core.database.upload_test_repository.UploadTestRepository", return_value=repository),
            patch("core.embeddings.embedding_service.EmbeddingService") as embedding_service_class,
            patch("core.tokenization.token_counter.TokenCounter") as token_counter_class,
            patch("core.tokenization.embedding_chunker.build_embedding_chunks") as build_embedding_chunks,
        ):
            processor.return_value.process.return_value = parsed
            processor.return_value.prepare_upload_test_output.return_value = parsed
            token_counter_class.return_value.count.return_value = 2
            build_embedding_chunks.return_value = [{"text": "Sample text", "metadata": {"page_number": 1, "token_count": 2}}]
            upload = Mock(filename="scan.pdf")
            upload.read = AsyncMock(return_value=pdf_bytes)
            response = asyncio.run(app_main.create_upload_test(
                request=None,
                file=upload,
                ocr_language="vie+eng",
                tesseract_psm=11, tesseract_table_psm=3,
                render_scale=3.5, table_render_scale=3.5,
                parser_engine="pymupdf_tesseract",
                thresholding_method=0, lstm_rating_coefficient=5,
                tessdata_variant="system", layout_detector="none",
                chunking_strategy="sentence", chunk_size=1100, chunk_overlap=120,
                layout_image_size=640, layout_confidence_threshold=0.30,
                paddle_device="cpu", paddle_render_scale=1.5,
                paddle_formula_recognition=False, paddle_chart_recognition=False,
                mineru_force_ocr=False, mineru_page_range="",
                paddle_layout=False,
                user={"sub": "ocr-tester", "role": "tester"},
            ))

        self.assertEqual(response["page_count"], 43)
        self.assertEqual(response["chunk_count"], 1)
        self.assertEqual(response["token_bounded_chunk_count"], 1)
        self.assertEqual(response["embedding_status"], "not_run")
        self.assertEqual(processor.call_args.args[0]["ocr_render_scale"], 3.5)
        self.assertEqual(processor.call_args.args[0]["ocr_table_render_scale"], 3.5)
        repository.save_run.assert_called_once()
        embedding_service_class.assert_not_called()
        self.assertEqual(repository.save_run.call_args.kwargs["chunks"], parsed["chunks"])
        self.assertEqual(repository.save_run.call_args.kwargs["embeddings"], [])
        self.assertEqual(repository.save_run.call_args.kwargs["token_bounded_chunks"][0]["text"], "Sample text")
        self.assertEqual(len(repository.save_run.call_args.kwargs["page_previews"]), 43)

    def test_upload_test_http_persists_rotated_scan_outputs_outside_corpus(self):
        from io import BytesIO
        import fitz
        from PIL import Image

        fixture = Path(__file__).resolve().parents[1] / "data/evaluation/ocr/commerce_synthetic_policy_scan_demo.pdf"
        source = fitz.open(fixture)
        pixmap = source[1].get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        source.close()
        sideways = Image.open(BytesIO(pixmap.tobytes("png"))).rotate(90, expand=True)
        image_bytes = BytesIO()
        sideways.save(image_bytes, format="PNG")
        pdf = fitz.open()
        page = pdf.new_page(width=sideways.width / 2.5, height=sideways.height / 2.5)
        page.insert_image(page.rect, stream=image_bytes.getvalue())
        pdf_bytes = pdf.tobytes()
        pdf.close()

        repository = Mock()
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_TESTER_USERNAME": "ocr-tester",
            "DEMO_TESTER_PASSWORD": "test-password",
        }
        with (
            patch.dict("os.environ", environment, clear=False),
            patch("core.database.upload_test_repository.UploadTestRepository", return_value=repository),
            patch("core.tokenization.token_counter.TokenCounter") as token_counter_class,
            patch("core.tokenization.embedding_chunker.build_embedding_chunks") as build_embedding_chunks,
            TestClient(app) as client,
        ):
            token_counter_class.return_value.count.return_value = 2
            build_embedding_chunks.return_value = [{"text": "Final text", "metadata": {"page_number": 1, "token_count": 2}}]
            login = client.post("/api/auth/login", json={
                "username": "ocr-tester", "password": "test-password",
            })
            self.assertEqual(login.status_code, 200)
            invalid_language = client.post(
                "/api/upload-tests",
                headers={"Origin": "http://testserver"},
                data={"ocr_language": "deu"},
                files={"file": ("rotated-synthetic-scan.pdf", pdf_bytes, "application/pdf")},
            )
            response = client.post(
                "/api/upload-tests",
                headers={"Origin": "http://testserver"},
                data={"ocr_language": "eng"},
                files={"file": ("rotated-synthetic-scan.pdf", pdf_bytes, "application/pdf")},
            )

        self.assertEqual(invalid_language.status_code, 422)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["table_count"], 1)
        self.assertEqual(response.json()["embedding_status"], "not_run")
        repository.save_run.assert_called_once()
        saved = repository.save_run.call_args.kwargs
        self.assertEqual(len(saved["page_previews"]), 1)
        self.assertEqual(saved["tables"][0]["metadata"]["ocr"]["orientation_correction_degrees"], 90)
        self.assertEqual(saved["tables"][0]["metadata"]["ocr"]["language"], "eng")
        self.assertEqual(len(saved["tables"][0]["rows"]), 3)
        self.assertEqual(saved["tables"][0]["rows"][0]["Avg fee units"], "42.50")
        self.assertEqual(saved["embeddings"], [])

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
            response = client.get("/api/admin/processing/COMMERCE-REF-2025/chunks?stage=indexed&source_chunk_id=9021")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stage"], "indexed")
        self.assertEqual(response.json()["chunks"][0]["content"], "Exact linked indexed source passage")
        parsed.get_document.assert_not_called()
        indexed.get_document_chunk.assert_called_once_with(
            9021, "COMMERCE-REF-2025", company=CORPUS_COMPANY,
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
