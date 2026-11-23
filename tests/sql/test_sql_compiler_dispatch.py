"""Behavior contracts for the SQL agent's deterministic compiler boundary."""

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.agents.sql.compiler_dispatch import (
    CompilerKind,
    compile_fixed_query,
    compile_inventory_mapping,
    match_fixed_query,
)
from core.agents.sql.metric_mapping import compile_inventory_query, decode_metric_mapping
from core.agents.sql.sql_validation import QueryPlan
from core.agents.sql.text_to_sql import APPROVED_COLUMNS, APPROVED_DATE_COLUMNS, APPROVED_JOINS
from core.agents.sql.join_validation import PRIMARY_KEYS
from core.models.agents import AgentRequest, VerifiedIdentity
from core.agents.sql.agent import AnalyticsPermissionDenied, SQLAnalyticsAgent
from core.agents.sql.query_intent import QueryIntent


def revenue_intent(question, *, start='2025-06-01', end='2026-01-01', dimensions=None):
    return QueryIntent.model_validate({
        'original_question': question,
        'operation': 'aggregate',
        'metrics': ['revenue'],
        'dimensions': dimensions or [],
        'filters': [],
        'time_scope': {'mode': 'range', 'ranges': [{
            'start': date.fromisoformat(start), 'end_exclusive': date.fromisoformat(end)}]},
        'requested_sources': [{'name': 'commerce.sales', 'provenance': 'ontology_required'}],
        'explicit_source_restriction': False,
        'geographic_basis': None,
        'geographic_coverage': None,
        'ranking': None,
        'unresolved_slots': [],
    })


class SQLCompilerDispatchTest(unittest.TestCase):
    def test_explicit_commerce_breakdowns_compile_with_bounded_scope(self):
        cases = (
            ('Show the top 4 products by return rate for orders placed in 2024 with at least 15 units sold',
             CompilerKind.PRODUCT_RETURN_RATE, (date(2024, 1, 1), date(2025, 1, 1), 15), 'LIMIT 4'),
            ('Top 3 danh mục theo lợi nhuận gộp năm 2024', CompilerKind.CATEGORY_GROSS_PROFIT,
             (date(2024, 1, 1), date(2025, 1, 1)), 'LIMIT 3'),
            ('Average order value by mobile, desktop, and tablet in 2024', CompilerKind.DEVICE_AOV,
             (date(2024, 1, 1), date(2025, 1, 1), 'mobile', 'desktop', 'tablet'), 'GROUP BY o.device_type'),
        )
        for question, compiler, parameters, clause in cases:
            with self.subTest(compiler=compiler):
                selection = compile_fixed_query(match_fixed_query(question))
                self.assertEqual(selection.compiler, compiler)
                self.assertEqual(selection.plan.parameters, parameters)
                self.assertIn(clause, selection.plan.sql)
                self.assertFalse(match_fixed_query(question + ', only orders from Hanoi').matched)

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

    def test_annual_template_declines_unrepresented_business_constraints(self):
        unsupported = (
            "Tổng doanh thu năm 2025 của đại lý Bình Minh",
            "Tổng doanh thu năm 2025 tại Hà Nội",
            "Doanh thu năm 2025 ở miền Bắc",
            "Doanh thu năm 2025 từ cửa hàng A",
            "Doanh thu năm 2025 cho chi nhánh B",
            "Doanh thu năm 2025 của khách hàng VIP",
            "Doanh thu năm 2025 thuộc thương hiệu X",
            "Doanh thu năm 2025 không tính đơn đã hủy",
            "Doanh thu năm 2025 loại trừ đơn hoàn trả",
            "Doanh thu năm 2025 theo từng tháng",
            "Doanh thu năm 2025 và lợi nhuận",
            "So sánh doanh thu 2024 và 2025",
            "Top 10 mã khuyến mãi theo doanh thu năm 2025",
            "Revenue in 2025 for dealer ABC",
            "Revenue for 2025 excluding cancelled orders",
            "Tổng doanh thu từ tháng 6 đến tháng 12 năm 2025",
            "Tổng doanh thu năm 2025 theo kênh trực tuyến",
        )
        for question in unsupported:
            with self.subTest(question=question):
                selection = self.compile(question)
                self.assertFalse(selection.matched)
                self.assertIsNone(selection.plan)

    def test_annual_template_accepts_harmless_vietnamese_and_english_phrasing(self):
        for question in (
            "Tổng doanh thu năm 2025",
            "Tổng doanh thu trong năm 2025 là bao nhiêu?",
            "Cho tôi biết tổng doanh thu năm 2025",
            "What was total revenue for 2025?",
        ):
            with self.subTest(question=question):
                selection = self.compile(question)
                self.assertTrue(selection.matched)
                self.assertEqual(selection.compiler, CompilerKind.ANNUAL_REVENUE)
                self.assertIn("SUM(s.revenue)", selection.plan.sql)
                self.assertEqual(selection.plan.parameters, (date(2025, 1, 1), date(2026, 1, 1)))

    def test_explicit_and_relative_year_conflict_is_unmatched(self):
        selection = self.compile("Revenue for 2025 and this year", today=date(2026, 11, 19))
        self.assertFalse(selection.matched)
        self.assertIsNone(selection.plan)

    def test_other_revenue_and_promotion_templates_reject_unknown_filter_terms(self):
        for question in (
            "Doanh thu tháng 12 năm 2025 của đại lý Bình Minh",
            "Doanh thu 5 tháng gần đây của đại lý Bình Minh",
            "Compare this month's revenue with previous month for dealer ABC",
            "Top 10 discount codes by total revenue from dealer ABC",
        ):
            with self.subTest(question=question):
                selection = self.compile(question, today=date(2026, 11, 19))
                self.assertFalse(selection.matched)
                self.assertIsNone(selection.plan)

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

        question = "Tổng doanh thu năm 2025"
        first_match = match_fixed_query(question)
        second_match = match_fixed_query(question)
        self.assertEqual(first_match, second_match)
        first_compilation = compile_fixed_query(first_match)
        second_compilation = compile_fixed_query(second_match)
        self.assertEqual(first_compilation, second_compilation)
        self.assertEqual(first_compilation.compiler, CompilerKind.ANNUAL_REVENUE)
        self.assertEqual(first_compilation.plan.sql, second_compilation.plan.sql)
        self.assertEqual(first_compilation.plan.parameters, second_compilation.plan.parameters)

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
    async def test_customer_rankings_fall_back_to_sql_when_intent_interpretation_fails(self):
        cases = (
            (
                "Khách hàng nào có nhiều đơn hàng nhất?",
                "SELECT o.customer_id, COUNT(DISTINCT o.order_id) AS order_count "
                "FROM commerce.orders AS o GROUP BY o.customer_id "
                "ORDER BY order_count DESC, o.customer_id LIMIT 1",
            ),
            (
                "khách hàng nào mua hàng nhiều nhất theo số lượng",
                "SELECT o.customer_id, SUM(oi.quantity) AS total_quantity "
                "FROM commerce.orders AS o "
                "JOIN commerce.order_items AS oi ON oi.order_id = o.order_id "
                "GROUP BY o.customer_id "
                "ORDER BY total_quantity DESC, o.customer_id LIMIT 1",
            ),
        )
        selected_tables = set(APPROVED_COLUMNS)
        selection = {
            "tables": selected_tables,
            "required_tables": set(),
            "candidate_tables": selected_tables,
        }

        for question, sql in cases:
            with self.subTest(question=question):
                repository = type("Repository", (), {})()
                repository.get_schema = AsyncMock(return_value={
                    "tables": APPROVED_COLUMNS,
                    "joins": APPROVED_JOINS,
                    "primary_keys": PRIMARY_KEYS,
                    "date_columns": APPROVED_DATE_COLUMNS,
                })
                repository.execute_approved_query = AsyncMock(return_value=[{
                    "customer_id": "customer-1",
                    "order_count": 12,
                    "total_quantity": 42,
                }])
                agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
                agent._generate_sql = AsyncMock(return_value=json.dumps({
                    "sql": sql, "parameters": [],
                }))

                with patch(
                    "core.agents.sql.agent.interpret_query_intent",
                    new=AsyncMock(side_effect=ValueError("intent response did not validate")),
                ) as interpret, patch(
                    "core.agents.sql.agent.asyncio.to_thread",
                    new=AsyncMock(return_value=selection),
                ):
                    result = await agent.run_payload(AgentRequest(
                        question=question,
                        identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
                    ))

                self.assertEqual(result.get("query_status"), "executed", result)
                self.assertEqual(result["sql"], sql)
                self.assertEqual(result["parameters"], [])
                self.assertFalse(result["metadata"].get("clarification_required", False))
                self.assertEqual(result["metadata"]["query_intent_fallback"], "ValueError")
                self.assertIn(question, agent._generate_sql.await_args.args[0])
                interpret.assert_awaited_once()
                agent._generate_sql.assert_awaited_once()
                repository.execute_approved_query.assert_awaited_once_with(sql)

    async def test_intent_interpretation_failure_does_not_bypass_sql_security(self):
        repository = type("Repository", (), {})()
        repository.get_schema = AsyncMock(return_value={
            "tables": APPROVED_COLUMNS,
            "joins": APPROVED_JOINS,
            "primary_keys": PRIMARY_KEYS,
            "date_columns": APPROVED_DATE_COLUMNS,
        })
        repository.execute_approved_query = AsyncMock(return_value=[])
        repository.execute_unverified_query = AsyncMock(return_value=[])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock(return_value=json.dumps({
            "sql": "DELETE FROM commerce.orders", "parameters": [],
        }))
        selected_tables = set(APPROVED_COLUMNS)
        selection = {
            "tables": selected_tables,
            "required_tables": set(),
            "candidate_tables": selected_tables,
        }

        with patch(
            "core.agents.sql.agent.interpret_query_intent",
            new=AsyncMock(side_effect=ValueError("intent response did not validate")),
        ), patch(
            "core.agents.sql.agent.asyncio.to_thread",
            new=AsyncMock(return_value=selection),
        ):
            result = await agent.run_payload(AgentRequest(
                question="Khách hàng nào có nhiều đơn hàng nhất?",
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        self.assertEqual(result["metadata"]["error_type"], "SQLSecurityError")
        self.assertEqual(agent._generate_sql.await_count, 2)
        repository.execute_approved_query.assert_not_awaited()
        repository.execute_unverified_query.assert_not_awaited()

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
        self.assertEqual(result["metadata"]["execution_status"], "executed_empty")
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
        self.assertEqual(result["metadata"]["execution_status"], "executed")
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

    async def test_structured_inventory_intent_adapts_without_second_interpretation(self):
        repository = type("Repository", (), {})()
        repository.get_schema = AsyncMock(return_value={
            "tables": APPROVED_COLUMNS, "joins": APPROVED_JOINS,
            "primary_keys": PRIMARY_KEYS, "date_columns": APPROVED_DATE_COLUMNS,
        })
        repository.execute_approved_query = AsyncMock(return_value=[])
        provider = type("Provider", (), {"generate": Mock()})()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        agent._generate_sql = AsyncMock(side_effect=AssertionError("inventory intent compiles without SQL generation"))
        question = "Which blue styles have the fewest pieces left at latest snapshot?"
        intent_response = json.dumps({"intent": {
            "original_question": question, "operation": "rank", "metrics": ["stock_on_hand"],
            "unverified_metric_request": None, "dimensions": ["product_id", "product_name"],
            "filters": [{"field": "commerce.products.color", "operator": "eq", "value": "blue"}],
            "time_scope": {"mode": "latest", "ranges": []},
            "requested_sources": [
                {"name": "commerce.inventory", "provenance": "ontology_required"},
                {"name": "commerce.products", "provenance": "ontology_required"}],
            "explicit_source_restriction": False, "geographic_basis": None,
            "geographic_coverage": None,
            "ranking": {"metric": "stock_on_hand", "direction": "asc", "limit": None},
            "unresolved_slots": [],
        }})
        selection = {"tables": set(APPROVED_COLUMNS), "required_tables": set(),
                     "candidate_tables": set(APPROVED_COLUMNS)}
        with patch("core.agents.sql.intent_resolution.generate",
                   new=AsyncMock(return_value=intent_response)) as interpret, \
                patch("core.agents.sql.agent.asyncio.to_thread",
                      new=AsyncMock(return_value=selection)) as select_tables:
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        self.assertEqual(result["query_status"], "executed")
        self.assertIn("commerce.products.color = $1", result["sql"])
        self.assertEqual(result["parameters"], ["blue"])
        interpret.assert_awaited_once()
        provider.generate.assert_not_called()
        agent._generate_sql.assert_not_awaited()
        repository.execute_approved_query.assert_awaited_once()
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
        question = "Doanh thu năm 2025 theo từng tháng"
        selected_tables = set(APPROVED_COLUMNS)
        selection = {
            "tables": selected_tables,
            "required_tables": set(),
            "candidate_tables": selected_tables,
        }
        with patch("core.agents.sql.agent.asyncio.to_thread", new=AsyncMock(return_value=selection)), \
                patch("core.agents.sql.agent.interpret_query_intent", new=AsyncMock(return_value=
                      revenue_intent(question, start='2025-01-01', end='2026-01-01', dimensions=['date']))):
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        agent._generate_sql.assert_awaited_once()
        self.assertTrue(result["metadata"]["clarification_required"])
        repository.execute_approved_query.assert_not_awaited()

    async def test_unsupported_date_scope_uses_valid_parameterized_llm_fallback(self):
        repository = type("Repository", (), {})()
        repository.get_schema = AsyncMock(return_value={
            "tables": APPROVED_COLUMNS,
            "joins": APPROVED_JOINS,
            "primary_keys": PRIMARY_KEYS,
            "date_columns": APPROVED_DATE_COLUMNS,
        })
        repository.execute_approved_query = AsyncMock(return_value=[{"revenue": 12.5}])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        sql = ("SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s "
               "WHERE s.date >= $1 AND s.date < $2 LIMIT 1")
        agent._generate_sql = AsyncMock(return_value=json.dumps({
            "sql": sql,
            "parameters": ["2025-06-01", "2026-01-01"],
            "explanation": "Revenue from June through December 2025.",
        }))
        selection = {
            "tables": set(APPROVED_COLUMNS),
            "required_tables": set(),
            "candidate_tables": set(APPROVED_COLUMNS),
        }
        with patch("core.agents.sql.agent.asyncio.to_thread", new=AsyncMock(return_value=selection)) as select_tables, \
                patch("core.agents.sql.agent.interpret_query_intent", new=AsyncMock(return_value=
                      revenue_intent("Doanh thu từ tháng 6 đến tháng 12 năm 2025"))) as interpret:
            result = await agent.run_payload(AgentRequest(
                question="Doanh thu từ tháng 6 đến tháng 12 năm 2025",
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        self.assertEqual(result["query_status"], "executed")
        self.assertIn("s.date >= $1", result["sql"])
        self.assertIn("s.date < $2", result["sql"])
        self.assertEqual(result["parameters"], [date(2025, 6, 1), date(2026, 1, 1)])
        agent._generate_sql.assert_awaited_once()
        interpret.assert_awaited_once()
        repository.execute_approved_query.assert_awaited_once_with(
            sql, date(2025, 6, 1), date(2026, 1, 1))
        select_tables.assert_awaited_once()

    async def test_unsupported_date_scope_fallback_rejects_unsafe_sql(self):
        class Repository:
            async def get_schema(self):
                return {
                    "tables": APPROVED_COLUMNS,
                    "joins": APPROVED_JOINS,
                    "primary_keys": PRIMARY_KEYS,
                    "date_columns": APPROVED_DATE_COLUMNS,
                }

            async def execute_approved_query(self, *_args):
                return [{"revenue": 1}]

            async def execute_unverified_query(self, *_args):
                return [{"revenue": 1}]

        repository = Repository()
        repository.get_schema = AsyncMock(return_value={
            "tables": APPROVED_COLUMNS,
            "joins": APPROVED_JOINS,
            "primary_keys": PRIMARY_KEYS,
            "date_columns": APPROVED_DATE_COLUMNS,
        })
        repository.execute_approved_query = AsyncMock(return_value=[{"revenue": 1}])
        repository.execute_unverified_query = AsyncMock(return_value=[{"revenue": 1}])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock(side_effect=[
            json.dumps({"sql": "DELETE FROM commerce.sales", "parameters": []}),
            json.dumps({"clarification": "The dealer field is unavailable in the approved schema."}),
        ])
        selection = {
            "tables": set(APPROVED_COLUMNS),
            "required_tables": set(),
            "candidate_tables": set(APPROVED_COLUMNS),
        }
        question = "Doanh thu từ tháng 6 đến tháng 12 năm 2025"
        with patch("core.agents.sql.agent.asyncio.to_thread", new=AsyncMock(return_value=selection)) as select_tables, \
                patch("core.agents.sql.agent.interpret_query_intent", new=AsyncMock(return_value=
                      revenue_intent(question))) as interpret:
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        self.assertTrue(result["metadata"]["clarification_required"])
        self.assertEqual(agent._generate_sql.await_count, 2)
        interpret.assert_awaited_once()
        repository.execute_approved_query.assert_not_awaited()
        repository.execute_unverified_query.assert_not_awaited()
        select_tables.assert_awaited_once()

    async def test_unavailable_dealer_filter_tries_options_once_without_sql_generation(self):
        repository = type("Repository", (), {})()
        repository.get_schema = AsyncMock(return_value={
            "tables": APPROVED_COLUMNS,
            "joins": APPROVED_JOINS,
            "primary_keys": PRIMARY_KEYS,
            "date_columns": APPROVED_DATE_COLUMNS,
        })
        repository.execute_approved_query = AsyncMock(return_value=[])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock(side_effect=AssertionError("unresolved dealer scope must clarify"))
        question = "Tổng doanh thu năm 2025 của đại lý Bình Minh"
        interpretation = {
            "intent": {
                "original_question": question,
                "operation": "aggregate",
                "metrics": ["revenue"],
                "unverified_metric_request": None,
                "dimensions": [],
                "filters": [{"field": "dealer_name", "operator": "eq", "value": "Bình Minh"}],
                "time_scope": {"mode": "range", "ranges": [
                    {"start": "2025-01-01", "end_exclusive": "2026-01-01"}]},
                "requested_sources": [{"name": "commerce.sales", "provenance": "ontology_required"}],
                "explicit_source_restriction": False,
                "geographic_basis": None,
                "geographic_coverage": None,
                "ranking": None,
                "unresolved_slots": [],
            }
        }
        with patch("core.agents.sql.intent_resolution.generate",
                   new=AsyncMock(side_effect=[json.dumps(interpretation), '{"allowed_choices":[]}'])) as interpret:
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        self.assertEqual(result["query_status"], "unsupported")
        self.assertEqual(result["metadata"]["failure_code"], "clarification_options_unavailable")
        self.assertEqual(result["rows"], [])
        self.assertEqual(interpret.await_count, 2)
        agent._generate_sql.assert_not_awaited()
        repository.execute_approved_query.assert_not_awaited()
        repository.get_schema.assert_awaited_once()

    async def test_explicit_source_restriction_clarifies_before_adding_required_order_items(self):
        repository = type("Repository", (), {})()
        repository.get_schema = AsyncMock(return_value={
            "tables": APPROVED_COLUMNS, "joins": APPROVED_JOINS,
            "primary_keys": PRIMARY_KEYS, "date_columns": APPROVED_DATE_COLUMNS,
        })
        repository.execute_approved_query = AsyncMock(return_value=[])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock(side_effect=AssertionError(
            "an explicit source conflict must clarify before SQL generation"))
        question = "Revenue by region in May 2026 using only orders and geography"
        response = {"intent": {
            "original_question": question, "operation": "aggregate",
            "metrics": ["regional_revenue"], "unverified_metric_request": None,
            "dimensions": ["region"], "filters": [],
            "time_scope": {"mode": "range", "ranges": [
                {"start": "2026-05-01", "end_exclusive": "2026-06-01"}]},
            "requested_sources": [
                {"name": "commerce.orders", "provenance": "user"},
                {"name": "commerce.geography", "provenance": "user"}],
            "explicit_source_restriction": True,
            "geographic_basis": "order_destination", "geographic_coverage": "all",
            "ranking": None, "unresolved_slots": [],
        }}
        with patch("core.agents.sql.intent_resolution.generate",
                   new=AsyncMock(return_value=json.dumps(response))) as interpret, \
                patch("core.agents.sql.agent.select_jev_schema_tables") as select_tables:
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        self.assertEqual(result["query_status"], "clarification_required")
        self.assertIn("order_items", result["answer"])
        interpret.assert_awaited_once()
        agent._generate_sql.assert_not_awaited()
        select_tables.assert_not_called()
        repository.execute_approved_query.assert_not_awaited()

    async def test_unauthorized_request_stops_before_schema_llm_and_execution(self):
        repository = type("Repository", (), {})()
        repository.get_schema = AsyncMock(return_value={
            "tables": APPROVED_COLUMNS,
            "joins": APPROVED_JOINS,
            "primary_keys": PRIMARY_KEYS,
            "date_columns": APPROVED_DATE_COLUMNS,
        })
        repository.execute_approved_query = AsyncMock(return_value=[])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock()

        with self.assertRaises(AnalyticsPermissionDenied):
            await agent.run_payload(AgentRequest(
                question="Tổng doanh thu năm 2025",
                identity=VerifiedIdentity(subject="test", permissions=set()),
            ))

        repository.get_schema.assert_not_awaited()
        repository.execute_approved_query.assert_not_awaited()
        agent._generate_sql.assert_not_awaited()

    async def test_database_failure_is_source_failed_without_sql_replanning(self):
        repository = type("Repository", (), {})()
        repository.get_schema = AsyncMock(return_value={
            "tables": APPROVED_COLUMNS,
            "joins": APPROVED_JOINS,
            "primary_keys": PRIMARY_KEYS,
            "date_columns": APPROVED_DATE_COLUMNS,
        })
        repository.execute_approved_query = AsyncMock(side_effect=RuntimeError("database unavailable"))
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock(side_effect=AssertionError("fixed SQL must not be replanned"))
        with patch("core.agents.sql.agent.select_jev_schema_tables") as select_tables:
            result = await agent.run_payload(AgentRequest(
                question="Tổng doanh thu năm 2025",
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        self.assertEqual(result["query_status"], "error")
        self.assertEqual(result["metadata"]["execution_status"], "source_failed")
        repository.execute_approved_query.assert_awaited_once()
        agent._generate_sql.assert_not_awaited()
        select_tables.assert_not_called()

    async def test_invalid_sql_retry_exhaustion_rejects_without_execution(self):
        repository = type("Repository", (), {})()
        repository.get_schema = AsyncMock(return_value={
            "tables": APPROVED_COLUMNS,
            "joins": APPROVED_JOINS,
            "primary_keys": PRIMARY_KEYS,
            "date_columns": APPROVED_DATE_COLUMNS,
        })
        repository.execute_approved_query = AsyncMock(return_value=[])
        agent = SQLAnalyticsAgent(repository, llm=object(), inventory_only=False)
        agent._generate_sql = AsyncMock(side_effect=[
            json.dumps({"sql": "DELETE FROM commerce.sales", "parameters": []}),
            json.dumps({"sql": "UPDATE commerce.sales SET revenue = 0", "parameters": []}),
        ])
        selection = {
            "tables": set(APPROVED_COLUMNS),
            "required_tables": set(),
            "candidate_tables": set(APPROVED_COLUMNS),
        }
        question = "Doanh thu từ tháng 6 đến tháng 12 năm 2025"
        with patch("core.agents.sql.agent.asyncio.to_thread", new=AsyncMock(return_value=selection)), \
                patch("core.agents.sql.agent.interpret_query_intent", new=AsyncMock(return_value=
                      revenue_intent(question))) as interpret:
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
            ))

        self.assertEqual(agent._generate_sql.await_count, 2)
        interpret.assert_awaited_once()
        self.assertEqual(result["query_status"], "rejected")
        self.assertEqual(result["metadata"]["execution_status"], "validation_failed")
        repository.execute_approved_query.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
