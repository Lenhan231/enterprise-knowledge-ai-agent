import unittest
from unittest.mock import AsyncMock

from core.agents.sql.agent import SQLAnalyticsAgent
from core.agents.sql.compiler_dispatch import compile_fixed_query, match_fixed_query
from core.agents.sql.metric_mapping import MetricMapping, MetricTime, compile_inventory_query
from core.agents.sql.metric_validation import (
    MetricDefinitionError,
    validate_monthly_year_comparison,
    validate_snapshot_label_sources,
)
from core.agents.sql.text_to_sql import build_sql_prompt
from core.models.agents import AgentRequest, VerifiedIdentity


class SQLBenchmarkRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_undefined_previous_period_clarifies_before_sql(self):
        repository = AsyncMock()
        repository.get_schema.return_value = {}
        agent = SQLAnalyticsAgent(repository, inventory_only=False)
        for question in ("How much did revenue increase compared with the previous period?",
                         "Doanh thu tăng bao nhiêu so với kỳ trước?"):
            payload = await agent.run_payload(AgentRequest(
                question=question, identity=VerifiedIdentity(subject="test", permissions={"analytics:read"})))
            self.assertEqual(payload["metadata"]["status"], "clarification_required")
        repository.execute_approved_query.assert_not_awaited()
        repository.execute_unverified_query.assert_not_awaited()

    def test_monthly_year_comparison_rejects_full_date_equality(self):
        question = "Compare 2024 gross profit by month with the previous year."
        query = '''
            WITH a AS (SELECT DATE_TRUNC('month', s.date) AS month FROM commerce.sales AS s),
                 b AS (SELECT DATE_TRUNC('month', s.date) AS month FROM commerce.sales AS s)
            SELECT a.month FROM a LEFT JOIN b ON a.month = b.month LIMIT 12
        '''
        with self.assertRaisesRegex(MetricDefinitionError, "month of year"):
            validate_monthly_year_comparison(query, question)
        valid = query.replace("a.month = b.month", "EXTRACT(MONTH FROM a.month) = EXTRACT(MONTH FROM b.month)")
        validate_monthly_year_comparison(valid, question)
        validate_monthly_year_comparison(query, "List matching full dates")
        self.assertIn("absolute difference", build_sql_prompt(question))
        self.assertNotIn("absolute difference", build_sql_prompt("Show last year’s gross profit by month."))

    def test_historical_inventory_labels_are_available_and_catalog_label_is_rejected(self):
        question = "At snapshot 2024-06-30, group units received by segment."
        prompt = build_sql_prompt(question, metric_names={"units_received"})
        self.assertIn("Use commerce.inventory.segment", prompt)
        wrong = '''
            SELECT p.segment, SUM(i.units_received)
            FROM commerce.inventory AS i JOIN commerce.products AS p ON i.product_id = p.product_id
            GROUP BY p.segment LIMIT 200
        '''
        with self.assertRaisesRegex(MetricDefinitionError, "inventory.segment"):
            validate_snapshot_label_sources(wrong, question)
        validate_snapshot_label_sources(wrong.replace("p.segment", "i.segment"), question)
        validate_snapshot_label_sources(wrong, question.replace("by segment", "by current catalog segment"))
        mapping = MetricMapping(metrics=["units_received"], dimensions=["segment"],
                                snapshot_labels=["segment"], time=MetricTime(mode="snapshot", start="2024-06-30"))
        compiled, params = compile_inventory_query(mapping)
        self.assertIn("commerce.inventory.segment", compiled)
        self.assertNotIn("commerce.products.segment", compiled)
        self.assertEqual(params[0].isoformat(), "2024-06-30")

    def test_snapshot_summaries_preserve_zero_counts_and_nulls(self):
        stockouts = "At snapshot 2024-06-30, count products with stockout_flag = TRUE by category."
        plan = compile_fixed_query(match_fixed_query(stockouts)).plan
        self.assertIn("COUNT(*) FILTER (WHERE i.stockout_flag = TRUE)", plan.sql)
        self.assertIn("WHERE i.snapshot_date = $1 GROUP BY i.category", plan.sql)
        self.assertFalse(match_fixed_query(stockouts + " For Outdoor only.").matched)

        supply = ("At snapshot 2024-06-30, average days_of_supply by recorded category and "
                  "report non-NULL and NULL counts. Do not replace NULL with 0.")
        query = compile_fixed_query(match_fixed_query(supply)).plan.sql
        self.assertIn("AVG(i.days_of_supply)", query)
        self.assertIn("COUNT(i.days_of_supply)", query)
        self.assertIn("COUNT(*) FILTER (WHERE i.days_of_supply IS NULL)", query)
