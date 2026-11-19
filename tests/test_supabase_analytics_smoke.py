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
            ("SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue, "
             "SUM(s.cogs) AS cogs FROM commerce.sales AS s WHERE s.date >= $1 "
             "AND s.date < $2 GROUP BY 1 LIMIT 20", ["2022-01-01", "2023-01-01"]),
            ("SELECT o.order_status, COUNT(DISTINCT o.order_id) AS order_count "
             "FROM commerce.orders AS o GROUP BY o.order_status LIMIT 20", []),
            ("SELECT p.category, COUNT(*) AS products FROM commerce.products AS p "
             "GROUP BY p.category LIMIT 20", []),
        ]

    def generate(self, prompt):
        if prompt.startswith("Extract only the user-requested business intent."):
            question = json.loads(prompt.split("\n", 1)[1])["question"]
            if question.startswith("Show monthly revenue"):
                intent = {
                    "operation": "trend", "metrics": ["revenue", "cogs"],
                    "dimensions": [], "time_grain": "month",
                    "time_scope": {"mode": "range", "ranges": [
                        {"start": "2022-01-01", "end_exclusive": "2023-01-01"}]},
                }
            elif question.startswith("Count orders"):
                intent = {
                    "operation": "aggregate", "metrics": ["order_count"],
                    "dimensions": ["order_status"],
                    "time_scope": {"mode": "all", "ranges": []},
                }
            else:
                intent = {
                    "operation": "aggregate", "metrics": [],
                    "unverified_metric_request": "product count", "dimensions": ["category"],
                    "time_scope": {"mode": "all", "ranges": []},
                }
            return json.dumps({"intent": {
                "original_question": question, "unverified_metric_request": None,
                "filters": [], "requested_sources": [], "explicit_source_restriction": False,
                "geographic_basis": None, "geographic_coverage": None, "ranking": None,
                "unresolved_slots": [], **intent,
            }})
        if prompt.startswith('Interpret the question BEFORE'):
            return json.dumps({'domain':'other'})
        if not getattr(self, "pending_summary", False):
            sql, parameters = self.plans.pop(0)
            self.pending_summary = True
            return json.dumps({"sql": sql, "parameters": parameters})
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
