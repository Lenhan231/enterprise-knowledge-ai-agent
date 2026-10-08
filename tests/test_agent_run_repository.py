import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.database.agent_run_repository import AgentRunRepository


class AgentRunRepositoryTest(unittest.TestCase):
    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"})
    @patch("core.database.agent_run_repository.connect_database")
    def test_record_event_persists_only_telemetry_fields(self, connect):
        connection = connect.return_value
        repository = AgentRunRepository()
        repository.record_event(
            actor_role="finance_analyst", agent_name="knowledge",
            retrieval_method="hybrid", status="completed", elapsed_ms=125,
            citation_count=2, error_type=None,
        )

        cursor = connection.cursor.return_value.__enter__.return_value
        query, params = cursor.execute.call_args.args
        self.assertIn("agent_run_events", query)
        self.assertNotIn("question", query.lower())
        self.assertNotIn("prompt", query.lower())
        self.assertEqual(params, ("finance_analyst", "knowledge", "hybrid", "completed", 125, 2, None))

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"})
    @patch("core.database.agent_run_repository.connect_database")
    def test_monitoring_snapshot_reads_bounded_window_and_recent_limit(self, connect):
        connection = connect.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"total_runs": 2, "success_rate": 50.0}
        cursor.fetchall.side_effect = [[{"agent_name": "knowledge", "total_runs": 2}], [{"id": 2}]]
        snapshot = AgentRunRepository().monitoring_snapshot()

        statements = [call.args[0].lower() for call in cursor.execute.call_args_list]
        self.assertEqual(len(statements), 3)
        self.assertTrue(all("now() - interval '24 hours'" in query for query in statements))
        self.assertIn("limit 100", statements[-1])
        self.assertEqual(snapshot["summary"]["total_runs"], 2)
        self.assertEqual(snapshot["recent_runs"], [{"id": 2}])

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"})
    @patch("core.database.agent_run_repository.close_database_connection")
    @patch("core.database.agent_run_repository.connect_database")
    def test_close_returns_connection_to_pool(self, connect, close):
        connection = connect.return_value
        repository = AgentRunRepository()
        repository.close()
        close.assert_called_once_with(connection)


if __name__ == "__main__":
    unittest.main()
