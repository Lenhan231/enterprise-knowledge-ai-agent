import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.analytics_agent import AnalyticsAgent
from core.agents.base import BaseAgent
from core.agents.intent_classifier import IntentClassifier
from core.agents.router import AgentRouter
from core.agents.sql_analytics_agent import SQLAnalyticsAgent, payload_to_agent_result
from core.models.agents import AgentRequest, AgentResult, Evidence


class FakeCommerceRepository:
    def __init__(self):
        self.closed = False

    async def revenue_cogs_by_month(self, start_date, end_date):
        self.period = (start_date, end_date)
        return [{"month": date(2022, 12, 1), "revenue": 100, "cogs": 60}]

    async def revenue_by_region(self, start_date, end_date):
        return [{"region": "Miền Nam", "revenue": 100}]

    async def inventory_by_category(self, snapshot_date):
        self.snapshot_date = snapshot_date
        return [{
            "category": "Đồ uống",
            "products_observed": 2,
            "stockout_products": 1,
            "reorder_products": 1,
        }]

    async def close(self):
        self.closed = True


class FakeSQLAgent:
    async def run_payload(self, _request):
        return {
            "ok": True,
            "operation": "revenue_cogs_by_month",
            "rows": [{"month": "2022-12-01", "revenue": 100, "cogs": 60}],
            "evidence": [{"source": "commerce.sales", "period": "2022-12-01:2023-01-01"}],
            "metadata": {"period": "2022-12-01:2023-01-01"},
        }


class MockClassifier:
    def classify(self, question):
        return IntentClassifier.fallback(question)


class AnalyticsPayloadMappingTest(unittest.TestCase):
    def test_sql_operation_resolution_uses_vietnamese_metric_aliases(self):
        cases = {
            "Giá vốn hàng bán tháng 12/2022": "revenue_cogs_by_month",
            "Số ngày đủ hàng theo danh mục tại ngày 2022-12-31": "inventory_by_category",
            "Tỷ lệ bán hết theo danh mục tại ngày 2022-12-31": "inventory_by_category",
        }

        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertEqual(SQLAnalyticsAgent._resolve_operation(question), expected)

    def test_maps_success_payload_to_existing_agent_models(self):
        result = payload_to_agent_result({
            "ok": True,
            "operation": "revenue_cogs_by_month",
            "rows": [{"month": "2022-12-01", "revenue": 100, "cogs": 60}],
            "evidence": [{"source": "commerce.sales", "period": "2022-12-01:2023-01-01"}],
            "metadata": {"currency": "dataset_currency_unknown"},
            "analysis": "sales_performance",
            "metrics": [{"gross_profit": 40}],
            "findings": ["Doanh thu và giá vốn đã được tính."],
            "recommendations": [],
        })

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.agent, "analytics")
        self.assertIsInstance(result.evidence[0], Evidence)
        self.assertEqual(result.evidence[0].citation_id, "S1")
        self.assertEqual(result.evidence[0].source_type, "database")
        self.assertEqual(result.evidence[0].source, "commerce.sales")
        self.assertEqual(result.evidence[0].metadata["period"], "2022-12-01:2023-01-01")
        self.assertEqual(result.data["rows"][0]["revenue"], 100)
        self.assertEqual(result.data["analysis"], "sales_performance")
        self.assertIn("Doanh thu và giá vốn", result.answer)

    def test_maps_error_payload_without_dropping_limitations(self):
        result = payload_to_agent_result({
            "ok": False,
            "operation": None,
            "rows": [],
            "answer": "Vui lòng cung cấp tháng/năm.",
            "limitations": ["Missing required period in request"],
        })

        self.assertEqual(result.answer, "Vui lòng cung cấp tháng/năm.")
        self.assertEqual(result.data["rows"], [])
        self.assertEqual(result.metadata["ok"], False)
        self.assertEqual(result.metadata["limitations"], ["Missing required period in request"])
        self.assertEqual(result.evidence, [])


class AnalyticsAgentModelBoundaryTest(unittest.IsolatedAsyncioTestCase):
    async def test_sql_agent_accepts_agent_request_and_returns_agent_result(self):
        agent = SQLAnalyticsAgent(FakeCommerceRepository())

        result = await agent.run(AgentRequest(question="Doanh thu và giá vốn tháng 12/2022"))

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.agent, "sql_analytics")
        self.assertEqual(result.data["rows"][0]["revenue"], 100)
        self.assertEqual(result.evidence[0].source, "commerce.sales")

    async def test_revenue_by_region_for_december_2022(self):
        agent = SQLAnalyticsAgent(FakeCommerceRepository())

        result = await agent.run(AgentRequest(question="Doanh thu theo khu vực tháng 12/2022"))

        self.assertEqual(result.data["operation"], "revenue_by_region")
        self.assertEqual(result.data["rows"], [{"region": "Miền Nam", "revenue": 100}])
        self.assertEqual(
            [item.source for item in result.evidence],
            ["commerce.orders", "commerce.order_items", "commerce.geography"],
        )

    async def test_inventory_by_category_at_snapshot_date(self):
        repository = FakeCommerceRepository()
        agent = SQLAnalyticsAgent(repository)

        result = await agent.run(
            AgentRequest(question="Tỷ lệ bán hết theo danh mục tại ngày 2022-12-31")
        )

        self.assertEqual(result.data["operation"], "inventory_by_category")
        self.assertEqual(repository.snapshot_date, date(2022, 12, 31))

    async def test_missing_date_returns_vietnamese_agent_result(self):
        agent = SQLAnalyticsAgent(FakeCommerceRepository())

        result = await agent.run(AgentRequest(question="Doanh thu và giá vốn"))

        self.assertFalse(result.metadata["ok"])
        self.assertIn("Vui lòng cung cấp tháng/năm", result.answer)

    async def test_unsupported_metric_returns_vietnamese_agent_result(self):
        agent = SQLAnalyticsAgent(FakeCommerceRepository())

        result = await agent.run(AgentRequest(question="Tỷ lệ hoàn hàng tháng 12/2022"))

        self.assertFalse(result.metadata["ok"])
        self.assertIn("chưa được hỗ trợ", result.answer)

    async def test_database_failure_returns_safe_vietnamese_agent_result(self):
        repository = FakeCommerceRepository()
        repository.revenue_cogs_by_month = AsyncMock(side_effect=RuntimeError("secret database detail"))
        agent = SQLAnalyticsAgent(repository)

        result = await agent.run(AgentRequest(question="Doanh thu tháng 12/2022"))

        self.assertFalse(result.metadata["ok"])
        self.assertEqual(result.metadata["error_type"], "RuntimeError")
        self.assertIn("Không thể truy xuất dữ liệu", result.answer)
        self.assertNotIn("secret database detail", result.answer)

    async def test_agents_follow_base_contract_and_close_repository(self):
        repository = FakeCommerceRepository()
        sql_agent = SQLAnalyticsAgent(repository)
        analytics_agent = AnalyticsAgent(sql_agent)

        self.assertIsInstance(sql_agent, BaseAgent)
        self.assertIsInstance(analytics_agent, BaseAgent)
        await analytics_agent.close()
        self.assertTrue(repository.closed)

    async def test_router_runs_analytics_flow_end_to_end(self):
        analytics_agent = AnalyticsAgent(SQLAnalyticsAgent(FakeCommerceRepository()))
        unused = AsyncMock()
        classifier = MockClassifier()
        router = AgentRouter(classifier, unused, analytics_agent, unused, unused)

        result = await router.route(
            AgentRequest(question="Doanh thu và giá vốn tháng 12/2022")
        )

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(router.last_destination, "analytics")
        self.assertEqual(result.data["operation"], "revenue_cogs_by_month")
        self.assertEqual(result.data["metrics"][0]["gross_profit"], 40)

    async def test_analytics_agent_maps_enriched_payload_to_agent_result(self):
        agent = AnalyticsAgent(FakeSQLAgent())

        result = await agent.run(AgentRequest(question="Doanh thu tháng 12/2022"))

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.agent, "analytics")
        self.assertEqual(result.data["metrics"][0]["gross_profit"], 40)
        self.assertEqual(result.evidence[0].citation_id, "S1")
        self.assertIn("Doanh thu: 100.00", result.answer)
        self.assertNotIn("Lợi nhuận gộp", result.answer)


if __name__ == "__main__":
    unittest.main()
