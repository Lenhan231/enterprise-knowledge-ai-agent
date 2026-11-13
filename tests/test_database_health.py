"""The page picks the faster backend with /api/health/db; it must time a real query and stay signed-in only."""

from contextlib import ExitStack
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.main import app, _issue_token


class DatabaseHealthTest(unittest.TestCase):
    def setUp(self):
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.dict(os.environ, {
            "AUTH_SECRET_KEY": "test-only-secret-for-database-health-32-chars",
            "EMBEDDING_PRELOAD": "0", "RERANKER_PRELOAD": "0",
        }))
        self.connection = MagicMock()
        self.connect = stack.enter_context(patch("core.database.connection_limit.connect_database", return_value=self.connection))
        self.close = stack.enter_context(patch("core.database.connection_limit.close_database_connection"))
        self.client = stack.enter_context(TestClient(app))
        self.headers = {"Authorization": "Bearer " + _issue_token("employee-test", "employee")}

    def test_signed_in_user_gets_the_database_round_trip_time(self):
        response = self.client.get("/api/health/db", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json()["database_ms"], int)
        self.connection.execute.assert_called_once_with("select 1")
        self.close.assert_called_once_with(self.connection)

    def test_anonymous_callers_cannot_open_connections(self):
        self.assertEqual(self.client.get("/api/health/db").status_code, 401)
        self.connect.assert_not_called()

    def test_unreachable_database_is_a_503_and_the_slot_is_released(self):
        self.connection.execute.side_effect = RuntimeError("network down")
        self.assertEqual(self.client.get("/api/health/db", headers=self.headers).status_code, 503)
        self.close.assert_called_once_with(self.connection)


if __name__ == "__main__":
    unittest.main()
