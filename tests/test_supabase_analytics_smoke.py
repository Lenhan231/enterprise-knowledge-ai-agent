import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from scripts.smoke_test_supabase_analytics import CASES, run_smoke, verify_read_only


class ReadOnlyViolation(RuntimeError):
    sqlstate = "25006"


class FakeTransaction:
    def __init__(self, connection, readonly):
        self.connection, self.readonly = connection, readonly

    async def __aenter__(self):
        self.connection.readonly_requested = self.readonly
        return self

    async def __aexit__(self, *_args):
        return False


class FakeConnection:
    def transaction(self, *, readonly=False):
        return FakeTransaction(self, readonly)

    async def fetchval(self, _query):
        return "on"

    async def execute(self, query):
        self.write_probe = query
        raise ReadOnlyViolation()


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


class FakePool:
    def __init__(self):
        self.connection = FakeConnection()

    def acquire(self):
        return FakeAcquire(self.connection)


class FakeRepository:
    def __init__(self):
        self.pool, self.calls, self.closed = FakePool(), [], False

    async def execute_approved_query(self, sql, *parameters):
        self.calls.append((sql, parameters))
        return [{"value": len(self.calls)}]

    async def close(self):
        self.closed = True


class FakeLLM:
    def __init__(self):
        self.plans = [
            ("commerce.sales", "SUM(s.revenue) AS revenue, SUM(s.cogs) AS cogs"),
            ("commerce.orders", "COUNT(*) AS orders"),
            ("commerce.products", "COUNT(*) AS products"),
        ]

    def generate(self, _prompt):
        if not getattr(self, "pending_summary", False):
            table, expression = self.plans.pop(0)
            self.pending_summary = True
            alias = {"commerce.sales": "s", "commerce.orders": "o", "commerce.products": "p"}[table]
            return json.dumps({"sql": f"SELECT {expression} FROM {table} AS {alias} LIMIT 20", "parameters": []})
        self.pending_summary = False
        return "The query returned rows."


class SupabaseAnalyticsSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_probe_requires_read_only_transaction_and_blocks_write(self):
        repository = FakeRepository()
        result = await verify_read_only(repository)
        self.assertTrue(repository.pool.connection.readonly_requested)
        self.assertTrue(result["write_probe_blocked"])
        self.assertIn("WHERE FALSE", repository.pool.connection.write_probe)

    async def test_smoke_uses_generic_generated_queries_and_model_contract(self):
        repository = FakeRepository()
        report = await run_smoke(repository=repository, llm=FakeLLM())
        self.assertEqual(len(CASES), 3)
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["passed_cases"], 3)
        self.assertEqual(len(repository.calls), 3)
        self.assertTrue(repository.closed)


if __name__ == "__main__":
    unittest.main()
