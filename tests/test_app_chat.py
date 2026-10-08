import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.main import create_app
from core.models.agents import AgentResult, Evidence


class FakeChatAgent:
    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return AgentResult(
            answer="Doanh thu tháng 12/2022 đã được phân tích.",
            agent="analytics",
            evidence=[Evidence(
                citation_id="S1",
                source_type="database",
                source="commerce.sales",
                metadata={"period": "2022-12-01:2023-01-01"},
            )],
            data={"operation": "revenue_cogs_by_month", "rows": [{"revenue": 100}]},
            metadata={"ok": True},
        )


class ChatAPITest(unittest.TestCase):
    def test_default_chat_routes_analytics_and_knowledge(self):
        class Repository:
            async def revenue_cogs_by_month(self, start, end):
                return [{"month": "2022-12-01", "revenue": 100, "cogs": 60}]

            async def close(self):
                pass

        class Knowledge:
            async def run(self, request):
                return AgentResult(answer="Theo tài liệu: có quy trình phê duyệt.", agent="knowledge")

            async def close(self):
                pass

        with TestClient(create_app(commerce_repository=Repository(),
                                   knowledge_agent=Knowledge())) as client:
            analytics = client.post("/api/chat", json={"question": "Doanh thu tháng 12/2022"})
            knowledge = client.post("/api/chat", json={"question": "Quy trình phê duyệt là gì?"})
            policy = client.post("/api/chat", json={"question": "Chính sách tồn kho quy định gì?"})

        self.assertEqual(analytics.status_code, 200)
        self.assertEqual(analytics.json()["agent"], "analytics")
        self.assertEqual(knowledge.status_code, 200)
        self.assertEqual(knowledge.json()["agent"], "knowledge")
        self.assertEqual(policy.json()["agent"], "knowledge")

    def test_chat_returns_agent_result_and_evidence(self):
        agent = FakeChatAgent()

        with TestClient(create_app(chat_agent=agent)) as client:
            response = client.post("/api/chat", json={
                "question": "Doanh thu tháng 12/2022",
                "user_id": "tester",
            })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["agent"], "analytics")
        self.assertEqual(payload["evidence"][0]["source"], "commerce.sales")
        self.assertEqual(agent.requests[0].question, "Doanh thu tháng 12/2022")
        self.assertEqual(agent.requests[0].user_id, "tester")

    def test_chat_rejects_blank_or_oversized_questions(self):
        with TestClient(create_app(chat_agent=FakeChatAgent())) as client:
            blank = client.post("/api/chat", json={"question": "   "})
            oversized = client.post("/api/chat", json={"question": "x" * 2001})

        self.assertEqual(blank.status_code, 422)
        self.assertEqual(oversized.status_code, 422)

    def test_chat_rejects_unknown_fields_and_unbounded_metadata(self):
        with TestClient(create_app(chat_agent=FakeChatAgent())) as client:
            unknown = client.post("/api/chat", json={
                "question": "Doanh thu tháng 12/2022",
                "sql": "DROP TABLE commerce.sales",
            })
            excessive_metadata = client.post("/api/chat", json={
                "question": "Doanh thu tháng 12/2022",
                "metadata": {f"field_{index}": index for index in range(21)},
            })

        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(excessive_metadata.status_code, 422)

    def test_chat_hides_internal_errors(self):
        agent = FakeChatAgent(error=RuntimeError("database password leaked"))

        with TestClient(create_app(chat_agent=agent)) as client:
            response = client.post("/api/chat", json={"question": "Doanh thu tháng 12/2022"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Hệ thống tạm thời không thể xử lý yêu cầu.")
        self.assertNotIn("password", response.text)

    def test_dashboard_endpoint_is_removed_and_root_is_vietnamese_chat(self):
        with TestClient(create_app(chat_agent=FakeChatAgent())) as client:
            dashboard = client.get("/api/dashboard")
            root = client.get("/")

        self.assertEqual(dashboard.status_code, 404)
        self.assertEqual(root.status_code, 200)
        self.assertIn("Trợ lý phân tích doanh nghiệp", root.text)
        self.assertIn('id="chat-form"', root.text)


if __name__ == "__main__":
    unittest.main()
