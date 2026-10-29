import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.analytics.text_to_sql import SQLValidationError, decode_query_plan, validate_commerce_sql
from core.agents.sql_analytics_agent import AnalyticsPermissionDenied, SQLAnalyticsAgent
from core.agents.analytics_agent import AnalyticsAgent
from core.database.commerce_repository import CommerceRepository
from core.models.agents import AgentRequest, VerifiedIdentity


ANALYST = VerifiedIdentity(subject="analyst-1", permissions={"analytics:read"})


class SQLValidationTest(unittest.TestCase):
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

    async def test_passes_native_date_parameters_to_repository(self):
        sql = (
            "SELECT r.return_reason, COUNT(*) AS number_of_returns "
            "FROM commerce.returns AS r WHERE r.return_date >= $1 "
            "AND r.return_date < $2 GROUP BY r.return_reason LIMIT 200"
        )

        class LLM:
            def generate(self, _prompt):
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
            def generate(self, _prompt):
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
        sql = "SELECT p.category, COUNT(*) AS products FROM commerce.products AS p GROUP BY p.category LIMIT 20"

        class LLM:
            def __init__(self):
                self.responses = [json.dumps({"sql": sql, "parameters": []}), "Outdoor has 12 products."]
                self.prompts = []

            def generate(self, prompt):
                self.prompts.append(prompt)
                return self.responses.pop(0)

        llm = LLM()
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"category": "Outdoor", "products": 12}]
        agent = AnalyticsAgent(SQLAnalyticsAgent(repository, llm=llm))

        result = await agent.run(AgentRequest(question="How many products are in each category?", identity=ANALYST))

        self.assertTrue(result.answer.startswith("Outdoor has 12 products."))
        self.assertIn("[S1] commerce.products", result.answer)
        self.assertIn("Cite factual claims with the supplied [S#] references", llm.prompts[-1])
        self.assertIn('"products": 12', llm.prompts[-1])
        self.assertEqual(result.data["rows"][0]["category"], "Outdoor")
        self.assertEqual(result.evidence[0].source, "commerce.products")

    async def test_summary_failure_returns_rows_and_deterministic_answer(self):
        sql = "SELECT p.product_id FROM commerce.products AS p LIMIT 20"

        class LLM:
            def __init__(self):
                self.calls = 0

            def generate(self, _prompt):
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
            def generate(self, _prompt):
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
            def generate(self, _prompt):
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

            async def execute(self, sql):
                self.timeout_sql = sql

            async def fetch(self, sql, *parameters):
                self.fetch_call = (sql, parameters)
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

            def acquire(self):
                self.acquire_count += 1
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


if __name__ == "__main__":
    unittest.main()
