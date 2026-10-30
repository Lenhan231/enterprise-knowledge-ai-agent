import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.dashboard_agent import InventoryDashboardAgent
from core.agents.sql_analytics_agent import AnalyticsPermissionDenied
from core.analytics.text_to_sql import validate_commerce_sql
from core.models.agents import AgentRequest, VerifiedIdentity


class InventoryDashboardTest(unittest.IsolatedAsyncioTestCase):
    def repository(self):
        repo = MagicMock()

        async def query(sql, *parameters):
            if "MAX(i.snapshot_date)" in sql:
                return [{"snapshot_date": "2022-12-31"}]
            if "AS sku_count" in sql:
                return [{"sku_count": 20, "stockout_rate": 10.0, "overstock_rate": 25.0,
                         "mean_fill_rate": 0.9, "high_days_of_supply_count": 5}]
            if "AS stockout_rate" in sql:
                return [{"category": "A", "stockout_rate": 10.0}]
            if "AS both_flags_count" in sql:
                return [{"category": "A", "stockout_flag_count": 2,
                         "overstock_flag_count": 5, "both_flags_count": 1}]
            return [{"product_id": "P1", "product_name": "Product 1", "category": "A",
                     "stock_on_hand": 10, "days_of_supply": 45,
                     "stockout_flag": False, "overstock_flag": True, "reorder_flag": False}]

        repo.execute_approved_query.side_effect = query
        return repo

    async def test_requires_verified_analytics_identity(self):
        with self.assertRaises(AnalyticsPermissionDenied):
            await InventoryDashboardAgent(self.repository()).run(AgentRequest(question="inventory"))

    async def test_returns_snapshot_scoped_sections_from_read_only_queries(self):
        repo = self.repository()
        result = await InventoryDashboardAgent(repo).run(AgentRequest(
            question="inventory", metadata={"category": "A"},
            identity=VerifiedIdentity(subject="analyst", permissions={"analytics:read"}),
        ))
        dashboard = result.data["dashboard"]
        self.assertEqual(dashboard["outline_id"], "inventory_control")
        self.assertEqual(dashboard["snapshot_date"], "2022-12-31")
        self.assertEqual(dashboard["kpis"]["sku_count"], 20)
        self.assertEqual(dashboard["exceptions"][0]["product_id"], "P1")
        self.assertEqual(repo.execute_approved_query.call_count, 5)
        for call in repo.execute_approved_query.call_args_list:
            self.assertEqual(validate_commerce_sql(call.args[0]).sources, ("commerce.inventory",))
        for call in repo.execute_approved_query.call_args_list[1:]:
            self.assertEqual(call.args[1:], ("2022-12-31", "A"))


if __name__ == "__main__":
    unittest.main()
