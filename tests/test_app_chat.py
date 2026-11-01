import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.agents.main import create_app
from core.models.agents import AgentResult, VerifiedIdentity


ANALYST = VerifiedIdentity(subject="analyst-1", permissions={"analytics:read", "documents:read"},
                           document_roles={"finance_analyst"})
SQL = "SELECT p.product_id FROM commerce.products AS p LIMIT 20"


class ChatAPITest(unittest.TestCase):
    def test_report_upload_requires_verified_analytics_identity(self):
        report = AsyncMock()
        report.generate_from_template.return_value = (
            AgentResult(answer="done", agent="report"), b"# Report\n", "text/markdown; charset=utf-8",
        )
        with TestClient(create_app(
            chat_agent=object(), report_agent=report, identity_resolver=lambda _request: None,
        )) as client:
            denied = client.post("/api/report", data={"question": "Create report"}, files={
                "template": ("report.md", b"# Report\n", "text/markdown"),
            })
        self.assertEqual(denied.status_code, 403)
        report.generate_from_template.assert_not_awaited()

    def test_report_upload_returns_rendered_markdown(self):
        report = AsyncMock()
        report.generate_from_template.return_value = (
            AgentResult(answer="done", agent="report"), b"# Report\n\nEvidence [S1].\n",
            "text/markdown; charset=utf-8",
        )
        with TestClient(create_app(
            chat_agent=object(), report_agent=report,
            identity_resolver=lambda _request: ANALYST,
        )) as client:
            response = client.post("/api/report", data={"question": "Create report"}, files={
                "template": ("report.md", b"# Report\n", "text/markdown"),
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"# Report\n\nEvidence [S1].\n")
        self.assertEqual(response.headers["content-disposition"], 'attachment; filename="report.md"')
        report.generate_from_template.assert_awaited_once()

    def test_report_upload_rejects_non_template(self):
        with TestClient(create_app(
            chat_agent=object(), report_agent=AsyncMock(),
            identity_resolver=lambda _request: ANALYST,
        )) as client:
            response = client.post("/api/report", data={"question": "Create report"}, files={
                "template": ("report.pdf", b"PDF", "application/pdf"),
            })
        self.assertEqual(response.status_code, 422)

    def test_chat_defaults_to_reranker_and_accepts_hybrid_override(self):
        class Agent:
            async def run_mode(self, request, mode):
                return AgentResult(answer=mode, agent=mode,
                                   metadata={"retrieval_method": request.metadata["retrieval_method"]})

            async def run(self, request):
                return await self.run_mode(request, "knowledge")

        with TestClient(create_app(chat_agent=Agent())) as client:
            default = client.post("/api/chat", json={"question": "test", "agent_mode": "knowledge"})
            hybrid = client.post("/api/chat", json={
                "question": "test", "agent_mode": "knowledge",
                "retrieval_method": "hybrid",
            })

        self.assertEqual(default.json()["metadata"]["retrieval_method"], "translated_hybrid_rerank")
        self.assertEqual(hybrid.json()["metadata"]["retrieval_method"], "hybrid")

    def test_selected_modes_and_legacy_auto_routing(self):
        class Agent:
            def __init__(self):
                self.modes = []
                self.automatic = 0

            async def run_mode(self, request, mode):
                self.modes.append(mode)
                return AgentResult(answer=mode, agent=mode)

            async def run(self, request):
                self.automatic += 1
                return AgentResult(answer="automatic", agent="knowledge")

        agent = Agent()
        with TestClient(create_app(chat_agent=agent)) as client:
            responses = [client.post("/api/chat", json={"question": "test", "agent_mode": mode})
                         for mode in ("knowledge", "sql", "agentic")]
            automatic = client.post("/api/chat", json={"question": "legacy request"})
            invalid = client.post("/api/chat", json={"question": "test", "agent_mode": "other"})

        self.assertEqual(agent.modes, ["knowledge", "sql", "agentic"])
        self.assertEqual(agent.automatic, 1)
        self.assertEqual([response.status_code for response in responses], [200, 200, 200])
        self.assertEqual(automatic.json()["answer"], "automatic")
        self.assertEqual(invalid.status_code, 422)

    def test_dashboard_mode_is_available_to_the_api(self):
        class Agent:
            async def run_mode(self, request, mode):
                return AgentResult(answer=mode, agent=mode)

        with TestClient(create_app(chat_agent=Agent())) as client:
            response = client.post("/api/chat", json={
                "question": "show inventory", "agent_mode": "dashboard",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["agent"], "dashboard")

    def test_default_router_handles_generic_sql_mode_with_verified_identity(self):
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"product_id": 42}]

        class LLM:
            def __init__(self):
                self.responses = [json.dumps({"sql": SQL, "parameters": []}), "Found product 42."]

            def generate(self, prompt):
                if prompt.startswith('Interpret the question BEFORE'):
                    return json.dumps({'domain':'other'})
                return self.responses.pop(0)

        with TestClient(create_app(
            commerce_repository=repository,
            knowledge_agent=AsyncMock(),
            identity_resolver=lambda _request: ANALYST,
            llm=LLM(),
        )) as client:
            response = client.post("/api/chat", json={"question": "List products", "agent_mode": "sql"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["rows"], [{"product_id": 42}])
        repository.execute_approved_query.assert_awaited_once_with(SQL)
        self.assertEqual(response.json()["data"]["sql"], SQL)
        self.assertNotIn("SELECT", response.json()["answer"])

    def test_sql_mode_requires_server_verified_permission(self):
        repository = AsyncMock()
        from unittest.mock import patch

        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            with TestClient(create_app(commerce_repository=repository)) as client:
                response = client.post("/api/chat", json={"question": "List products", "agent_mode": "sql"})

        self.assertEqual(response.status_code, 403)
        repository.execute_approved_query.assert_not_called()

    def test_chat_validation_and_removed_static_root(self):
        with TestClient(create_app(chat_agent=object())) as client:
            blank = client.post("/api/chat", json={"question": "   "})
            oversized = client.post("/api/chat", json={"question": "x" * 2001})
            unknown = client.post("/api/chat", json={"question": "test", "sql": "DROP TABLE x"})
            root = client.get("/")

        self.assertEqual(blank.status_code, 422)
        self.assertEqual(oversized.status_code, 422)
        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(root.status_code, 404)


if __name__ == "__main__":
    unittest.main()
