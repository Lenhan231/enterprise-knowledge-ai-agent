"""Behavior contracts for the SQL agent's deterministic compiler boundary."""

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.agents.sql.agent import compile_known_query
from core.analytics.metric_mapping import compile_inventory_query, decode_metric_mapping
from core.analytics.sql_validation import QueryPlan
from core.analytics.text_to_sql import APPROVED_COLUMNS, APPROVED_DATE_COLUMNS, APPROVED_JOINS
from core.analytics.join_validation import PRIMARY_KEYS
from core.models.agents import AgentRequest, VerifiedIdentity
from core.agents.sql.agent import SQLAnalyticsAgent


class SQLCompilerDispatchTest(unittest.TestCase):
    def compile(self, question, **kwargs):
        trace = {}
        plan = compile_known_query(question, trace=trace, **kwargs)
        return plan, trace

    def test_annual_revenue_resolves_explicit_and_relative_years(self):
        plan, trace = self.compile("Tổng doanh thu năm 2025 là bao nhiêu?")
        self.assertIsInstance(plan, QueryPlan)
        self.assertEqual(trace["compiler"], "annual_revenue")
        self.assertEqual(plan.parameters, (date(2025, 1, 1), date(2026, 1, 1)))
        self.assertIn("SUM(s.revenue)", plan.sql)
        self.assertNotIn("GROUP BY", plan.sql.upper())

        plan, trace = self.compile("Tổng doanh thu năm ngoái?", today=date(2026, 11, 19))
        self.assertEqual(trace["compiler"], "annual_revenue")
        self.assertEqual(plan.parameters, (date(2025, 1, 1), date(2026, 1, 1)))

    def test_annual_template_declines_grouping_comparison_and_extra_filters(self):
        for question in (
            "Doanh thu năm 2025 theo từng tháng",
            "So sánh doanh thu năm 2024 và 2025",
            "Doanh thu năm 2025 cho khu vực miền Bắc",
            "Revenue in 2025 for blue products",
            "Revenue for 2025 and this year",
        ):
            with self.subTest(question=question):
                plan, trace = self.compile(question)
                self.assertIsNone(plan)
                self.assertFalse(trace["candidate"])

    def test_month_comparison_handles_january_rollover(self):
        plan, trace = self.compile(
            "Compare this month's revenue with previous month", today=date(2026, 1, 10))
        self.assertEqual(trace["compiler"], "month_over_month_revenue")
        self.assertEqual(plan.parameters, (date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)))
        self.assertIn("previous_month_revenue", plan.sql)
        plan, _ = self.compile("Compare this month's revenue with previous month for blue products")
        self.assertIsNone(plan)

    def test_explicit_december_followup_uses_next_year_boundary(self):
        plan, trace = self.compile(
            "Doanh thu tháng 12 năm 2026", original_question="tháng trước thì sao")
        self.assertEqual(trace["compiler"], "explicit_month_revenue")
        self.assertEqual(plan.parameters, (date(2026, 12, 1), date(2027, 1, 1)))

    def test_completed_month_series_keeps_its_requested_count_and_boundaries(self):
        plan, trace = self.compile("Doanh thu 5 tháng gần đây", today=date(2026, 11, 19))
        self.assertEqual(trace["compiler"], "completed_months_revenue")
        self.assertEqual(plan.parameters, (date(2026, 6, 1), date(2026, 11, 1)))
        self.assertIn("GROUP BY DATE_TRUNC('month'", plan.sql)
        plan, _ = self.compile("Revenue for 5 completed months in 2025")
        self.assertIsNone(plan)

    def test_promotion_compiler_keeps_supported_scope_and_declines_added_scope(self):
        plan, trace = self.compile("Top 10 discount codes by total revenue")
        self.assertEqual(trace["compiler"], "promotion")
        self.assertEqual(trace["promotion_metric"], "promotion_revenue")
        self.assertTrue(plan.sql.endswith("LIMIT 10"))
        self.assertIn("oi.promo_id_2 IS NULL", plan.sql)

        plan, trace = self.compile("Top 10 discount codes by revenue in 2025")
        self.assertIsNone(plan)
        self.assertFalse(trace["candidate"])

    def test_direct_fields_return_the_shared_plan_with_bound_literals(self):
        plan, trace = self.compile(
            "List product_id, product_name, color, price from commerce.products "
            "where color='blue' and price>=100 order by price desc limit 5.")
        self.assertIsInstance(plan, QueryPlan)
        self.assertEqual(trace["compiler"], "direct_field")
        self.assertEqual(plan.parameters, ("blue", 100))
        self.assertIn("$1", plan.sql)
        self.assertNotIn("'blue'", plan.sql)

    def test_valid_inventory_mapping_is_adapted_without_changing_legacy_tuple(self):
        mapping = decode_metric_mapping(json.dumps({
            "metrics": ["stock_on_hand"],
            "dimensions": ["product_id", "product_name"],
            "representation": "product",
            "time": {"mode": "snapshot", "start": "2022-12-31"},
        }), "Show product stock_on_hand on 2022-12-31")
        legacy_sql, legacy_parameters = compile_inventory_query(mapping)
        plan, trace = self.compile(
            "Show product stock_on_hand on 2022-12-31", inventory_mapping=mapping)
        self.assertIsInstance(plan, QueryPlan)
        self.assertEqual(trace["compiler"], "inventory_mapping")
        self.assertEqual((plan.sql, plan.parameters), (legacy_sql, legacy_parameters))


class SQLCompilerDispatchFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_direct_field_request_executes_with_bound_values_without_sql_generation(self):
        class Repository:
            async def get_schema(self):
                return {
                    "tables": APPROVED_COLUMNS,
                    "joins": APPROVED_JOINS,
                    "primary_keys": PRIMARY_KEYS,
                    "date_columns": APPROVED_DATE_COLUMNS,
                }

        repository = Repository()
        repository.execute_approved_query = AsyncMock(return_value=[])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock(side_effect=AssertionError("direct fields should not reach generation"))
        question = (
            "List product_id, product_name, color, price from commerce.products "
            "where color='blue' and price>=100 order by price desc limit 5."
        )
        result = await agent.run_payload(AgentRequest(
            question=question,
            identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
        ))

        self.assertEqual(result["query_status"], "executed")
        self.assertEqual(result["parameters"], ["blue", 100])
        self.assertNotIn("'blue'", result["sql"])
        agent._generate_sql.assert_not_awaited()
        repository.execute_approved_query.assert_awaited_once()

    async def test_supported_annual_template_executes_without_sql_generation(self):
        class Repository:
            async def get_schema(self):
                return {
                    "tables": APPROVED_COLUMNS,
                    "joins": APPROVED_JOINS,
                    "primary_keys": PRIMARY_KEYS,
                    "date_columns": APPROVED_DATE_COLUMNS,
                }

        repository = Repository()
        repository.execute_approved_query = AsyncMock(return_value=[{"revenue": 12.5}])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock(side_effect=AssertionError("fixed SQL should not reach generation"))
        result = await agent.run_payload(AgentRequest(
            question="Tổng doanh thu năm 2025 là bao nhiêu?",
            identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
        ))

        self.assertEqual(result["query_status"], "executed")
        self.assertIn("SUM(s.revenue)", result["sql"])
        self.assertEqual(result["parameters"], [date(2025, 1, 1), date(2026, 1, 1)])
        agent._generate_sql.assert_not_awaited()
        repository.execute_approved_query.assert_awaited_once()

    async def test_ineligible_template_reaches_existing_llm_fallback(self):
        class Repository:

            async def get_schema(self):
                return {
                    "tables": APPROVED_COLUMNS,
                    "joins": APPROVED_JOINS,
                    "primary_keys": PRIMARY_KEYS,
                    "date_columns": APPROVED_DATE_COLUMNS,
                }

        repository = Repository()
        repository.execute_approved_query = AsyncMock(return_value=[])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock(return_value=json.dumps({
            "clarification": "Which monthly grouping should I use?"
        }))
        selected_tables = set(APPROVED_COLUMNS)
        selection = {
            "tables": selected_tables,
            "required_tables": set(),
            "candidate_tables": selected_tables,
        }
        with patch("core.agents.sql.agent.asyncio.to_thread", new=AsyncMock(return_value=selection)):
            result = await agent.run_payload(AgentRequest(
                question="Doanh thu năm 2025 theo từng tháng",
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        agent._generate_sql.assert_awaited_once()
        self.assertTrue(result["metadata"]["clarification_required"])
        repository.execute_approved_query.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
