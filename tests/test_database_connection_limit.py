from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.database import connection_limit
from core.database import document_chunks_repository


class DatabaseConnectionLimitTest(unittest.TestCase):
    def setUp(self):
        self.original_slots = connection_limit._slots
        self.original_leased = connection_limit._leased.copy()
        connection_limit._slots = threading.BoundedSemaphore(1)
        connection_limit._leased.clear()

    def tearDown(self):
        connection_limit._slots = self.original_slots
        connection_limit._leased.clear()
        connection_limit._leased.update(self.original_leased)

    def test_waiting_checkout_proceeds_after_connection_is_closed(self):
        first, second = Mock(), Mock()
        connect = Mock(side_effect=[first, second])
        with patch.object(connection_limit.psycopg, "connect", connect):
            held = connection_limit.connect_database("postgresql://example")
            finished = threading.Event()

            def checkout_and_return():
                borrowed = connection_limit.connect_database("postgresql://example")
                connection_limit.close_database_connection(borrowed)
                finished.set()

            worker = threading.Thread(target=checkout_and_return)
            worker.start()
            self.assertFalse(finished.wait(0.1))
            self.assertEqual(connect.call_count, 1)
            connection_limit.close_database_connection(held)
            self.assertTrue(finished.wait(2))
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(connect.call_count, 2)

    def test_connect_failure_releases_the_slot(self):
        with patch.object(
            connection_limit.psycopg, "connect",
            side_effect=[connection_limit.psycopg.OperationalError("offline"), Mock()],
        ):
            with self.assertRaises(connection_limit.psycopg.OperationalError):
                connection_limit.connect_database("postgresql://example")
            connection = connection_limit.connect_database("postgresql://example")
            connection_limit.close_database_connection(connection)

    def test_repeated_close_does_not_release_another_connection_slot(self):
        connection = Mock()
        with patch.object(connection_limit.psycopg, "connect", return_value=connection):
            leased = connection_limit.connect_database("postgresql://example")
            connection_limit.close_database_connection(leased)
            connection_limit.close_database_connection(leased)
            next_connection = connection_limit.connect_database("postgresql://example")
            connection_limit.close_database_connection(next_connection)

    def test_vector_registration_failure_closes_the_new_connection(self):
        connection = Mock()
        with (
            patch.dict("os.environ", {"DATABASE_URL": "postgresql://example"}),
            patch.object(document_chunks_repository, "connect_database", return_value=connection),
            patch.object(document_chunks_repository, "register_vector", side_effect=RuntimeError("missing vector")),
            patch.object(document_chunks_repository, "close_database_connection") as close,
        ):
            with self.assertRaisesRegex(RuntimeError, "missing vector"):
                document_chunks_repository.DocumentChunkRepository()
            close.assert_called_once_with(connection)


if __name__ == "__main__":
    unittest.main()
