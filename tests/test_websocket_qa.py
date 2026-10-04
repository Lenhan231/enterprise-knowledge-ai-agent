import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import httpx
from openai import RateLimitError

from fastapi.testclient import TestClient
from fastapi import HTTPException
from starlette.websockets import WebSocketDisconnect
from core.models.agents import AgentResult, Evidence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.main import AskRequest, _answer_documents, app


class WebSocketQATest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-long-enough-123",
            "DEMO_ANALYST_USERNAME": "analyst",
            "DEMO_ANALYST_PASSWORD": "analyst-password",
            "DEMO_VIEWER_USERNAME": "viewer",
            "DEMO_VIEWER_PASSWORD": "viewer-password",
            "DEMO_ADMIN_USERNAME": "admin",
            "DEMO_ADMIN_PASSWORD": "admin-password",
            "DEMO_UPLOADER_USERNAME": "uploader",
            "DEMO_UPLOADER_PASSWORD": "uploader-password",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.addCleanup(self.client_context.__exit__, None, None, None)

    def login(self, username="analyst", password="analyst-password"):
        response = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200)

    def test_websocket_returns_status_then_shared_qa_response(self):
        expected = {
            "answer": "Grounded result [S1]", "citations": [], "agent": "knowledge", "data": None,
            "question_sql_fallback": "provider_rate_limited",
        }
        self.login()
        with patch("app.main._answer_documents", return_value=expected) as answer:
            with self.client.websocket_connect("/ws/ask") as websocket:
                websocket.send_json({"question": "What does the report say?", "retrieval_method": "hybrid"})
                self.assertEqual(websocket.receive_json(), {"type": "status", "status": "processing"})
                self.assertEqual(websocket.receive_json(), {"type": "answer", **expected})
        answer.assert_called_once()
        self.assertEqual(answer.call_args.args[1]["role"], "finance_analyst")

    def test_generated_analytics_decimal_and_citation_are_json_safe_over_http_and_websocket(self):
        agent_result = AgentResult(
            answer="Verified revenue was 61,824 billion VND [M1].", agent="analytics",
            evidence=[Evidence(
                citation_id="M1", source_type="verified_metric", source="Vinamilk 2024 revenue",
                content="Total consolidated revenue 61,824 billion VND",
                metadata={"company": "Vinamilk", "document_id": "AR24", "page_number": 12,
                          "source_url": "https://example.test/ar24"},
            )],
            data={"results": [{"total": Decimal("61824.00")} ]},
        )
        self.login()
        with patch("app.main.KnowledgeAgent"), patch("app.main.SQLAnalyticsAgent"), \
             patch("app.main.HybridAgent"), patch("app.main.DashboardAgent"), \
             patch("app.main.IntentClassifier"), patch("app.main.ReportAgent"), \
             patch("app.main.AgentRouter") as router, patch("app.main.AgentRunRepository"):
            router.return_value.route.return_value = agent_result
            response = self.client.post("/api/ask", json={"question": "Revenue in 2024?"})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["data"]["results"][0]["total"], 61824.0)
            self.assertEqual(body["citations"][0]["id"], "M1")
            with self.client.websocket_connect("/ws/ask") as websocket:
                websocket.send_json({"question": "Revenue in 2024?"})
                websocket.receive_json()
                message = websocket.receive_json()
                self.assertEqual(message["type"], "answer")
                self.assertEqual(message["data"]["results"][0]["total"], 61824.0)

    def test_commerce_sql_citation_exposes_generated_query_for_review(self):
        result = AgentResult(
            answer="The grouped result and vetted overlap are shown below [C1][C2].", agent="report",
            evidence=[
                Evidence(
                    citation_id="C1", source_type="commerce_sql", source="Commerce SQL",
                    content='question_specific_query question-specific SQL observations: '
                            '[{"category": "Shoes", "units_sold": 42}]',
                    metadata={
                        "company": "Commerce Demo", "source_tables": ["commerce.inventory"],
                        "commerce_observation_group": "question_specific_query",
                        "commerce_observations": [{"category": "Shoes", "units_sold": 42}],
                        "sql_query": "SELECT i.category, SUM(i.units_sold) AS units_sold FROM commerce.inventory i GROUP BY i.category",
                    },
                ),
                Evidence(
                    citation_id="C2", source_type="commerce_sql", source="Commerce SQL aggregate",
                    content='inventory_latest_flag_overlap aggregate observations: [{"both_flagged_rows": 232}]',
                    metadata={
                        "company": "Commerce Demo", "source_tables": ["commerce.inventory"],
                        "commerce_aggregate_key": "inventory_latest_flag_overlap",
                        "commerce_observation_group": "inventory_latest_flag_overlap",
                        "commerce_observations": [{"both_flagged_rows": 232}],
                    },
                ),
            ],
        )
        self.login()
        with patch("app.main.KnowledgeAgent"), patch("app.main.SQLAnalyticsAgent"), \
             patch("app.main.HybridAgent"), patch("app.main.DashboardAgent"), \
             patch("app.main.IntentClassifier"), patch("app.main.ReportAgent"), \
             patch("app.main.AgentRouter") as router, patch("app.main.AgentRunRepository"):
            router.return_value.route.return_value = result
            response = self.client.post("/api/ask", json={"question": "Which category moved fastest?"})

        self.assertEqual(response.status_code, 200)
        citations = {item["id"]: item for item in response.json()["citations"]}
        self.assertEqual(citations["C1"]["source_tables"], ["commerce.inventory"])
        self.assertIn("SUM(i.units_sold)", citations["C1"]["sql_query"])
        self.assertEqual(citations["C2"]["commerce_aggregate_key"], "inventory_latest_flag_overlap")
        self.assertIsNone(citations["C2"]["sql_query"])
        self.assertEqual(citations["C1"]["commerce_observations"], [{"category": "Shoes", "units_sold": 42}])
        self.assertEqual(citations["C2"]["commerce_observations"], [{"both_flagged_rows": 232}])

    def test_http_exposes_commerce_query_fallback_reason(self):
        result = AgentResult(
            answer="Using the bounded snapshot because SQL generation was rate-limited [C1].",
            agent="report",
            metadata={
                "question_sql_fallback": "provider_rate_limited",
                "generation_provider": "deterministic_safety_fallback",
            },
        )
        self.login()
        with patch("app.main.KnowledgeAgent"), patch("app.main.SQLAnalyticsAgent"), \
             patch("app.main.HybridAgent"), patch("app.main.DashboardAgent"), \
             patch("app.main.IntentClassifier"), patch("app.main.ReportAgent"), \
             patch("app.main.AgentRouter") as router, patch("app.main.AgentRunRepository"):
            router.return_value.route.return_value = result
            response = self.client.post("/api/ask", json={
                "question": "Compare recent inventory signals by category?",
                "business_decision_domain": "inventory_allocation",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["question_sql_fallback"], "provider_rate_limited")
        self.assertEqual(response.json()["generation_provider"], "deterministic_safety_fallback")

    def test_http_marks_report_withheld_for_unverified_citations(self):
        result = AgentResult(
            answer="The answer was withheld because its citations could not be verified. Please retry the question.",
            agent="report",
            metadata={"citation_validation_failed": True},
        )
        self.login()
        with patch("app.main.KnowledgeAgent"), patch("app.main.SQLAnalyticsAgent"), \
             patch("app.main.HybridAgent"), patch("app.main.DashboardAgent"), \
             patch("app.main.IntentClassifier"), patch("app.main.ReportAgent"), \
             patch("app.main.AgentRouter") as router, patch("app.main.AgentRunRepository"):
            router.return_value.route.return_value = result
            response = self.client.post("/api/ask", json={"question": "Summarize the report"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["citation_validation_failed"])
        self.assertEqual(response.json()["citations"], [])

    def test_websocket_validates_request_without_dropping_session(self):
        self.login()
        with self.client.websocket_connect("/ws/ask") as websocket:
            websocket.send_json({"question": "x", "retrieval_method": "unfiltered"})
            message = websocket.receive_json()
            self.assertEqual(message["type"], "error")
            self.assertTrue(message["detail"])

    def test_websocket_preserves_temporary_provider_rate_limit(self):
        self.login()
        with patch("app.main._answer_documents", side_effect=HTTPException(429, "Provider quota; retry later")):
            with self.client.websocket_connect("/ws/ask") as websocket:
                websocket.send_json({"question": "What does the report say?"})
                self.assertEqual(websocket.receive_json()["type"], "status")
                message = websocket.receive_json()
                self.assertEqual(message["type"], "error")
                self.assertEqual(message["status_code"], 429)
                self.assertIn("retry", message["detail"])

    def test_shared_qa_handler_maps_provider_rate_limit_to_http_429(self):
        response = httpx.Response(429, request=httpx.Request("POST", "https://provider.example"))
        rate_error = RateLimitError("quota", response=response, body={})
        with patch("app.main.KnowledgeAgent"), patch("app.main.SQLAnalyticsAgent"), \
             patch("app.main.HybridAgent"), patch("app.main.DashboardAgent"), \
             patch("app.main.IntentClassifier"), patch("app.main.ReportAgent"), \
             patch("app.main.AgentRouter") as router, patch("app.main.AgentRunRepository") as monitor:
            router.return_value.route.side_effect = rate_error
            router.return_value.last_destination = "knowledge"
            with self.assertRaises(HTTPException) as caught:
                _answer_documents(AskRequest(question="What does the report say?"), {"sub": "analyst", "role": "finance_analyst"})
        self.assertEqual(caught.exception.status_code, 429)
        monitor.return_value.record_event.assert_called_once()
        self.assertEqual(monitor.return_value.record_event.call_args.kwargs["status"], "rate_limited")
        self.assertEqual(monitor.return_value.record_event.call_args.kwargs["agent_name"], "knowledge")

    def test_websocket_requires_authenticated_session(self):
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.client.websocket_connect("/ws/ask"):
                pass
        self.assertEqual(caught.exception.code, 4401)

    def test_uploader_cannot_use_document_qa_websocket(self):
        self.login("uploader", "uploader-password")
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.client.websocket_connect("/ws/ask"):
                pass
        self.assertEqual(caught.exception.code, 4403)

    def test_websocket_rejects_cross_origin_handshake(self):
        self.login()
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.client.websocket_connect("/ws/ask", headers={"origin": "https://attacker.example"}):
                pass
        self.assertEqual(caught.exception.code, 4403)

    def test_agent_monitoring_api_is_admin_only(self):
        self.login("analyst", "analyst-password")
        self.assertEqual(self.client.get("/api/admin/agent-monitoring").status_code, 403)
        self.login("admin", "admin-password")
        snapshot = {"summary": {"total_runs": 0}, "by_agent": [], "recent_runs": []}
        with patch("app.main.AgentRunRepository") as repository:
            repository.return_value.monitoring_snapshot.return_value = snapshot
            response = self.client.get("/api/admin/agent-monitoring")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), snapshot)
        repository.return_value.close.assert_called_once()

if __name__ == "__main__":
    unittest.main()
