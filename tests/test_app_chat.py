import sys
import unittest
from unittest.mock import patch
from pathlib import Path

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.main import create_app
from core.models.agents import AgentResult, Evidence, VerifiedIdentity


ANALYST = VerifiedIdentity(subject="analyst-1", permissions={"analytics:read"})


def verified_analyst(_request):
    return ANALYST


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
                                   knowledge_agent=Knowledge(),
                                   identity_resolver=verified_analyst)) as client:
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

        with patch.dict("os.environ", {"APP_ENV": "production"}, clear=False), TestClient(
            create_app(chat_agent=agent)
        ) as client:
            response = client.post("/api/chat", json={
                "question": "Doanh thu tháng 12/2022",
            })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["agent"], "analytics")
        self.assertEqual(payload["evidence"][0]["source"], "commerce.sales")
        self.assertEqual(agent.requests[0].question, "Doanh thu tháng 12/2022")
        self.assertIsNone(agent.requests[0].user_id)

    def test_verified_identity_is_server_derived_and_client_user_id_is_rejected(self):
        agent = FakeChatAgent()

        with TestClient(create_app(chat_agent=agent, identity_resolver=verified_analyst)) as client:
            accepted = client.post("/api/chat", json={"question": "Doanh thu tháng 12/2022"})
            spoofed = client.post("/api/chat", json={
                "question": "Doanh thu tháng 12/2022",
                "user_id": "admin",
            })

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(agent.requests[0].identity.subject, "analyst-1")
        self.assertEqual(agent.requests[0].user_id, "analyst-1")
        self.assertEqual(spoofed.status_code, 422)

    def test_explicit_local_development_identity_allows_browser_testing(self):
        agent = FakeChatAgent()
        with patch.dict("os.environ", {
            "APP_ENV": "development",
            "ALLOW_DEV_ANALYTICS": "true",
            "DEV_ANALYTICS_IDENTITY": "local-analyst",
        }, clear=False):
            with TestClient(create_app(chat_agent=agent)) as client:
                response = client.post("/api/chat", json={"question": "Doanh thu thÃ¡ng 12/2022"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(agent.requests[0].identity.subject, "local-analyst")
        self.assertEqual(agent.requests[0].user_id, "local-analyst")

    def test_local_identity_requires_development_environment(self):
        agent = FakeChatAgent()
        with patch.dict("os.environ", {
            "APP_ENV": "production",
            "ALLOW_DEV_ANALYTICS": "true",
            "DEV_ANALYTICS_IDENTITY": "local-analyst",
        }, clear=False):
            with TestClient(create_app(chat_agent=agent)) as client:
                response = client.post("/api/chat", json={"question": "Doanh thu thÃ¡ng 12/2022"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(agent.requests[0].identity)

    def test_unauthenticated_analytics_is_denied_but_policy_stays_on_knowledge_path(self):
        class Repository:
            async def revenue_cogs_by_month(self, start, end):
                raise AssertionError("unauthenticated analytics must not execute")

            async def close(self):
                pass

        class Knowledge:
            async def run(self, request):
                return AgentResult(answer="Theo chính sách đã truy xuất.", agent="knowledge")

            async def close(self):
                pass

        with patch.dict("os.environ", {"APP_ENV": "production"}, clear=False), TestClient(create_app(
            commerce_repository=Repository(),
            knowledge_agent=Knowledge(),
        )) as client:
            denied = client.post("/api/chat", json={"question": "Doanh thu tháng 12/2022"})
            policy = client.post("/api/chat", json={"question": "Chính sách nghỉ phép quy định gì?"})

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(policy.status_code, 200)
        self.assertEqual(policy.json()["agent"], "knowledge")

    def test_verified_full_chat_path_runs_basic_lookup_outside_legacy_operations(self):
        class Repository:
            async def execute_approved_query(self, sql, *parameters):
                self.executed = (sql, parameters)
                return [{
                    "product_id": 42,
                    "product_name": "DragonWear MA-42",
                    "category": "Outdoor",
                    "segment": "Women",
                    "size": "M",
                    "color": "Blue",
                    "price": 125,
                    "cogs": 80,
                }]

            async def close(self):
                pass

        repository = Repository()
        with TestClient(create_app(
            commerce_repository=repository,
            knowledge_agent=object(),
            identity_resolver=verified_analyst,
        )) as client:
            response = client.post("/api/chat", json={"question": "Thông tin sản phẩm mã 42"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["agent"], "analytics")
        self.assertEqual(response.json()["data"]["rows"][0]["product_id"], 42)
        self.assertNotIn("SELECT", response.text)

    def test_full_chat_path_handles_monthly_minimum_ambiguity_and_region_subset(self):
        class Repository:
            async def revenue_cogs_by_month(self, start, end):
                return [
                    {"month": "2022-01-01", "revenue": 100, "cogs": 40},
                    {"month": "2022-02-01", "revenue": 30, "cogs": 20},
                ]

            async def revenue_by_region(self, start, end):
                return [
                    {"region": "East", "revenue": 60},
                    {"region": "Central", "revenue": 30},
                    {"region": "West", "revenue": 10},
                ]

            async def close(self):
                pass

        with TestClient(create_app(
            commerce_repository=Repository(),
            knowledge_agent=object(),
            identity_resolver=verified_analyst,
        )) as client:
            lowest = client.post("/api/chat", json={
                "question": "Doanh thu thấp nhất theo tháng trong năm 2022"
            })
            ambiguous = client.post("/api/chat", json={
                "question": "doanh thu thấp nhất 2022"
            })
            regions = client.post("/api/chat", json={
                "question": "So sánh doanh thu East và West tháng 12/2022"
            })

        self.assertIn("02/2022", lowest.json()["answer"])
        self.assertIn("ngày hay tháng", ambiguous.json()["answer"])
        self.assertEqual(
            {row["region"] for row in regions.json()["data"]["table"]["rows"]},
            {"East", "West"},
        )

    def test_full_chat_path_reports_empty_lookup_explicitly(self):
        class Repository:
            async def execute_approved_query(self, sql, *parameters):
                return []

            async def close(self):
                pass

        with TestClient(create_app(
            commerce_repository=Repository(),
            knowledge_agent=object(),
            identity_resolver=verified_analyst,
        )) as client:
            response = client.post("/api/chat", json={
                "question": "Thông tin sản phẩm mã 999999"
            })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["metadata"]["ok"])
        self.assertIn("Không tìm thấy", response.json()["answer"])

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
