import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.analytics.text_to_sql import (SQLValidationError, current_year_month_range,
                                        decode_query_plan, validate_commerce_sql,
                                        build_sql_prompt,
                                        validate_current_year_month_range,
                                        validate_current_month_total_query,
                                        rolling_days_range, resolve_rolling_days_parameters,
                                        validate_rolling_days_range)
from core.sql_agent.agent import AnalyticsPermissionDenied, SQLAnalyticsAgent
from core.sql_agent.analytics_agent import AnalyticsAgent
from core.database.commerce_repository import CommerceRepository
from core.models.agents import AgentRequest, VerifiedIdentity


ANALYST = VerifiedIdentity(subject="analyst-1", permissions={"analytics:read"})


class SQLValidationTest(unittest.TestCase):
    def test_multiple_explicit_decision_criteria_use_entity_rows_without_clarification(self):
        prompt = build_sql_prompt(
            'Show product candidates by revenue, gross margin, inventory and returns for orders in the period, with returns through 2026-11-13. '
            'Present each criterion separately; no combined score.',
            schema_tables={'commerce.orders', 'commerce.order_items', 'commerce.returns',
                           'commerce.products', 'commerce.inventory'},
        )
        self.assertIn('one row per entity', prompt)
        self.assertIn('do not ask whether to use separate result sets', prompt)
        self.assertIn('invent a combined score', prompt)
        self.assertIn('preserve it as a query calculation', prompt)
        self.assertIn('aggregate each fact separately', prompt)
        self.assertIn('orders.order_date must match the specified sales cohort', prompt)
        self.assertIn('include the selected snapshot_date, stock_on_hand, days_of_supply', prompt)

    def test_original_request_scope_survives_a_narrow_sql_subtask(self):
        original = (
            'Compare product sales for orders from 2026-09-01 through 2026-10-31 and include returns '
            'through 2026-11-13 for orders in that period.'
        )
        prompt = build_sql_prompt(
            'Return product sales and return rate.',
            original_question=original,
            schema_tables={'commerce.orders', 'commerce.order_items', 'commerce.returns', 'commerce.products'},
        )

        self.assertIn(original, prompt)
        self.assertIn('orders.order_date must match the specified sales cohort exactly', prompt)
        self.assertIn('The return-event cutoff never replaces the sales-order cohort', prompt)

    def test_generation_and_repair_prompts_require_a_final_limit(self):
        prompt = build_sql_prompt('Compare revenue for 2025 and 2026')
        self.assertIn('final SELECT MUST contain an explicit LIMIT between 1 and 200', prompt)
        self.assertIn("DATE_PART('year', alias.date)", prompt)
        self.assertIn('aggregate that table once by year', prompt)
        repaired = build_sql_prompt('Compare revenue for 2025 and 2026',
                                    validation_error='The final SELECT needs LIMIT 1..200.',
                                    previous_response='SELECT ...')
        self.assertIn('including grouped and comparison queries', repaired)
        self.assertIn('LIMIT 1..200', repaired)
        self.assertIn('never PostgreSQL :: casts', repaired)

    def test_prompt_uses_boolean_literals_and_only_placeholder_parameters(self):
        prompt = build_sql_prompt('Show overstock_flag products and filter by snapshot date')
        self.assertIn('BOOLEAN: compare them with TRUE/FALSE, never 1/0', prompt)
        self.assertIn('exactly one value per placeholder', prompt)
        self.assertIn('no more than 32 values', prompt)

    def test_year_extract_uses_function_syntax_not_a_postgres_cast(self):
        invalid = ("SELECT s.date::DATE_PART('year') AS year FROM commerce.sales AS s LIMIT 1")
        with self.assertRaisesRegex(SQLValidationError, 'Only DATE and NUMERIC casts are approved'):
            validate_commerce_sql(invalid)
        valid = ("SELECT EXTRACT(YEAR FROM s.date) AS year, SUM(s.revenue) AS revenue "
                 "FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 "
                 "GROUP BY 1 ORDER BY 1 LIMIT 200")
        self.assertEqual(validate_commerce_sql(valid).sources, ('commerce.sales',))

    def test_current_year_month_uses_server_year_and_half_open_dates(self):
        expected = (date(2026, 3, 1), date(2026, 4, 1))
        self.assertEqual(current_year_month_range("Doanh thu tháng 3 năm nay", date(2026, 11, 14)), expected)
        self.assertEqual(current_year_month_range("Doanh thu tháng 3", date(2026, 11, 14)), expected)
        self.assertEqual(current_year_month_range("doanh thu tháng này sao", date(2026, 11, 14)),
                         (date(2026, 11, 1), date(2026, 12, 1)))
        self.assertEqual(current_year_month_range("revenue this month", date(2026, 11, 14)),
                         (date(2026, 11, 1), date(2026, 12, 1)))
        sql = "SELECT SUM(s.revenue) FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 LIMIT 1"
        validate_current_year_month_range(sql, expected, "Doanh thu tháng 3 năm nay",
                                          today=date(2026, 11, 14))
        with self.assertRaisesRegex(SQLValidationError, "Current-year month filters must bind"):
            validate_current_year_month_range(sql, (date(2024, 3, 1), date(2024, 3, 31)),
                                              "Doanh thu tháng 3 năm nay", today=date(2026, 11, 14))

    def test_rolling_days_confirmation_resolves_to_bound_half_open_range(self):
        expected = (date(2026, 10, 18), date(2026, 11, 17))
        self.assertEqual(rolling_days_range('last 30 days', date(2026, 11, 16)), expected)
        self.assertEqual(rolling_days_range('30 ngày gần nhất', date(2026, 11, 16)), expected)
        sql = ('SELECT p.segment, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue '
               'FROM commerce.orders AS o JOIN commerce.order_items AS oi ON oi.order_id = o.order_id '
               'JOIN commerce.products AS p ON p.product_id = oi.product_id '
               'WHERE o.order_date >= $1 AND o.order_date < $2 GROUP BY 1 LIMIT 200')
        parameters = resolve_rolling_days_parameters(sql, ('1900-01-01', '1900-02-01'),
                                                     'last 30 days', today=date(2026, 11, 16))
        self.assertEqual(parameters, expected)
        validate_rolling_days_range(sql, parameters, 'last 30 days', today=date(2026, 11, 16))
        with self.assertRaisesRegex(SQLValidationError, 'Rolling date filters'):
            validate_rolling_days_range(sql, ('2026-10-01', '2026-11-01'),
                                        'last 30 days', today=date(2026, 11, 16))

    def test_sql_prompt_resolves_confirmed_rolling_period_instead_of_asking_again(self):
        prompt = build_sql_prompt('Compare product revenue by segment', relative_time_question='last 30 days')
        expected = rolling_days_range('last 30 days')
        self.assertIn(expected[0].isoformat(), prompt)
        self.assertIn(expected[1].isoformat(), prompt)
        self.assertIn('do not ask the user to restate this range', prompt)

    def test_current_month_single_total_rejects_daily_grouping_only(self):
        daily = (
            "SELECT s.date, SUM(s.revenue) AS revenue FROM commerce.sales AS s "
            "WHERE s.date >= $1 AND s.date < $2 GROUP BY s.date LIMIT 200"
        )
        with self.assertRaisesRegex(SQLValidationError, "Do not group the result by day"):
            validate_current_month_total_query(daily, "doanh thu tháng này sao",
                                               date_columns={("commerce.sales", "date")})
        validate_current_month_total_query(daily, "doanh thu tháng này theo ngày",
                                           date_columns={("commerce.sales", "date")})
        monthly = "SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 LIMIT 1"
        validate_current_month_total_query(monthly, "doanh thu tháng này sao",
                                           date_columns={("commerce.sales", "date")})

    def test_accepts_cte_aggregation_and_bind_parameters(self):
        sql = (
            "WITH monthly AS (SELECT date_trunc('month', s.date) AS month, "
            "SUM(s.revenue) AS revenue FROM commerce.sales AS s "
            "WHERE s.date >= $1 AND s.date < $2 GROUP BY 1) "
            "SELECT m.month, m.revenue FROM monthly AS m "
            "WHERE m.revenue > $3 ORDER BY m.revenue DESC LIMIT 20"
        )

        validated = validate_commerce_sql(sql)

        self.assertEqual(validated.sources, ("commerce.sales",))

    def test_rejects_unsafe_or_unbounded_sql(self):
        rejected = (
            "DELETE FROM commerce.products",
            "SELECT p.product_id FROM commerce.products AS p; SELECT 1",
            "SELECT pg_sleep(10) FROM commerce.products AS p LIMIT 1",
            "SELECT p.product_id FROM commerce.products AS p LIMIT 201",
            "SELECT p.email FROM commerce.products AS p LIMIT 1",
            "SELECT p.product_id FROM commerce.products AS p "
            "JOIN commerce.orders AS o ON p.product_id = o.order_id LIMIT 1",
        )
        for sql in rejected:
            with self.subTest(sql=sql), self.assertRaises(SQLValidationError):
                validate_commerce_sql(sql)

    def test_query_plan_requires_parameter_count_to_match_placeholders(self):
        with self.assertRaises(SQLValidationError):
            decode_query_plan(json.dumps({
                "sql": "SELECT p.product_id FROM commerce.products AS p "
                       "WHERE p.product_id = $1 LIMIT 1",
                "parameters": [],
            }))

    def test_accepts_parameterized_filtered_and_ranked_query(self):
        plan = decode_query_plan(json.dumps({
            "sql": "SELECT p.product_id, p.price FROM commerce.products AS p "
                   "WHERE p.category = $1 AND p.price > $2 "
                   "ORDER BY p.price DESC LIMIT 10",
            "parameters": ["Outdoor", 50],
        }))
        self.assertEqual(plan.parameters, ("Outdoor", 50))

    def test_accepts_extract_for_standard_date_grouping(self):
        sql = (
            "SELECT EXTRACT(MONTH FROM s.date) AS month, SUM(s.revenue) AS revenue "
            "FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 "
            "GROUP BY EXTRACT(MONTH FROM s.date) ORDER BY 1 LIMIT 12"
        )
        self.assertEqual(validate_commerce_sql(sql).sources, ("commerce.sales",))

    def test_date_column_parameters_are_converted_to_native_dates(self):
        plan = decode_query_plan(json.dumps({
            "sql": "SELECT r.return_reason FROM commerce.returns AS r "
                   "WHERE r.return_date >= $1 AND r.return_date < $2 LIMIT 20",
            "parameters": ["2022-01-01", "2023-01-01"],
        }))
        self.assertEqual(plan.parameters, (date(2022, 1, 1), date(2023, 1, 1)))

    def test_date_looking_text_filter_remains_a_string(self):
        plan = decode_query_plan(json.dumps({
            "sql": "SELECT r.return_id FROM commerce.returns AS r "
                   "WHERE r.return_reason = $1 LIMIT 20",
            "parameters": ["2022-01-01"],
        }))
        self.assertEqual(plan.parameters, ("2022-01-01",))

    def test_approved_customers_and_payments_tables_and_joins(self):
        customer_query = (
            "SELECT c.gender, COUNT(o.order_id) AS orders "
            "FROM commerce.customers AS c JOIN commerce.orders AS o "
            "ON c.customer_id = o.customer_id GROUP BY c.gender LIMIT 20"
        )
        payment_query = (
            "SELECT p.payment_method, SUM(p.payment_value) AS payment_total "
            "FROM commerce.payments AS p JOIN commerce.orders AS o "
            "ON p.order_id = o.order_id GROUP BY p.payment_method LIMIT 20"
        )
        self.assertEqual(validate_commerce_sql(customer_query).sources,
                         ("commerce.customers", "commerce.orders"))
        self.assertEqual(validate_commerce_sql(payment_query).sources,
                         ("commerce.payments", "commerce.orders"))


class SQLGenerationAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_current_year_in_latest_turn_overrides_planner_carried_prior_year(self):
        current_year = date.today().year
        sql = ('SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s '
               'WHERE s.date >= $1 AND s.date < $2 LIMIT 1')

        class LLM:
            def generate(self, prompt):
                raise AssertionError('Current year revenue uses the checked SQL plan')

        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{'revenue': 42}]
        result = await SQLAnalyticsAgent(repository, llm=LLM()).run(AgentRequest(
            question='Doanh thu năm 2025', identity=ANALYST,
            metadata={'_original_question': 'năm nay'}))

        self.assertTrue(result.metadata['ok'], result.answer)
        repository.execute_approved_query.assert_awaited_once_with(
            sql, date(current_year, 1, 1), date(current_year + 1, 1, 1))

    async def test_compiles_annual_revenue_as_one_aggregate_without_llm_sql(self):
        class LLM:
            def generate(self, prompt):
                raise AssertionError("A single calendar-year revenue total should use the checked SQL plan")

        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"revenue": 1234.5}]

        result = await SQLAnalyticsAgent(repository, llm=LLM()).run(
            AgentRequest(question="doanh thu năm 2025", identity=ANALYST))

        self.assertTrue(result.metadata["ok"], result.answer)
        self.assertEqual(result.data["rows"], [{"revenue": 1234.5}])
        self.assertTrue(any("completeness for the full year" in item
                            for item in result.metadata["limitations"]))
        sql, *parameters = repository.execute_approved_query.await_args.args
        self.assertIn("SUM(s.revenue)", sql)
        self.assertNotIn("GROUP BY", sql.upper())
        self.assertEqual(parameters, [date(2025, 1, 1), date(2026, 1, 1)])

    async def test_followup_summary_uses_original_question_language(self):
        class LLM:
            def __init__(self):
                self.prompts = []

            def generate(self, prompt):
                self.prompts.append(prompt)
                return "Doanh thu năm 2025 là 2.000 [S1]."

        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"revenue": 2000}]
        llm = LLM()
        analytics = AnalyticsAgent(SQLAnalyticsAgent(repository, llm=llm))

        result = await analytics.run(AgentRequest(
            question="Revenue for 2025", identity=ANALYST,
            metadata={"_original_question": "năm 2025"}))

        self.assertIn("Question: năm 2025", llm.prompts[0])
        self.assertTrue(result.answer.startswith("Doanh thu năm 2025"))

    async def test_compiles_explicit_month_revenue_without_llm_sql(self):
        class LLM:
            def generate(self, prompt):
                raise AssertionError("An explicit month revenue total should use the checked SQL plan")

        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{
            "month": date(2026, 2, 1), "revenue": 123.45,
        }]

        result = await SQLAnalyticsAgent(repository, llm=LLM()).run(
            AgentRequest(question="doanh thu tháng 2 năm 2026", identity=ANALYST,
                         metadata={"_original_question": "tháng trước thì sao"}))

        self.assertTrue(result.metadata["ok"], result.answer)
        self.assertEqual(result.data["rows"][0]["month"], date(2026, 2, 1))
        sql, *parameters = repository.execute_approved_query.await_args.args
        self.assertIn("AS month", sql)
        self.assertEqual(parameters, [date(2026, 2, 1), date(2026, 3, 1)])

    async def test_compiles_current_vs_previous_month_revenue_without_llm_sql(self):
        class LLM:
            def generate(self, prompt):
                raise AssertionError("A relative month comparison should use the checked SQL plan")

        today = date.today()
        current_start = date(today.year, today.month, 1)
        previous_start = date(today.year - (today.month == 1), 12 if today.month == 1 else today.month - 1, 1)
        next_start = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{
            "month": current_start, "previous_month": previous_start,
            "revenue": 100, "previous_month_revenue": 80,
            "revenue_change": 20, "revenue_change_fraction": .25,
        }]

        result = await SQLAnalyticsAgent(repository, llm=LLM()).run(
            AgentRequest(question="Compare this month's revenue with previous month", identity=ANALYST))

        self.assertTrue(result.metadata["ok"], result.answer)
        self.assertEqual(result.data["rows"][0]["revenue_change_fraction"], .25)
        sql, *parameters = repository.execute_approved_query.await_args.args
        self.assertIn("previous_month_revenue", sql)
        self.assertIn("FILTER (WHERE s.date >= $2 AND s.date < $3)", sql)
        self.assertEqual(parameters, [previous_start, current_start, next_start])

    async def test_resolves_model_year_to_current_month_before_execution(self):
        year = date.today().year
        sql = "SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 LIMIT 1"

        class LLM:
            def __init__(self):
                self.prompts = []
                self.responses = [json.dumps({"sql": sql, "parameters": ["2024-03-01", "2024-03-31"]})]

            def generate(self, prompt):
                if prompt.startswith("Interpret the question BEFORE"):
                    return json.dumps({"domain": "other"})
                self.prompts.append(prompt)
                return self.responses.pop(0)

        llm = LLM()
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"revenue": 100}]
        result = await SQLAnalyticsAgent(repository, llm=llm).run(
            AgentRequest(question="Revenue in March", identity=ANALYST,
                         metadata={"_original_question": "doanh thu tháng 3"}))

        self.assertTrue(result.metadata["ok"], result.answer)
        self.assertEqual(len(llm.prompts), 1)
        self.assertIn(f"bind {year}-03-01 as the inclusive start", llm.prompts[0])
        repository.execute_approved_query.assert_awaited_once_with(
            sql, date(year, 3, 1), date(year, 4, 1))

    async def test_current_month_daily_breakdown_is_repaired_to_one_total(self):
        year, month = date.today().year, date.today().month
        daily_sql = (
            "SELECT s.date, SUM(s.revenue) AS revenue FROM commerce.sales AS s "
            "WHERE s.date >= $1 AND s.date < $2 GROUP BY s.date LIMIT 200"
        )
        monthly_sql = (
            "SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s "
            "WHERE s.date >= $1 AND s.date < $2 LIMIT 1"
        )

        class LLM:
            def __init__(self):
                self.prompts = []
                self.responses = [
                    json.dumps({"sql": daily_sql, "parameters": ["2024-01-01", "2024-02-01"]}),
                    json.dumps({"sql": monthly_sql, "parameters": ["2024-01-01", "2024-02-01"]}),
                ]

            def generate(self, prompt):
                self.prompts.append(prompt)
                return self.responses.pop(0)

        llm = LLM()
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"revenue": 42}]
        request = AgentRequest(question="doanh thu tháng này sao", identity=ANALYST)
        result = await SQLAnalyticsAgent(repository, llm=llm).run(request)

        self.assertTrue(result.metadata["ok"], result.answer)
        self.assertEqual(len(llm.prompts), 2)
        self.assertIn("Do not group the result by day", llm.prompts[1])
        repository.execute_approved_query.assert_awaited_once_with(
            monthly_sql, date(year, month, 1), date(year + (month == 12), month % 12 + 1, 1))

    async def test_retries_validation_failure_with_feedback_for_generic_date_query(self):
        bad_sql = (
            "SELECT EXTRACT(YEAR FROM commerce.sales.date) AS year, "
            "EXTRACT(MONTH FROM commerce.sales.date) AS month, "
            "SUM(commerce.sales.revenue) AS revenue, SUM(commerce.sales.cogs) AS cogs "
            "FROM commerce.sales WHERE EXTRACT(YEAR FROM commerce.sales.date) = $1 "
            "GROUP BY 1, 2 ORDER BY 1, 2 LIMIT 200"
        )
        good_sql = (
            "SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue "
            "FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 "
            "GROUP BY DATE_TRUNC('month', s.date) ORDER BY 1 LIMIT 200"
        )

        class LLM:
            def __init__(self):
                self.prompts = []
                self.responses = [
                    json.dumps({"sql": bad_sql, "parameters": []}),
                    json.dumps({"sql": good_sql, "parameters": ["2021-01-01", "2022-01-01"]}),
                ]

            def generate(self, prompt):
                if prompt.startswith("Interpret the question BEFORE"):
                    return json.dumps({"domain":"other"})
                self.prompts.append(prompt)
                return self.responses.pop(0)

        llm = LLM()
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"month": "2021-01-01", "revenue": 20}]
        result = await SQLAnalyticsAgent(repository, llm=llm).run(
            AgentRequest(question="Show monthly revenue for 2021", identity=ANALYST))

        self.assertTrue(result.metadata["ok"])
        self.assertEqual(len(llm.prompts), 2)
        self.assertIn("SQL placeholders must match", llm.prompts[1])
        repository.execute_approved_query.assert_awaited_once_with(
            good_sql, date(2021, 1, 1), date(2022, 1, 1))

    async def test_retries_comparison_query_when_final_limit_is_missing(self):
        invalid_sql = (
            "SELECT DATE_PART('year', s.date) AS year, SUM(s.revenue) AS revenue "
            "FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 GROUP BY 1 ORDER BY 1"
        )
        valid_sql = invalid_sql + ' LIMIT 200'

        class LLM:
            def __init__(self):
                self.prompts = []
                self.responses = [
                    json.dumps({'sql': invalid_sql, 'parameters': ['2025-01-01', '2027-01-01']}),
                    json.dumps({'sql': valid_sql, 'parameters': ['2025-01-01', '2027-01-01']}),
                ]

            def generate(self, prompt):
                if prompt.startswith('Interpret the question BEFORE'):
                    return json.dumps({'domain': 'other'})
                self.prompts.append(prompt)
                return self.responses.pop(0)

        repository = AsyncMock()
        repository.execute_approved_query.return_value = [
            {'year': 2025, 'revenue': 10}, {'year': 2026, 'revenue': 20}]
        llm = LLM()
        result = await SQLAnalyticsAgent(repository, llm=llm).run(AgentRequest(
            question='Compare revenue for 2025 and 2026', identity=ANALYST))

        self.assertTrue(result.metadata['ok'], result.answer)
        self.assertEqual(len(llm.prompts), 2)
        self.assertIn('final SELECT MUST contain an explicit LIMIT', llm.prompts[0])
        self.assertIn('The final SELECT needs LIMIT 1..200', llm.prompts[1])
        repository.execute_approved_query.assert_awaited_once_with(
            valid_sql, date(2025, 1, 1), date(2027, 1, 1))

    async def test_retries_year_comparison_at_daily_grain(self):
        invalid_sql = (
            'SELECT CAST(s.date AS DATE) AS date, SUM(s.revenue) AS sum '
            'FROM commerce.sales AS s WHERE EXTRACT(YEAR FROM s.date) = $1 '
            'OR EXTRACT(YEAR FROM s.date) = $2 GROUP BY 1 ORDER BY 1 DESC LIMIT 1'
        )
        valid_sql = (
            'SELECT EXTRACT(YEAR FROM s.date) AS year, SUM(s.revenue) AS revenue '
            'FROM commerce.sales AS s WHERE EXTRACT(YEAR FROM s.date) = $1 '
            'OR EXTRACT(YEAR FROM s.date) = $2 GROUP BY 1 ORDER BY 1 LIMIT 200'
        )

        class LLM:
            def __init__(self):
                self.prompts = []
                self.responses = [
                    json.dumps({'sql': invalid_sql, 'parameters': [2025, 2026]}),
                    json.dumps({'sql': valid_sql, 'parameters': [2025, 2026]}),
                ]

            def generate(self, prompt):
                if prompt.startswith('Interpret the question BEFORE'):
                    return json.dumps({'domain': 'other'})
                self.prompts.append(prompt)
                return self.responses.pop(0)

        repository = AsyncMock()
        repository.execute_approved_query.return_value = [
            {'year': 2025, 'revenue': 10}, {'year': 2026, 'revenue': 20}]
        llm = LLM()
        result = await SQLAnalyticsAgent(repository, llm=llm).run(AgentRequest(
            question='compare the revenue of 2025 and 2026', identity=ANALYST))

        self.assertTrue(result.metadata['ok'], result.answer)
        self.assertEqual(len(llm.prompts), 2)
        self.assertIn('separate aggregate per year', llm.prompts[1])
        repository.execute_approved_query.assert_awaited_once_with(valid_sql, 2025, 2026)

    async def test_passes_native_date_parameters_to_repository(self):
        sql = (
            "SELECT r.return_reason, COUNT(*) AS number_of_returns "
            "FROM commerce.returns AS r WHERE r.return_date >= $1 "
            "AND r.return_date < $2 GROUP BY r.return_reason LIMIT 200"
        )

        class LLM:
            def generate(self, prompt):
                if prompt.startswith("Interpret the question BEFORE"):
                    return json.dumps({"domain":"other"})
                return json.dumps({"sql": sql, "parameters": ["2022-01-01", "2023-01-01"]})

        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"return_reason": "Size", "number_of_returns": 4}]
        agent = SQLAnalyticsAgent(repository, llm=LLM())

        await agent.run(AgentRequest(question="Returns by reason in 2022", identity=ANALYST))

        repository.execute_approved_query.assert_awaited_once_with(
            sql, date(2022, 1, 1), date(2023, 1, 1),
        )

    async def test_executes_only_the_validated_generated_plan(self):
        sql = "SELECT p.category, COUNT(*) AS products FROM commerce.products AS p GROUP BY p.category LIMIT 20"

        class LLM:
            def generate(self, prompt):
                if prompt.startswith("Interpret the question BEFORE"):
                    return json.dumps({"domain":"other"})
                return json.dumps({"sql": sql, "parameters": [], "explanation": "Products by category"})

        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"category": "Outdoor", "products": 12}]
        agent = SQLAnalyticsAgent(repository, llm=LLM())

        result = await agent.run(AgentRequest(question="How many products are in each category?", identity=ANALYST))

        repository.execute_approved_query.assert_awaited_once_with(sql)
        self.assertEqual(result.data["rows"], [{"category": "Outdoor", "products": 12}])
        self.assertEqual(result.data["sql"], sql)
        self.assertEqual(result.data["query_status"], "executed")

    async def test_analytics_summary_is_grounded_and_keeps_rows_and_sources(self):
        start = date(date.today().year, 3, 1)
        end = date(date.today().year, 4, 1)
        sql = ("SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s "
               "WHERE s.date >= $1 AND s.date < $2 LIMIT 1")

        class LLM:
            def __init__(self):
                self.responses = [json.dumps({"sql": sql, "parameters": [start.isoformat(), end.isoformat()]}),
                                  "March revenue was 2,248,522.83."]
                self.prompts = []

            def generate(self, prompt):
                if prompt.startswith("Interpret the question BEFORE"):
                    return json.dumps({"domain":"other"})
                self.prompts.append(prompt)
                return self.responses.pop(0)

        llm = LLM()
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"revenue": 2248522.83}]
        agent = AnalyticsAgent(SQLAnalyticsAgent(repository, llm=llm))

        result = await agent.run(AgentRequest(question="Doanh thu tháng 3 năm nay là bao nhiêu?", identity=ANALYST))

        self.assertTrue(result.answer.startswith("March revenue was 2,248,522.83."))
        self.assertIn("[S1] commerce.sales", result.answer)
        self.assertIn("Cite factual claims with the supplied [S#] references", llm.prompts[-1])
        self.assertIn("Use the language of the question", llm.prompts[-1])
        self.assertIn('"sql": "SELECT SUM(s.revenue)', llm.prompts[-1])
        self.assertIn(f'"{start.isoformat()}"', llm.prompts[-1])
        self.assertIn('"revenue": 2248522.83', llm.prompts[-1])
        self.assertEqual(result.data["rows"][0]["revenue"], 2248522.83)
        self.assertEqual(result.evidence[0].source, "commerce.sales")

    async def test_month_comparison_has_deterministic_human_readable_summary(self):
        class SQLAgent:
            async def run_payload(self, request):
                return {
                    "ok": True,
                    "rows": [{
                        "month": "2026-11-01", "previous_month": "2026-10-01",
                        "revenue": "1000968.55", "previous_month_revenue": "1754342.36",
                        "revenue_change": "-753373.81", "revenue_change_fraction": "-0.4294337",
                    }],
                    "metadata": {"source": ["commerce.sales"]},
                    "limitations": [],
                }

            def _provider(self):
                raise AssertionError("This checked comparison should not need an LLM summary")

        result = await AnalyticsAgent(SQLAgent()).run_payload(
            AgentRequest(question="so sánh với tháng trước", identity=ANALYST))

        self.assertIn("1,000,968.55", result["answer"])
        self.assertIn("1,754,342.36", result["answer"])
        self.assertIn("-42.94%", result["answer"])
        self.assertNotIn("Evidence fallback", result["answer"])

    async def test_summary_failure_returns_rows_and_deterministic_answer(self):
        sql = "SELECT p.product_id FROM commerce.products AS p LIMIT 20"

        class LLM:
            def __init__(self):
                self.calls = 0

            def generate(self, prompt):
                if prompt.startswith("Interpret the question BEFORE"):
                    return json.dumps({"domain":"other"})
                self.calls += 1
                if self.calls == 1:
                    return json.dumps({"sql": sql, "parameters": []})
                raise RuntimeError("summary unavailable")

        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"product_id": 42}]
        agent = AnalyticsAgent(SQLAnalyticsAgent(repository, llm=LLM()))

        result = await agent.run(AgentRequest(question="List products", identity=ANALYST))

        self.assertIn("1 row", result.answer)
        self.assertEqual(result.data["rows"], [{"product_id": 42}])

    async def test_requires_verified_analytics_permission_before_generation(self):
        llm = AsyncMock()
        agent = SQLAnalyticsAgent(AsyncMock(), llm=llm)

        with self.assertRaises(AnalyticsPermissionDenied):
            await agent.run(AgentRequest(question="List products"))

        llm.generate.assert_not_called()

    async def test_empty_results_and_database_failures_are_explicit(self):
        class LLM:
            def generate(self, prompt):
                if prompt.startswith("Interpret the question BEFORE"):
                    return json.dumps({"domain":"other"})
                return json.dumps({"sql": "SELECT p.product_id FROM commerce.products AS p LIMIT 20",
                                   "parameters": []})

        empty_repository = AsyncMock()
        empty_repository.execute_approved_query.return_value = []
        empty = await SQLAnalyticsAgent(empty_repository, llm=LLM()).run(
            AgentRequest(question="List products", identity=ANALYST))
        self.assertFalse(empty.metadata["ok"])
        self.assertEqual(empty.data["rows"], [])
        self.assertIn("No matching rows", empty.answer)

        failed_repository = AsyncMock()
        failed_repository.execute_approved_query.side_effect = RuntimeError("private database details")
        failed = await SQLAnalyticsAgent(failed_repository, llm=LLM()).run(
            AgentRequest(question="List products", identity=ANALYST))
        self.assertFalse(failed.metadata["ok"])
        self.assertNotIn("private database details", failed.answer)
        self.assertTrue(failed.data["attempted_sql"].startswith("SELECT"))
        self.assertEqual(failed.data["query_status"], "error")

    async def test_unsafe_generated_query_never_reaches_repository(self):
        class LLM:
            def generate(self, prompt):
                if prompt.startswith("Interpret the question BEFORE"):
                    return json.dumps({"domain":"other"})
                return json.dumps({"sql": "DELETE FROM commerce.products", "parameters": []})

        repository = AsyncMock()
        result = await SQLAnalyticsAgent(repository, llm=LLM()).run(
            AgentRequest(question="Remove products", identity=ANALYST))
        self.assertFalse(result.metadata["ok"])
        self.assertEqual(result.data["attempted_sql"], "DELETE FROM commerce.products")
        self.assertEqual(result.data["query_status"], "rejected")
        repository.execute_approved_query.assert_not_awaited()


class RepositoryBoundaryTest(unittest.IsolatedAsyncioTestCase):
    async def test_repository_revalidates_before_read_only_execution(self):
        class Transaction:
            def __init__(self, connection, readonly):
                self.connection, self.readonly = connection, readonly

            async def __aenter__(self):
                self.connection.readonly = self.readonly
                return self

            async def __aexit__(self, *_args):
                return False

        class Connection:
            def transaction(self, *, readonly=False):
                return Transaction(self, readonly)

            async def execute(self, sql, **options):
                self.timeout_sql = sql
                self.execute_options = options

            async def fetch(self, sql, *parameters, **options):
                self.fetch_call = (sql, parameters)
                self.fetch_options = options
                return [{"product_id": 42}]

        class Acquire:
            def __init__(self, connection):
                self.connection = connection

            async def __aenter__(self):
                return self.connection

            async def __aexit__(self, *_args):
                return False

        class Pool:
            def __init__(self):
                self.connection = Connection()
                self.acquire_count = 0

            def acquire(self, **options):
                self.acquire_count += 1
                self.acquire_options = options
                return Acquire(self.connection)

        pool = Pool()
        repository = CommerceRepository(pool)
        sql = "SELECT p.product_id FROM commerce.products AS p WHERE p.product_id = $1 LIMIT 10"
        rows = await repository.execute_approved_query(sql, 42)
        self.assertEqual(rows, [{"product_id": 42}])
        self.assertTrue(pool.connection.readonly)
        self.assertIn("statement_timeout", pool.connection.timeout_sql)
        self.assertEqual(pool.connection.fetch_call[1], (42,))

        with self.assertRaises(SQLValidationError):
            await repository.execute_approved_query("DELETE FROM commerce.products")
        self.assertEqual(pool.acquire_count, 1)
        self.assertEqual(pool.acquire_options, {})
        from core.agents.runtime import deadline
        import time
        token = deadline.set(time.monotonic()+2)
        try:
            await repository.execute_approved_query(sql, 42)
        finally:
            deadline.reset(token)
        for options in (pool.acquire_options, pool.connection.execute_options, pool.connection.fetch_options):
            self.assertGreater(options['timeout'], 0)
            self.assertLessEqual(options['timeout'], 2)

    async def test_unverified_repository_path_skips_semantics_but_keeps_security(self):
        class Connection:
            def transaction(self, *, readonly=False):
                class Transaction:
                    async def __aenter__(self):
                        return self
                    async def __aexit__(self, *_args):
                        return False
                self.readonly = readonly
                return Transaction()
            async def execute(self, _sql, **_options):
                pass
            async def fetch(self, sql, *parameters, **_options):
                self.query = sql
                return [{'average_shipping_fee': 12}]

        class Acquire:
            async def __aenter__(self):
                return connection
            async def __aexit__(self, *_args):
                return False

        class Pool:
            def acquire(self, **_options):
                return Acquire()

        connection = Connection()
        repository = CommerceRepository(Pool())
        sql = ('SELECT AVG(s.shipping_fee) AS average_shipping_fee FROM commerce.shipments AS s '
               'JOIN commerce.customers AS c ON s.order_id = c.customer_id LIMIT 1')
        self.assertEqual(await repository.execute_unverified_query(sql), [{'average_shipping_fee': 12}])
        self.assertIn('JOIN commerce.customers', connection.query)
        self.assertTrue(connection.readonly)
        with self.assertRaises(SQLValidationError):
            await repository.execute_unverified_query('DELETE FROM commerce.shipments')


if __name__ == "__main__":
    unittest.main()
