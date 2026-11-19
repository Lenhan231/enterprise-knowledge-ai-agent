"""Behavior contracts for the SQL agent's deterministic compiler boundary."""

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.agents.sql.compiler_dispatch import (
    CompilerKind,
    compile_fixed_query,
    compile_inventory_mapping,
    match_fixed_query,
)
from core.analytics.metric_mapping import compile_inventory_query, decode_metric_mapping
from core.analytics.sql_validation import QueryPlan
from core.analytics.text_to_sql import APPROVED_COLUMNS, APPROVED_DATE_COLUMNS, APPROVED_JOINS
from core.analytics.join_validation import PRIMARY_KEYS
from core.models.agents import AgentRequest, VerifiedIdentity
from core.agents.sql.agent import SQLAnalyticsAgent


class SQLCompilerDispatchTest(unittest.TestCase):
    def compile(self, question, **kwargs):
        dashboard_build = kwargs.pop("dashboard_build", False)
        return compile_fixed_query(
            match_fixed_query(question, **kwargs), dashboard_build=dashboard_build
        )

    def test_annual_revenue_resolves_explicit_and_relative_years(self):
        selection = self.compile("Tổng doanh thu năm 2025 là bao nhiêu?")
        plan = selection.plan
        self.assertIsInstance(plan, QueryPlan)
        self.assertEqual(selection.compiler, CompilerKind.ANNUAL_REVENUE)
        self.assertEqual(plan.parameters, (date(2025, 1, 1), date(2026, 1, 1)))
        self.assertIn("SUM(s.revenue)", plan.sql)
        self.assertNotIn("GROUP BY", plan.sql.upper())

        selection = self.compile("Tổng doanh thu năm ngoái?", today=date(2026, 11, 19))
        self.assertEqual(selection.compiler, CompilerKind.ANNUAL_REVENUE)
        plan = selection.plan
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
                selection = self.compile(question)
                self.assertIsNone(selection.plan)
                self.assertFalse(selection.matched)

    def test_month_comparison_handles_january_rollover(self):
        selection = self.compile(
            "Compare this month's revenue with previous month", today=date(2026, 1, 10))
        plan = selection.plan
        self.assertEqual(selection.compiler, CompilerKind.MONTH_OVER_MONTH_REVENUE)
        self.assertEqual(plan.parameters, (date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)))
        self.assertIn("previous_month_revenue", plan.sql)
        selection = self.compile("Compare this month's revenue with previous month for blue products")
        self.assertIsNone(selection.plan)

    def test_explicit_december_followup_uses_next_year_boundary(self):
        selection = self.compile(
            "Doanh thu tháng 12 năm 2026", original_question="tháng trước thì sao")
        self.assertEqual(selection.compiler, CompilerKind.EXPLICIT_MONTH_REVENUE)
        plan = selection.plan
        self.assertEqual(plan.parameters, (date(2026, 12, 1), date(2027, 1, 1)))

    def test_completed_month_series_keeps_its_requested_count_and_boundaries(self):
        selection = self.compile("Doanh thu 5 tháng gần đây", today=date(2026, 11, 19))
        self.assertEqual(selection.compiler, CompilerKind.COMPLETED_MONTHS_REVENUE)
        plan = selection.plan
        self.assertEqual(plan.parameters, (date(2026, 6, 1), date(2026, 11, 1)))
        self.assertIn("GROUP BY DATE_TRUNC('month'", plan.sql)
        selection = self.compile("Revenue for 5 completed months in 2025")
        self.assertIsNone(selection.plan)

    def test_promotion_compiler_keeps_supported_scope_and_declines_added_scope(self):
        selection = self.compile("Top 10 discount codes by total revenue")
        plan = selection.plan
        self.assertEqual(selection.compiler, CompilerKind.PROMOTION)
        self.assertEqual(selection.promotion_metric, "promotion_revenue")
        self.assertTrue(plan.sql.endswith("LIMIT 10"))
        self.assertIn("oi.promo_id_2 IS NULL", plan.sql)

        selection = self.compile("Top 10 discount codes by revenue in 2025")
        self.assertIsNone(selection.plan)
        self.assertFalse(selection.matched)

    def test_direct_fields_return_the_shared_plan_with_bound_literals(self):
        selection = self.compile(
            "List product_id, product_name, color, price from commerce.products "
            "where color='blue' and price>=100 order by price desc limit 5.")
        plan = selection.plan
        self.assertIsInstance(plan, QueryPlan)
        self.assertEqual(selection.compiler, CompilerKind.DIRECT_FIELD)
        self.assertIsNotNone(selection.direct_contract)
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
        selection = compile_inventory_mapping(mapping)
        plan = selection.plan
        self.assertIsInstance(plan, QueryPlan)
        self.assertEqual(selection.compiler, CompilerKind.INVENTORY_MAPPING)
        self.assertEqual((plan.sql, plan.parameters), (legacy_sql, legacy_parameters))

    def test_unmatched_result_is_explicit_immutable_and_repeatable(self):
        first = self.compile("Explain whether our logistics strategy is effective")
        second = self.compile("Explain whether our logistics strategy is effective")
        self.assertFalse(first.matched)
        self.assertIsNone(first.compiler)
        self.assertIsNone(first.plan)
        self.assertEqual(first, second)
        with self.assertRaises((AttributeError, TypeError)):
            first.plan = QueryPlan(sql="SELECT 1", parameters=())

        match = match_fixed_query("Tổng doanh thu năm 2025")
        first_compilation = compile_fixed_query(match)
        second_compilation = compile_fixed_query(match)
        self.assertEqual(first_compilation, second_compilation)

    def test_optional_context_is_safe_and_conversation_context_disables_direct_fields(self):
        question = "List product_id, product_name from commerce.products"
        without_context = self.compile(question)
        with_context = self.compile(question, context={"turn": 1})
        self.assertEqual(without_context.compiler, CompilerKind.DIRECT_FIELD)
        self.assertFalse(with_context.matched)

    def test_dashboard_candidate_keeps_selection_but_defers_plan(self):
        selection = self.compile("Tổng doanh thu năm 2025", dashboard_build=True)
        self.assertTrue(selection.matched)
        self.assertEqual(selection.compiler, CompilerKind.ANNUAL_REVENUE)
        self.assertIsNone(selection.plan)

    def test_inventory_mapping_not_applicable_is_an_unmatched_result(self):
        mapping = decode_metric_mapping(json.dumps({
            "domain": "other",
            "metrics": [],
        }), "Explain the inventory schema")
        selection = compile_inventory_mapping(mapping)
        self.assertFalse(selection.matched)
        self.assertIsNone(selection.plan)

    def test_required_unsupported_scopes_decline_fixed_templates(self):
        unsupported = (
            "Tổng doanh thu năm 2025 tại Hà Nội",
            "Doanh thu năm 2025 ở miền Bắc",
            "Doanh thu năm 2025 cho chi nhánh A",
            "Doanh thu năm 2025 theo sản phẩm",
            "Doanh thu năm 2025 của sản phẩm màu xanh",
            "So sánh doanh thu năm 2024 và 2025",
            "Top 10 mã khuyến mãi theo doanh thu năm 2025",
            "Doanh thu năm 2025 tại kho Cầu Giấy",
        )
        for question in unsupported:
            with self.subTest(question=question):
                selection = self.compile(question)
                self.assertFalse(selection.matched)
                self.assertIsNone(selection.plan)

    def test_supported_annual_scope_matches_exactly(self):
        selection = self.compile("Tổng doanh thu năm 2025")
        self.assertEqual(selection.compiler, CompilerKind.ANNUAL_REVENUE)
        self.assertEqual(selection.plan.parameters, (date(2025, 1, 1), date(2026, 1, 1)))


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
        repository.get_schema = AsyncMock(return_value={
            "tables": APPROVED_COLUMNS,
            "joins": APPROVED_JOINS,
            "primary_keys": PRIMARY_KEYS,
            "date_columns": APPROVED_DATE_COLUMNS,
        })
        repository.execute_approved_query = AsyncMock(return_value=[])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock(side_effect=AssertionError("direct fields should not reach generation"))
        question = (
            "List product_id, product_name, color, price from commerce.products "
            "where color='blue' and price>=100 order by price desc limit 5."
        )
        with patch("core.agents.sql.agent.select_jev_schema_tables") as select_tables:
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        self.assertEqual(result["query_status"], "executed")
        self.assertEqual(result["parameters"], ["blue", 100])
        self.assertNotIn("'blue'", result["sql"])
        agent._generate_sql.assert_not_awaited()
        repository.execute_approved_query.assert_awaited_once()
        repository.get_schema.assert_awaited_once()
        select_tables.assert_not_called()

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
        repository.get_schema = AsyncMock(return_value={
            "tables": APPROVED_COLUMNS,
            "joins": APPROVED_JOINS,
            "primary_keys": PRIMARY_KEYS,
            "date_columns": APPROVED_DATE_COLUMNS,
        })
        repository.execute_approved_query = AsyncMock(return_value=[{"revenue": 12.5}])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock(side_effect=AssertionError("fixed SQL should not reach generation"))
        with patch("core.agents.sql.agent.select_jev_schema_tables") as select_tables:
            result = await agent.run_payload(AgentRequest(
                question="Tổng doanh thu năm 2025 là bao nhiêu?",
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        self.assertEqual(result["query_status"], "executed")
        self.assertIn("SUM(s.revenue)", result["sql"])
        self.assertEqual(result["parameters"], [date(2025, 1, 1), date(2026, 1, 1)])
        agent._generate_sql.assert_not_awaited()
        repository.execute_approved_query.assert_awaited_once()
        repository.get_schema.assert_awaited_once()
        select_tables.assert_not_called()

    async def test_inventory_mapping_stage_uses_one_interpretation_and_skips_sql_generation(self):
        class Repository:
            async def get_schema(self):
                return {
                    "tables": APPROVED_COLUMNS,
                    "joins": APPROVED_JOINS,
                    "primary_keys": PRIMARY_KEYS,
                    "date_columns": APPROVED_DATE_COLUMNS,
                }

        repository = Repository()
        repository.get_schema = AsyncMock(return_value={
            "tables": APPROVED_COLUMNS,
            "joins": APPROVED_JOINS,
            "primary_keys": PRIMARY_KEYS,
            "date_columns": APPROVED_DATE_COLUMNS,
        })
        repository.execute_approved_query = AsyncMock(return_value=[])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock(side_effect=AssertionError("inventory mapping should compile directly"))
        mapped = json.dumps({
            "metrics": ["stock_on_hand"],
            "dimensions": ["product_id", "product_name"],
            "representation": "product",
            "time": {"mode": "snapshot", "start": "2022-12-31"},
        })
        selection = {
            "tables": set(APPROVED_COLUMNS),
            "required_tables": set(),
            "candidate_tables": set(APPROVED_COLUMNS),
        }
        with patch("core.agents.sql.agent.generate", new=AsyncMock(return_value=mapped)) as generate_mapping, \
                patch("core.agents.sql.agent.asyncio.to_thread", new=AsyncMock(return_value=selection)) as select_tables:
            result = await agent.run_payload(AgentRequest(
                question="Show product stock_on_hand on 2022-12-31",
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        self.assertEqual(result["query_status"], "executed")
        generate_mapping.assert_awaited_once()
        agent._generate_sql.assert_not_awaited()
        repository.execute_approved_query.assert_awaited_once()
        repository.get_schema.assert_awaited_once()
        select_tables.assert_awaited_once()

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
