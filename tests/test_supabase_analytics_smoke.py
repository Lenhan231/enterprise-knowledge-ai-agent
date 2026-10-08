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
        self.connection = connection
        self.readonly = readonly

    async def __aenter__(self):
        self.connection.readonly_requested = self.readonly
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    readonly_requested = False

    def transaction(self, *, readonly=False):
        return FakeTransaction(self, readonly)

    async def fetchval(self, query):
        self.read_only_query = query
        return "on"

    async def execute(self, query):
        self.write_probe = query
        raise ReadOnlyViolation("cannot execute UPDATE in a read-only transaction")


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakePool:
    def __init__(self):
        self.connection = FakeConnection()

    def acquire(self):
        return FakeAcquire(self.connection)


class FakeRepository:
    def __init__(self):
        self.pool = FakePool()
        self.closed = False

    async def revenue_cogs_by_month(self, start_date, end_date):
        return [{"month": start_date, "revenue": "52454936.20", "cogs": "53489673.44"}]

    async def revenue_by_region(self, start_date, end_date):
        return [{"region": "East", "revenue": "14079268.92"}]

    async def inventory_by_category(self, snapshot_date):
        return [{
            "category": "Casual",
            "products_observed": 40,
            "stockout_products": 31,
            "reorder_products": 0,
        }]

    async def close(self):
        self.closed = True


class SupabaseAnalyticsSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_probe_requires_read_only_transaction_and_blocks_write(self):
        repository = FakeRepository()

        result = await verify_read_only(repository)

        self.assertTrue(repository.pool.connection.readonly_requested)
        self.assertEqual(result, {
            "transaction_read_only": "on",
            "write_probe_blocked": True,
            "write_probe_sqlstate": "25006",
        })
        self.assertIn("WHERE FALSE", repository.pool.connection.write_probe)

    async def test_smoke_covers_all_live_cases_and_model_contract(self):
        repository = FakeRepository()

        report = await run_smoke(repository=repository)

        self.assertEqual(
            [case["id"] for case in CASES],
            ["revenue_cogs_2022_12", "revenue_by_region_2022_12", "inventory_2022_12_31"],
        )
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["passed_cases"], 3)
        self.assertTrue(all(row["agent_result"] for row in report["cases"]))
        self.assertTrue(all(row["evidence_valid"] for row in report["cases"]))
        self.assertTrue(all(row["expected_values_valid"] for row in report["cases"]))
        self.assertTrue(report["read_only"]["write_probe_blocked"])
        self.assertTrue(repository.closed)


if __name__ == "__main__":
    unittest.main()
