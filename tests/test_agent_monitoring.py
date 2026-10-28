import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import ANY, AsyncMock, Mock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import app.main as app_main
from app.agents import _record_agent_run
from core.models.agents import AgentResult


class AgentMonitoringTest(unittest.TestCase):
    def test_chat_defaults_to_agentic_routing(self):
        from app.agents import AgentChatRequest, agent_chat

        runtime = Mock()
        runtime.run_mode = AsyncMock(return_value=AgentResult(answer="Answer", agent="agentic"))
        with patch("app.agents._get_runtime", new=AsyncMock(return_value=runtime)), \
                patch("app.agents._record_agent_run"):
            result = asyncio.run(agent_chat(
                AgentChatRequest(question="Explain the returns policy"),
                Mock(), user={"role": "admin", "sub": "admin-test"},
            ))

        runtime.run_mode.assert_awaited_once_with(ANY, "agentic")
        runtime.run.assert_not_called()
        self.assertEqual(result.agent, "agentic")

    def test_admin_can_read_monitoring_snapshot(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
        }
        repository = Mock()
        repository.monitoring_snapshot.return_value = {
            "summary": {"total_runs": 2}, "by_agent": [], "recent_runs": [],
        }
        with patch.dict("os.environ", environment, clear=False), \
                patch("core.database.agent_run_repository.AgentRunRepository", return_value=repository), \
                TestClient(app_main.app) as client:
            client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            })
            response = client.get("/api/admin/agent-monitoring")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["total_runs"], 2)
        repository.close.assert_called_once()

    def test_telemetry_failure_does_not_escape_agent_request_cleanup(self):
        repository = Mock()
        repository.close.side_effect = RuntimeError("close failed")
        event = {
            "actor_role": "admin", "agent_name": "knowledge",
            "retrieval_method": "hybrid", "status": "completed",
            "elapsed_ms": 12, "citation_count": 1, "error_type": None,
        }
        with patch("core.database.agent_run_repository.AgentRunRepository", return_value=repository):
            _record_agent_run(**event)

        repository.record_event.assert_called_once_with(**event)

    def test_agent_chat_records_privacy_minimized_run(self):
        environment = {
            "AUTH_SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "DEMO_ADMIN_USERNAME": "admin-test",
            "DEMO_ADMIN_PASSWORD": "admin-password",
        }
        runtime = Mock()
        runtime.run_mode = AsyncMock(return_value=AgentResult(
            answer="Grounded answer", agent="knowledge",
        ))
        with patch.dict("os.environ", environment, clear=False), \
                patch("app.agents._get_runtime", new=AsyncMock(return_value=runtime)), \
                patch("app.agents._record_agent_run") as record, \
                TestClient(app_main.app) as client:
            client.post("/api/auth/login", json={
                "username": "admin-test", "password": "admin-password",
            })
            response = client.post("/api/agents/chat", json={
                "question": "Test question", "agent_mode": "knowledge",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["agent"], "knowledge")
        record.assert_called_once()
        self.assertEqual(record.call_args.kwargs["agent_name"], "knowledge")
        self.assertEqual(record.call_args.kwargs["status"], "completed")
        self.assertEqual(record.call_args.kwargs["citation_count"], 0)


if __name__ == "__main__":
    unittest.main()
