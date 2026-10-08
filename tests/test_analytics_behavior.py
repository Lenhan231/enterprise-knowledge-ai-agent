import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.analytics_agent import AnalyticsAgent
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.models.agents import AgentRequest


class RowsRepository:
    async def revenue_cogs_by_month(self, start, end):
        self.period = start, end
        if start.year == 2025:
            return []
        if start == date(2022, 1, 1):
            return [
                {"month": date(2022, 1, 1), "revenue": 100, "cogs": 40},
                {"month": date(2022, 2, 1), "revenue": 30, "cogs": 20},
                {"month": date(2022, 3, 1), "revenue": 60, "cogs": 70},
            ]
        return [
            {"month": date(2022, 12, 1), "revenue": 100, "cogs": 120}
        ]

    async def revenue_by_region(self, start, end):
        return [
            {"region": "East", "revenue": 60},
            {"region": "Central", "revenue": 30},
            {"region": "West", "revenue": 10},
        ]

    async def inventory_by_category(self, snapshot):
        return [
            {"category": "Casual", "products_observed": 4, "stockout_products": 3,
             "reorder_products": 1, "overstock_products": 2, "stock_on_hand": 40,
             "avg_sell_through_rate": 0.15, "avg_fill_rate": 0.8,
             "avg_days_of_supply": 12},
            {"category": "Outdoor", "products_observed": 2, "stockout_products": 1,
             "reorder_products": 0, "overstock_products": 0, "stock_on_hand": 20,
             "avg_sell_through_rate": 0.45, "avg_fill_rate": 0.9,
             "avg_days_of_supply": 20},
        ]

    async def close(self):
        pass


class AnalyticsBehaviorTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repository = RowsRepository()
        self.agent = AnalyticsAgent(SQLAnalyticsAgent(self.repository))

    async def ask(self, question):
        return await self.agent.run(AgentRequest(question=question))

    async def test_revenue_cogs_and_derived_profit_answer_the_requested_metric(self):
        both = await self.ask("Doanh thu và giá vốn tháng 12/2022 là bao nhiêu?")
        profit = await self.ask("Lợi nhuận gộp tháng 12/2022 là bao nhiêu?")
        self.assertIn("100", both.answer)
        self.assertIn("120", both.answer)
        self.assertIn("-20", profit.answer)
        self.assertIn("revenue - cogs", profit.answer)

    async def test_one_two_and_three_regions_and_both_rank_directions(self):
        one = await self.ask("Doanh thu khu vực West tháng 12/2022 là bao nhiêu?")
        two = await self.ask("So sánh doanh thu East và West tháng 12/2022")
        three = await self.ask("So sánh doanh thu các khu vực tháng 12/2022")
        lowest = await self.ask("Khu vực nào có doanh thu thấp nhất tháng 12/2022?")
        highest = await self.ask("Khu vực nào có doanh thu cao nhất tháng 12/2022?")
        self.assertEqual([row["region"] for row in one.data["table"]["rows"]], ["West"])
        self.assertEqual({row["region"] for row in two.data["table"]["rows"]}, {"East", "West"})
        self.assertEqual(two.data["table"]["rows"][0]["share"], "60.00%")
        self.assertEqual(len(three.data["table"]["rows"]), 3)
        self.assertIn("West", lowest.answer)
        self.assertIn("East", highest.answer)

    async def test_inventory_metric_selection_and_category_filter(self):
        sell = await self.ask("Tỷ lệ bán hết theo danh mục ngày 2022-12-31 là bao nhiêu?")
        stockout = await self.ask("Danh mục nào có tỷ lệ hết hàng cao nhất ngày 2022-12-31?")
        filtered = await self.ask("Tồn kho danh mục Outdoor ngày 2022-12-31 là bao nhiêu?")
        self.assertIn("15.00%", sell.answer)
        self.assertIn("45.00%", sell.answer)
        self.assertNotIn("hết hàng cao nhất", sell.answer)
        self.assertIn("Casual", stockout.answer)
        self.assertEqual([row["category"] for row in filtered.data["table"]["rows"]], ["Outdoor"])

    async def test_each_inventory_metric_uses_its_own_column(self):
        cases = [
            ("Tồn kho", "stock_on_hand", "40.00"),
            ("Tỷ lệ hết hàng", "stockout_rate", "75.00%"),
            ("Tỷ lệ bán hết", "sell_through_rate", "15.00%"),
            ("Tỷ lệ đáp ứng", "fill_rate", "80.00%"),
            ("Số ngày đủ hàng", "days_of_supply", "12.00"),
        ]
        for phrase, column, expected in cases:
            with self.subTest(metric=column):
                result = await self.ask(f"{phrase} theo danh mục ngày 2022-12-31")
                self.assertEqual(result.data["table"]["rows"][0][column], expected)

    async def test_unknown_group_requests_clarification(self):
        result = await self.ask("Doanh thu khu vực North tháng 12/2022")
        self.assertFalse(result.metadata["ok"])
        self.assertIn("Không xác định", result.answer)

    async def test_region_and_category_names_work_without_dimension_keyword(self):
        region = await self.ask("Doanh thu West tháng 12/2022")
        category = await self.ask("Tỷ lệ bán hết Casual ngày 2022-12-31")
        self.assertEqual(region.data["table"]["rows"][0]["region"], "West")
        self.assertEqual(category.data["table"]["rows"][0]["category"], "Casual")

    async def test_year_without_rows_is_not_misreported_as_missing_date(self):
        result = await self.ask("Doanh thu và giá vốn năm 2025 là bao nhiêu?")
        self.assertEqual(self.repository.period, (date(2025, 1, 1), date(2026, 1, 1)))
        self.assertFalse(result.metadata["ok"])
        self.assertIn("không có dữ liệu", result.answer.casefold())

    async def test_monthly_minimum_and_maximum_within_a_year_use_monthly_rows(self):
        lowest = await self.ask("Doanh thu thấp nhất theo tháng trong năm 2022 là bao nhiêu?")
        highest = await self.ask("Tháng nào có doanh thu cao nhất trong năm 2022?")
        annual = await self.ask("Doanh thu năm 2022 là bao nhiêu?")
        self.assertIn("02/2022", lowest.answer)
        self.assertIn("30.00", lowest.answer)
        self.assertNotIn("190.00", lowest.answer)
        self.assertEqual(len(lowest.data["table"]["rows"]), 3)
        self.assertIn("01/2022", highest.answer)
        self.assertIn("100.00", highest.answer)
        self.assertIn("190.00", annual.answer)

    async def test_missing_period_and_unsupported_metric_have_distinct_reasons(self):
        missing = await self.ask("Doanh thu theo khu vực là bao nhiêu?")
        unsupported = await self.ask("Tỷ lệ hoàn hàng tháng 12/2022 là bao nhiêu?")
        self.assertIn("tháng/năm", missing.answer)
        self.assertIn("chưa được hỗ trợ", unsupported.answer)
