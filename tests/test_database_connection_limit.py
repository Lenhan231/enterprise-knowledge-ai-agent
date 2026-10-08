from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

from psycopg.rows import dict_row, tuple_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.database import connection_limit


class DatabaseConnectionLimitTest(unittest.TestCase):
    def setUp(self):
        self.original_slots = connection_limit._slots
        self.original_leased = connection_limit._leased.copy()
        self.original_pools = connection_limit._pools.copy()
        connection_limit._slots = threading.BoundedSemaphore(1)
        connection_limit._leased.clear()
        connection_limit._pools.clear()

    def tearDown(self):
        connection_limit._slots = self.original_slots
        connection_limit._leased.clear()
        connection_limit._leased.update(self.original_leased)
        connection_limit._pools.clear()
        connection_limit._pools.update(self.original_pools)

    def test_waiting_checkout_proceeds_after_connection_is_closed(self):
        first, second = Mock(), Mock()
        pool = Mock()
        pool.getconn.side_effect = [first, second]
        with patch.object(connection_limit, "_connection_pool", return_value=pool):
            held = connection_limit.connect_database("postgresql://example")
            finished = threading.Event()

            def checkout_and_return():
                borrowed = connection_limit.connect_database("postgresql://example")
                connection_limit.close_database_connection(borrowed)
                finished.set()

            worker = threading.Thread(target=checkout_and_return)
            worker.start()
            self.assertFalse(finished.wait(0.1))
            self.assertEqual(pool.getconn.call_count, 1)
            connection_limit.close_database_connection(held)
            self.assertTrue(finished.wait(2))
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(pool.getconn.call_count, 2)
            self.assertEqual(pool.putconn.call_args_list, [unittest.mock.call(held), unittest.mock.call(second)])

    def test_connect_failure_releases_the_slot(self):
        pool = Mock()
        pool.getconn.side_effect = [connection_limit.psycopg.OperationalError("offline"), Mock()]
        with patch.object(connection_limit, "_connection_pool", return_value=pool):
            with self.assertRaises(connection_limit.psycopg.OperationalError):
                connection_limit.connect_database("postgresql://example")
            connection = connection_limit.connect_database("postgresql://example")
            connection_limit.close_database_connection(connection)

    def test_repeated_close_does_not_release_another_connection_slot(self):
        connection = Mock()
        pool = Mock()
        pool.getconn.return_value = connection
        with patch.object(connection_limit, "_connection_pool", return_value=pool):
            leased = connection_limit.connect_database("postgresql://example")
            connection_limit.close_database_connection(leased)
            connection_limit.close_database_connection(leased)
            next_connection = connection_limit.connect_database("postgresql://example")
            connection_limit.close_database_connection(next_connection)
            self.assertEqual(pool.putconn.call_count, 2)

    def test_row_factory_is_reset_for_each_lease(self):
        connection = Mock()
        pool = Mock()
        pool.getconn.return_value = connection
        with patch.object(connection_limit, "_connection_pool", return_value=pool):
            mapped = connection_limit.connect_database("postgresql://example", row_factory=dict_row)
            self.assertIs(mapped.row_factory, dict_row)
            connection_limit.close_database_connection(mapped)
            tupled = connection_limit.connect_database("postgresql://example")
            self.assertIs(tupled.row_factory, tuple_row)
            connection_limit.close_database_connection(tupled)

    def test_pool_registers_pgvector_once_when_each_connection_is_created(self):
        connection, pool = Mock(), Mock()
        pool.getconn.return_value = connection
        with patch.object(connection_limit, "ConnectionPool", return_value=pool) as create_pool:
            borrowed = connection_limit.connect_database("postgresql://example")
            self.assertIs(borrowed, connection)
            self.assertIs(create_pool.call_args.kwargs["configure"], connection_limit.register_vector)
            connection_limit.close_database_connection(borrowed)


if __name__ == "__main__":
    unittest.main()
