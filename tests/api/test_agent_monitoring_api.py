import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from app.main import app


class AgentMonitoringApiTest(unittest.TestCase):
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
    def test_agent_monitoring_api_is_admin_only(self):
        self.login("analyst", "analyst-password")
        self.assertEqual(self.client.get("/api/admin/agent-monitoring").status_code, 403)
        self.login("admin", "admin-password")
        snapshot = {"summary": {"total_runs": 0}, "by_agent": [], "recent_runs": []}
        with patch("core.database.agent_run_repository.AgentRunRepository") as repository:
            repository.return_value.monitoring_snapshot.return_value = snapshot
            response = self.client.get("/api/admin/agent-monitoring")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), snapshot)
        repository.return_value.close.assert_called_once()

if __name__ == "__main__":
    unittest.main()
