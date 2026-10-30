import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.analytics.metric_ontology import METRIC_ONTOLOGY, get_metric_definition
from core.analytics.text_to_sql import APPROVED_COLUMNS, SQLValidationError, build_sql_prompt, decode_query_plan
from core.agents.analytics_agent import AnalyticsAgent
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.models.agents import AgentRequest, VerifiedIdentity


class MetricPlanningTest(unittest.TestCase):
    def test_prompt_contains_authoritative_metric_details(self):
        prompt = build_sql_prompt("What is regional revenue?")
        self.assertIn("Canonical metric definitions", prompt)
        self.assertIn(json.dumps(get_metric_definition("regional_revenue"), ensure_ascii=False), prompt)
        self.assertIn("dataset_currency_unknown", prompt)
        self.assertIn("orders.order_status = 'delivered'", prompt)

    def test_prompt_distinguishes_metrics_from_generic_queries(self):
        self.assertIn('"metrics": ["revenue"]', build_sql_prompt("Total revenue in 2022"))
        self.assertIn('"metrics": []', build_sql_prompt("List products"))
        self.assertIn("Do not invent a metric definition", build_sql_prompt("List products"))

    def test_repair_prompt_keeps_metric_definitions(self):
        prompt = build_sql_prompt("Average order value", validation_error="wrong formula", previous_response="{}")
        self.assertIn(get_metric_definition("average_order_value")["formula"], prompt)
        self.assertIn("wrong formula", prompt)


class MetricEnforcementTest(unittest.TestCase):
    def validate(self, sql, names, parameters=()):
        from core.analytics.metric_validation import validate_metric_definitions
        return validate_metric_definitions(sql, names, parameters, APPROVED_COLUMNS)

    def test_accepts_canonical_revenue_with_arbitrary_alias_and_transparent_cte(self):
        for sql in (
            "SELECT SUM(s.revenue) AS total FROM commerce.sales AS s LIMIT 1",
            "WITH m AS (SELECT SUM(s.revenue) AS total FROM commerce.sales AS s) "
            "SELECT m.total FROM m LIMIT 1",
        ):
            with self.subTest(sql=sql):
                definitions = self.validate(sql, {"revenue"})
                self.assertEqual(definitions["revenue"]["formula"], "SUM(revenue)")

    def test_rejects_wrong_formula_source_or_missing_requested_metric(self):
        from core.analytics.metric_validation import MetricDefinitionError
        queries = (
            "SELECT AVG(s.revenue) AS revenue FROM commerce.sales AS s LIMIT 1",
            "SELECT SUM(p.payment_value) AS revenue FROM commerce.payments AS p LIMIT 1",
            "SELECT SUM(s.cogs) AS cogs FROM commerce.sales AS s LIMIT 1",
            "SELECT SUM(s.revenue) AS good, AVG(s.revenue) AS wrong FROM commerce.sales AS s LIMIT 1",
            "SELECT SUM(s.revenue) + 1 AS revenue FROM commerce.sales AS s LIMIT 1",
        )
        for sql in queries:
            with self.subTest(sql=sql), self.assertRaises(MetricDefinitionError):
                self.validate(sql, {"revenue"})

    def test_order_count_requires_distinct_orders(self):
        from core.analytics.metric_validation import MetricDefinitionError
        self.validate("SELECT COUNT(DISTINCT o.order_id) AS n FROM commerce.orders AS o LIMIT 1", {"order_count"})
        with self.assertRaises(MetricDefinitionError):
            self.validate("SELECT COUNT(o.order_id) AS n FROM commerce.orders AS o LIMIT 1", {"order_count"})

    def test_regional_revenue_requires_the_delivered_filter(self):
        from core.analytics.metric_validation import MetricDefinitionError
        sql = (
            "SELECT g.region, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue "
            "FROM commerce.orders AS o JOIN commerce.order_items AS oi ON o.order_id = oi.order_id "
            "JOIN commerce.geography AS g ON o.zip = g.zip "
        )
        self.validate(sql + "WHERE o.order_status = $1 GROUP BY g.region LIMIT 20", {"regional_revenue"}, ("delivered",))
        for predicate, parameters in (
            ("", ()),
            ("WHERE o.order_status = $1", ("cancelled",)),
            ("WHERE o.order_status = 'delivered' OR o.order_status = 'cancelled'", ()),
        ):
            with self.subTest(predicate=predicate), self.assertRaises(MetricDefinitionError):
                self.validate(sql + predicate + " GROUP BY g.region LIMIT 20", {"regional_revenue"}, parameters)

    def test_metric_dimensions_and_snapshot_grain_are_enforced(self):
        from core.analytics.metric_validation import MetricDefinitionError
        self.validate(
            "SELECT i.snapshot_date, AVG(i.days_of_supply) FROM commerce.inventory AS i "
            "GROUP BY i.snapshot_date LIMIT 20", {"days_of_supply"})
        for sql, metric in (
            ("SELECT s.cogs, SUM(s.revenue) FROM commerce.sales AS s GROUP BY s.cogs LIMIT 20", "revenue"),
            ("SELECT AVG(i.days_of_supply) FROM commerce.inventory AS i LIMIT 1", "days_of_supply"),
            ("SELECT DATE_TRUNC('month', i.snapshot_date), AVG(i.days_of_supply) "
             "FROM commerce.inventory AS i GROUP BY 1 LIMIT 20", "days_of_supply"),
            ("SELECT AVG(i.days_of_supply) FROM commerce.inventory AS i "
             "WHERE i.snapshot_date = $1 OR i.category = $2 LIMIT 1", "days_of_supply"),
        ):
            with self.subTest(sql=sql), self.assertRaises(MetricDefinitionError):
                self.validate(sql, {metric}, ("2022-12-31", "Outdoor"))

    def test_canonical_metric_label_cannot_disguise_another_formula(self):
        from core.analytics.metric_validation import MetricDefinitionError
        with self.assertRaises(MetricDefinitionError):
            self.validate("SELECT SUM(s.cogs) AS revenue, SUM(s.revenue) AS total FROM commerce.sales AS s LIMIT 1", {"revenue"})

    def test_generic_queries_are_not_restricted_to_ontology_metrics(self):
        self.assertEqual(self.validate("SELECT p.product_id FROM commerce.products AS p LIMIT 10", set()), {})

    def test_supplementary_counts_do_not_replace_or_restrict_requested_metrics(self):
        self.validate(
            "SELECT AVG(sh.delivery_date - sh.ship_date) AS delivery_time, COUNT(sh.order_id) AS shipments "
            "FROM commerce.shipments AS sh LIMIT 1", {"delivery_time"})

    def test_canonical_examples_for_every_existing_metric_pass_both_validators(self):
        sales = " FROM commerce.sales AS s LIMIT 1"
        inventory = " FROM commerce.inventory AS i WHERE i.snapshot_date = $1 LIMIT 1"
        items = (" FROM commerce.orders AS o JOIN commerce.order_items AS oi ON o.order_id = oi.order_id ")
        examples = {
            "revenue": ("SELECT SUM(s.revenue)" + sales, []),
            "cogs": ("SELECT SUM(s.cogs)" + sales, []),
            "gross_profit": ("SELECT SUM(s.revenue) - SUM(s.cogs)" + sales, []),
            "regional_revenue": ("SELECT SUM(oi.quantity * oi.unit_price - oi.discount_amount)" + items
                                 + "WHERE o.order_status = $1 LIMIT 1", ["delivered"]),
            "order_count": ("SELECT COUNT(DISTINCT o.order_id) FROM commerce.orders AS o LIMIT 1", []),
            "average_order_value": ("SELECT SUM(oi.quantity * oi.unit_price - oi.discount_amount) / "
                                    "COUNT(DISTINCT o.order_id)" + items + "LIMIT 1", []),
            "return_rate": ("SELECT COUNT(DISTINCT r.order_id)::numeric / NULLIF(COUNT(DISTINCT o.order_id), 0) "
                            "FROM commerce.orders AS o LEFT JOIN commerce.returns AS r ON o.order_id = r.order_id LIMIT 1", []),
            "rating": ("SELECT AVG(r.rating) FROM commerce.reviews AS r LIMIT 1", []),
            "sessions": ("SELECT SUM(w.sessions) FROM commerce.web_traffic AS w LIMIT 1", []),
            "bounce_rate": ("SELECT AVG(w.bounce_rate) FROM commerce.web_traffic AS w LIMIT 1", []),
            "delivery_time": ("SELECT AVG(sh.delivery_date - sh.ship_date) FROM commerce.shipments AS sh LIMIT 1", []),
            "stock_on_hand": ("SELECT SUM(i.stock_on_hand)" + inventory, ["2022-12-31"]),
            "stockout_rate": ("SELECT COUNT(*) FILTER (WHERE i.stockout_flag IS TRUE)::numeric / NULLIF(COUNT(*), 0)"
                              + inventory, ["2022-12-31"]),
            "days_of_supply": ("SELECT AVG(i.days_of_supply)" + inventory, ["2022-12-31"]),
            "fill_rate": ("SELECT AVG(i.fill_rate)" + inventory, ["2022-12-31"]),
            "sell_through_rate": ("SELECT AVG(i.sell_through_rate)" + inventory, ["2022-12-31"]),
            "promotion_discount": ("SELECT SUM(oi.discount_amount) FROM commerce.order_items AS oi LIMIT 1", []),
        }
        self.assertTrue(set(examples) <= set(METRIC_ONTOLOGY))
        self.assertEqual({name for name, definition in METRIC_ONTOLOGY.items()
                          if definition.get("domain") != "inventory_management"},
                         {name for name in examples if METRIC_ONTOLOGY[name].get("domain") != "inventory_management"})
        for name, (sql, parameters) in examples.items():
            with self.subTest(metric=name):
                plan = decode_query_plan(json.dumps({"sql": sql, "parameters": parameters}))
                self.assertIn(name, self.validate(plan.sql, {name}, plan.parameters))

    def test_casts_to_unapproved_types_remain_blocked(self):
        with self.assertRaises(SQLValidationError):
            decode_query_plan(json.dumps({"sql": "SELECT CAST(o.order_id AS regclass) FROM commerce.orders AS o LIMIT 1"}))


class MetricAgentTest(unittest.IsolatedAsyncioTestCase):
    def request(self, question):
        return AgentRequest(question=question, identity=VerifiedIdentity(subject="analyst", permissions={"analytics:read"}))

    def provider(self, *responses):
        class Provider:
            def __init__(self):
                self.responses = iter(responses)
                self.prompts = []

            def generate(self, prompt):
                self.prompts.append(prompt)
                return next(self.responses)
        return Provider()

    async def test_wrong_metric_is_repaired_before_execution(self):
        wrong = "SELECT AVG(s.revenue) AS revenue FROM commerce.sales AS s LIMIT 1"
        correct = "SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s LIMIT 1"
        llm = self.provider(*(json.dumps({"sql": sql}) for sql in (wrong, correct)))
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"revenue": 200}]
        result = await SQLAnalyticsAgent(repository, llm=llm).run(self.request("Total revenue"))
        self.assertTrue(result.metadata["ok"])
        repository.execute_approved_query.assert_awaited_once_with(correct)
        self.assertIn("metric", llm.prompts[1].lower())
        self.assertEqual(result.metadata["metrics"]["revenue"]["currency"], "dataset_currency_unknown")

    async def test_repeated_metric_violation_never_executes(self):
        wrong = json.dumps({
            "sql": "SELECT SUM(s.revenue) AS gross_profit FROM commerce.sales AS s LIMIT 1",
            "metrics": {"gross_profit": {"formula": "SUM(revenue)"}},
        })
        repository = AsyncMock()
        result = await SQLAnalyticsAgent(repository, llm=self.provider(wrong, wrong)).run(self.request("Gross profit"))
        self.assertFalse(result.metadata["ok"])
        repository.execute_approved_query.assert_not_awaited()

    async def test_repaired_revenue_returns_the_fixture_total_not_the_average(self):
        with sqlite3.connect(":memory:") as database:
            database.row_factory = sqlite3.Row
            database.execute("ATTACH DATABASE ':memory:' AS commerce")
            database.execute("CREATE TABLE commerce.sales (revenue NUMERIC, cogs NUMERIC)")
            database.executemany("INSERT INTO commerce.sales VALUES (?, ?)", [(10, 4), (30, 14)])
            self.assertEqual(database.execute("SELECT AVG(revenue) FROM commerce.sales").fetchone()[0], 20)
            wrong = "SELECT AVG(s.revenue) AS revenue FROM commerce.sales AS s LIMIT 1"
            correct = "SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s LIMIT 1"
            llm = self.provider(*(json.dumps({"sql": sql}) for sql in (wrong, correct)))
            repository = AsyncMock()
            repository.execute_approved_query.side_effect = lambda sql: [dict(row) for row in database.execute(sql)]
            result = await SQLAnalyticsAgent(repository, llm=llm).run(self.request("Total revenue"))
            self.assertEqual(result.data["rows"], [{"revenue": 40}])
            repository.execute_approved_query.assert_awaited_once_with(correct)

    async def test_ratio_rows_preserve_the_canonical_fraction(self):
        query = json.dumps({"sql": "SELECT COUNT(*) FILTER (WHERE i.stockout_flag IS TRUE)::numeric / "
                           "NULLIF(COUNT(*), 0) AS rate FROM commerce.inventory AS i "
                           "WHERE i.snapshot_date = '2022-12-31' LIMIT 1"})
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"rate": 0.25}]
        result = await SQLAnalyticsAgent(repository, llm=self.provider(query)).run(self.request("Stockout rate on 2022-12-31"))
        self.assertEqual(result.data["rows"], [{"rate": 0.25}])
        self.assertEqual(result.metadata["metrics"]["stockout_rate"]["unit"], "percent")
        self.assertTrue(any("fractions" in note for note in result.metadata["limitations"]))

    async def test_summary_receives_enforced_units_and_limitations(self):
        query = json.dumps({"sql": "SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s LIMIT 1"})
        llm = self.provider(query, "Revenue is 200 in unspecified currency.")
        repository = AsyncMock()
        repository.execute_approved_query.return_value = [{"revenue": 200}]
        result = await AnalyticsAgent(SQLAnalyticsAgent(repository, llm=llm)).run(self.request("Total revenue"))
        self.assertIn("dataset_currency_unknown", llm.prompts[-1])
        self.assertIn("Canonical metric definitions", llm.prompts[-1])
        self.assertIn("currency", " ".join(result.metadata["limitations"]).lower())


if __name__ == "__main__":
    unittest.main()
