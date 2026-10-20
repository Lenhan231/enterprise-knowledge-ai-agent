import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.main import create_app
from core.models.agents import AgentResult, VerifiedIdentity


ANALYST = VerifiedIdentity(subject="analyst-1", permissions={"analytics:read"})
SQL = "SELECT p.product_id FROM commerce.products AS p LIMIT 20"


class ChatAPITest(unittest.TestCase):
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

    def test_default_router_handles_generic_sql_mode_with_verified_identity(self):
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"product_id": 42}]

        class LLM:
            def __init__(self):
                self.responses = [json.dumps({"sql": SQL, "parameters": []}), "Found product 42."]

            def generate(self, _prompt):
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
        self.assertNotIn("SELECT", response.text)

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
