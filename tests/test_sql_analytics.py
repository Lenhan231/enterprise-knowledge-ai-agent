from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
import os

import httpx
from openai import RateLimitError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.sql_analytics_agent import (
    SQLAnalyticsAgent, UnsupportedCommerceDimension, _asks_for_promotion_tag_comparison,
    _asks_for_campaign_scoped_outcomes,
    _inventory_question_needs_latest_snapshot, _validate_repeated_inventory_flags,
    _validate_campaign_outcome_query,
    _validate_requested_year_filter,
)
from core.analytics.sql_safety import UnsafeAnalyticsQuery, validate_analytics_sql, validate_commerce_sql
from core.analytics.commerce_decision_support import COMMERCE_QUERY_TABLES, unavailable_commerce_dimensions
from core.database.document_repository import DocumentRepository
from core.models.agents import AgentRequest


class AnalyticsSqlSafetyTest(unittest.TestCase):
    def test_commerce_query_accepts_unseen_question_specific_grouped_select(self):
        query = (
            "SELECT i.category, SUM(i.units_sold) AS units_sold "
            "FROM commerce.inventory i WHERE i.year = 2022 "
            "GROUP BY i.category ORDER BY units_sold DESC LIMIT 12"
        )
        normalized = validate_commerce_sql(query, COMMERCE_QUERY_TABLES["inventory_allocation"])
        self.assertIn("FROM commerce.inventory AS i", normalized)
        self.assertIn("LIMIT 12", normalized)

    def test_commerce_query_qualifies_unambiguous_source_columns(self):
        query = (
            "SELECT category, COUNT(*) AS product_count "
            "FROM commerce.inventory i GROUP BY category ORDER BY product_count DESC LIMIT 10"
        )

        normalized = validate_commerce_sql(query, COMMERCE_QUERY_TABLES["inventory_allocation"])

        self.assertIn("SELECT i.category", normalized)
        self.assertIn("GROUP BY i.category", normalized)

    def test_commerce_query_rejects_unqualified_ambiguous_columns(self):
        query = (
            "SELECT product_id, COUNT(*) AS product_count "
            "FROM commerce.inventory i JOIN commerce.products p ON i.product_id = p.product_id "
            "GROUP BY product_id LIMIT 10"
        )

        with self.assertRaisesRegex(UnsafeAnalyticsQuery, "product_id is ambiguous"):
            validate_commerce_sql(query, COMMERCE_QUERY_TABLES["inventory_allocation"])

    def test_commerce_query_allows_only_selected_domain_tables_columns_and_functions(self):
        cases = (
            ("SELECT o.order_id FROM public.orders o", "inventory_allocation"),
            ("SELECT i.reorder_flag FROM commerce.inventory i JOIN commerce.promotions p ON TRUE", "inventory_allocation"),
            ("SELECT pg_sleep(3) AS pause FROM commerce.inventory i", "inventory_allocation"),
            ("SELECT category FROM commerce.inventory i", "inventory_allocation"),
            ("SELECT i.product_name FROM commerce.inventory i LIMIT 10", "inventory_allocation"),
            ("SELECT i.category FROM commerce.inventory i; SELECT 1", "inventory_allocation"),
        )
        for query, domain in cases:
            with self.subTest(query=query), self.assertRaises(UnsafeAnalyticsQuery):
                validate_commerce_sql(query, COMMERCE_QUERY_TABLES[domain])

    def test_question_specific_commerce_query_preserves_novel_wording_and_limits_domain(self):
        repository = Mock()
        repository.latest_commerce_inventory_snapshot.return_value = "2022-12-31"
        repository.execute_commerce_analytics.return_value = [{"category": "Shoes", "units_sold": 42}]
        llm = Mock()
        llm.last_usage = {"input_tokens": 80, "output_tokens": 14, "total_tokens": 94}
        llm.generate.return_value = (
            '{"sql":"SELECT i.category, SUM(i.units_sold) AS units_sold '
            'FROM commerce.inventory i GROUP BY i.category LIMIT 10"}'
        )
        agent = SQLAnalyticsAgent(repository, llm)

        result = agent.commerce_question_observations(
            "Which product groups are moving fastest before a replenishment review?",
            "inventory_allocation",
        )

        self.assertEqual(result["observations"], [{"category": "Shoes", "units_sold": 42}])
        self.assertEqual(result["source_tables"], ["commerce.inventory"])
        self.assertEqual(result["sql_generation_usage"], llm.last_usage)
        self.assertIn("Which product groups are moving fastest", llm.generate.call_args.args[0])
        self.assertIn("Select an aggregate for every measure explicitly requested", llm.generate.call_args.args[0])
        self.assertIn("preserve every requested group", llm.generate.call_args.args[0])
        self.assertIn("COUNT(*) as its own measure", llm.generate.call_args.args[0])
        self.assertIn("no CTEs, nested queries, scalar subqueries", llm.generate.call_args.args[0])
        self.assertIn("database's latest snapshot date", llm.generate.call_args.args[0])
        repository.execute_commerce_analytics.assert_called_once()

    def test_malformed_json_sql_reply_is_repaired_instead_of_leaking_sqlglot_error(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [{"category": "Shoes", "sku_count": 42}]
        llm = Mock()
        llm.generate.side_effect = [
            '{"sql":"SELECT p.category, COUNT(DISTINCT p.product_id) AS sku_count FROM commerce.products p',
            '{"sql":"SELECT p.category, COUNT(DISTINCT p.product_id) AS sku_count '
            'FROM commerce.products p GROUP BY p.category ORDER BY sku_count DESC LIMIT 100"}',
        ]

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Which product categories have the most SKUs?", "inventory_allocation",
        )

        self.assertEqual(result["observations"], [{"category": "Shoes", "sku_count": 42}])
        self.assertEqual(llm.generate.call_count, 2)
        self.assertIn("could not be parsed as one valid PostgreSQL SELECT", llm.generate.call_args.args[0])
        repository.execute_commerce_analytics.assert_called_once_with(result["sql_query"], "inventory_allocation")

    def test_question_specific_commerce_query_normalizes_unambiguous_columns_before_execution(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [{"region": "East", "zip_count": 4}]
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT region, COUNT(*) AS zip_count FROM commerce.geography '
            'GROUP BY region ORDER BY zip_count DESC LIMIT 10"}'
        )

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Which region has the most ZIP codes?", "nationwide_logistics",
        )

        self.assertIn("SELECT geography.region", result["sql_query"])
        self.assertIn("GROUP BY geography.region", result["sql_query"])
        self.assertEqual(result["observations"], [{"region": "East", "zip_count": 4}])
        repository.execute_commerce_analytics.assert_called_once_with(
            result["sql_query"], "nationwide_logistics",
        )

    def test_question_specific_query_rejects_dimension_missing_from_domain_schema_before_llm(self):
        repository = Mock()
        llm = Mock()

        with self.assertRaises(UnsupportedCommerceDimension) as raised:
            SQLAnalyticsAgent(repository, llm).commerce_question_observations(
                "Có đủ cơ sở để phân bổ lại hàng giữa các vùng nhằm giảm stockout?",
                "inventory_allocation",
            )

        self.assertEqual(raised.exception.dimensions, ["region"])
        self.assertNotIn("region", raised.exception.available_columns)
        llm.generate.assert_not_called()
        repository.execute_commerce_analytics.assert_not_called()

    def test_question_specific_query_rejects_other_missing_domain_dimensions_before_llm(self):
        cases = (
            ("How should we rebalance inventory by warehouse?", "inventory_allocation", "warehouse/location"),
            ("Which carrier has the most delayed deliveries?", "nationwide_logistics", "carrier"),
        )
        for question, domain, expected_dimension in cases:
            with self.subTest(domain=domain, question=question):
                repository = Mock()
                llm = Mock()

                with self.assertRaises(UnsupportedCommerceDimension) as raised:
                    SQLAnalyticsAgent(repository, llm).commerce_question_observations(question, domain)

                self.assertIn(expected_dimension, raised.exception.dimensions)
                llm.generate.assert_not_called()
                repository.execute_commerce_analytics.assert_not_called()

    def test_missing_dimension_is_not_treated_as_sql_group_when_listed_as_required_evidence(self):
        available = {column for columns in COMMERCE_QUERY_TABLES["inventory_allocation"].values()
                     for column in columns}
        question = (
            "What should be checked before reallocating stock? State the warehouse-level stock, "
            "forecast demand, replenishment lead time, transfer cost, and service target needed before moving stock."
        )

        self.assertEqual(
            unavailable_commerce_dimensions(question, "inventory_allocation", available),
            [],
        )
        self.assertEqual(
            unavailable_commerce_dimensions(
                "How should we compare inventory by warehouse?", "inventory_allocation", available,
            ),
            ["warehouse/location"],
        )

    def test_repeated_inventory_signal_uses_history_instead_of_latest_snapshot(self):
        question = (
            "Should inventory be reallocated toward products with repeated stockout signals? "
            "Use only the Commerce inventory aggregates and company references. State the warehouse-level "
            "stock, forecast demand, replenishment lead time, transfer cost, and target service level needed."
        )
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [{"product_id": 11, "stockout_snapshots": 4}]
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT i.product_id, COUNT(DISTINCT i.snapshot_date) '
            'FILTER (WHERE i.stockout_flag) AS stockout_snapshots FROM commerce.inventory i '
            'GROUP BY i.product_id HAVING COUNT(DISTINCT i.snapshot_date) '
            'FILTER (WHERE i.stockout_flag) >= 2 ORDER BY stockout_snapshots DESC LIMIT 100"}'
        )

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            question, "inventory_allocation",
        )

        self.assertFalse(_inventory_question_needs_latest_snapshot(question))
        self.assertEqual(result["observations"], [{"product_id": 11, "stockout_snapshots": 4}])
        self.assertIn("repeated, recurring, or persistent require historical", llm.generate.call_args.args[0])
        self.assertIn("inspect historical product-snapshot rows", llm.generate.call_args.args[0])
        self.assertIn("COUNT(DISTINCT", result["sql_query"])
        repository.latest_commerce_inventory_snapshot.assert_not_called()

    def test_repeated_inventory_query_repairs_latest_only_aggregate(self):
        question = "Should we act on products with repeated stockout signals?"
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [
            {"product_id": 11, "stockout_snapshots": 4},
        ]
        llm = Mock()
        llm.generate.side_effect = [
            '{"sql":"SELECT i.category, AVG(i.fill_rate) AS avg_fill_rate '
            'FROM commerce.inventory i GROUP BY i.category LIMIT 100"}',
            '{"sql":"SELECT i.product_id, COUNT(DISTINCT i.snapshot_date) '
            'FILTER (WHERE i.stockout_flag) AS stockout_snapshots '
            'FROM commerce.inventory i GROUP BY i.product_id HAVING COUNT(DISTINCT i.snapshot_date) '
            'FILTER (WHERE i.stockout_flag) >= 2 LIMIT 100"}',
        ]

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            question, "inventory_allocation",
        )

        self.assertEqual(result["observations"], repository.execute_commerce_analytics.return_value)
        self.assertEqual(llm.generate.call_count, 2)
        self.assertIn("COUNT(DISTINCT snapshot_date)", llm.generate.call_args.args[0])
        self.assertIn("Rejected SQL:", llm.generate.call_args.args[0])
        self.assertIn("For repeated inventory flags", llm.generate.call_args.args[0])
        self.assertIn("grouped by i.product_id", llm.generate.call_args.args[0])
        self.assertIn("add HAVING for each requested count >= 2", llm.generate.call_args.args[0])

    def test_repeated_inventory_query_rejects_single_snapshot_filter(self):
        sql = (
            "SELECT i.product_id, COUNT(DISTINCT i.snapshot_date) "
            "FILTER (WHERE i.stockout_flag) AS stockout_snapshots "
            "FROM commerce.inventory i WHERE i.snapshot_date = '2022-12-31' "
            "GROUP BY i.product_id LIMIT 100"
        )

        with self.assertRaisesRegex(UnsafeAnalyticsQuery, "cannot be restricted to one snapshot_date"):
            _validate_repeated_inventory_flags("Repeated stockout signals", sql)

    def test_repeated_inventory_query_requires_two_flagged_snapshots(self):
        sql = (
            "SELECT i.product_id, COUNT(DISTINCT i.snapshot_date) "
            "FILTER (WHERE i.stockout_flag) AS stockout_snapshots "
            "FROM commerce.inventory i GROUP BY i.product_id LIMIT 100"
        )

        with self.assertRaisesRegex(UnsafeAnalyticsQuery, "HAVING COUNT\(DISTINCT snapshot_date\).+>= 2"):
            _validate_repeated_inventory_flags("Repeated stockout signals", sql)
    def test_question_specific_query_keeps_region_available_for_logistics_schema(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [{"region": "East", "shipment_count": 4}]
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT g.region, COUNT(*) AS shipment_count FROM commerce.geography g '
            'GROUP BY g.region LIMIT 10"}'
        )

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Compare shipment counts by region", "nationwide_logistics",
        )

        self.assertEqual(result["observations"], [{"region": "East", "shipment_count": 4}])

    def test_explicit_year_query_repairs_when_sql_omits_requested_period(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [
            {"region": "East", "avg_transit_time": 4.52},
            {"region": "Central", "avg_transit_time": 4.51},
            {"region": "West", "avg_transit_time": 4.51},
        ]
        llm = Mock()
        llm.generate.side_effect = [
            '{"sql":"SELECT g.region, AVG(s.delivery_date - s.ship_date) AS avg_transit_time '
            'FROM commerce.shipments s JOIN commerce.orders o ON s.order_id = o.order_id '
            'JOIN commerce.geography g ON o.zip = g.zip GROUP BY g.region LIMIT 100"}',
            '{"sql":"SELECT g.region, AVG(s.delivery_date - s.ship_date) AS avg_transit_time '
            'FROM commerce.shipments s JOIN commerce.orders o ON s.order_id = o.order_id '
            'JOIN commerce.geography g ON o.zip = g.zip '
            'WHERE EXTRACT(YEAR FROM s.delivery_date) = 2022 GROUP BY g.region LIMIT 100"}',
        ]

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Trong năm 2022, vùng nào có average transit time cao nhất?", "nationwide_logistics",
        )

        self.assertEqual(len(llm.generate.call_args_list), 2)
        self.assertIn("requests year(s) [2022]", llm.generate.call_args_list[1].args[0])
        self.assertEqual(result["observations"][0], {"region": "East", "avg_transit_time": 4.52})
        self.assertEqual(len(result["observations"]), 3)
        self.assertIn("EXTRACT(YEAR FROM s.delivery_date) = 2022", result["sql_query"])

    def test_requested_year_filter_accepts_exact_year_and_explicit_range(self):
        exact_year = (
            "SELECT g.region, AVG(s.delivery_date - s.ship_date) AS avg_days "
            "FROM commerce.shipments s JOIN commerce.geography g ON TRUE "
            "WHERE EXTRACT(YEAR FROM s.delivery_date) = 2022 GROUP BY g.region"
        )
        year_range = (
            "SELECT g.region, EXTRACT(YEAR FROM s.delivery_date) AS year "
            "FROM commerce.shipments s JOIN commerce.geography g ON TRUE "
            "WHERE EXTRACT(YEAR FROM s.delivery_date) BETWEEN 2020 AND 2022 "
            "GROUP BY g.region, EXTRACT(YEAR FROM s.delivery_date)"
        )

        self.assertEqual(_validate_requested_year_filter("In 2022, compare regions", exact_year), exact_year)
        self.assertEqual(_validate_requested_year_filter("Compare 2020–2022", year_range), year_range)

    def test_requested_year_filter_rejects_missing_year_or_broadened_or(self):
        missing_year = "SELECT g.region FROM commerce.geography g GROUP BY g.region"
        broadened_or = (
            "SELECT g.region FROM commerce.shipments s JOIN commerce.geography g ON TRUE "
            "WHERE EXTRACT(YEAR FROM s.delivery_date) = 2022 OR g.region = 'East' GROUP BY g.region"
        )

        with self.assertRaisesRegex(UnsafeAnalyticsQuery, "filter a time column"):
            _validate_requested_year_filter("In 2022, compare regions", missing_year)
        with self.assertRaisesRegex(UnsafeAnalyticsQuery, "mixed with OR"):
            _validate_requested_year_filter("In 2022, compare regions", broadened_or)

    def test_promotion_sql_prompt_defines_campaign_window_tagging_semantics(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [{"campaign": "Spring Sale 2022", "net_item_sales": 42}]
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT p.promo_name AS campaign, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS net_item_sales '
            'FROM commerce.promotions p JOIN commerce.order_items oi ON (oi.promo_id = p.promo_id OR oi.promo_id_2 = p.promo_id) '
            'JOIN commerce.orders o ON o.order_id = oi.order_id WHERE o.order_status = \'delivered\' '
            'AND o.order_date BETWEEN p.start_date AND p.end_date AND EXTRACT(YEAR FROM p.start_date) = 2022 '
            'GROUP BY p.promo_name LIMIT 10"}'
        )

        SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Which campaign had highest net item sales during its campaign window?", "promotion_planning",
        )

        prompt = llm.generate.call_args.args[0]
        self.assertIn("promo_id_2", prompt)
        self.assertIn("order_date falls between", prompt)
        self.assertIn("delivered orders", prompt)
        self.assertIn("requested campaign year to the campaign dates", prompt)
        self.assertIn("filter every order-derived aggregate", prompt)

    def test_promotion_query_repairs_when_a_requested_tag_comparison_returns_one_group(self):
        repository = Mock()
        repository.execute_commerce_analytics.side_effect = [
            [{"year": 2020, "delivered_orders": 10}],
            [
                {"year": 2020, "used_promotion": True, "delivered_orders": 4},
                {"year": 2020, "used_promotion": False, "delivered_orders": 8},
            ],
        ]
        llm = Mock()
        llm.generate.side_effect = [
            '{"sql":"SELECT EXTRACT(YEAR FROM o.order_date) AS year, '
            'COUNT(DISTINCT o.order_id) AS delivered_orders FROM commerce.orders o '
            'JOIN commerce.order_items oi ON oi.order_id = o.order_id '
            'WHERE o.order_status = \'delivered\' AND o.order_date BETWEEN \'2020-01-01\' AND \'2022-12-31\' '
            'AND (oi.promo_id IS NOT NULL OR oi.promo_id_2 IS NOT NULL) '
            'GROUP BY EXTRACT(YEAR FROM o.order_date) LIMIT 100"}',
            '{"sql":"SELECT EXTRACT(YEAR FROM o.order_date) AS year, '
            '(oi.promo_id IS NOT NULL OR oi.promo_id_2 IS NOT NULL) AS used_promotion, '
            'COUNT(DISTINCT o.order_id) AS delivered_orders FROM commerce.orders o '
            'JOIN commerce.order_items oi ON oi.order_id = o.order_id '
            'WHERE o.order_status = \'delivered\' AND o.order_date BETWEEN \'2020-01-01\' AND \'2022-12-31\' '
            'GROUP BY EXTRACT(YEAR FROM o.order_date), '
            '(oi.promo_id IS NOT NULL OR oi.promo_id_2 IS NOT NULL) LIMIT 100"}',
        ]

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Trong 2020–2022, so sánh nhóm đơn delivered có gắn khuyến mãi và không gắn tag theo số đơn?",
            "promotion_planning",
        )

        self.assertTrue(_asks_for_promotion_tag_comparison("Compare tagged and untagged orders."))
        self.assertTrue(_asks_for_promotion_tag_comparison("Compare orders with promotion and without promotion."))
        self.assertFalse(_asks_for_promotion_tag_comparison("Compare promotion sales with and without discounts."))
        self.assertEqual(len(llm.generate.call_args_list), 2)
        self.assertEqual(len(repository.execute_commerce_analytics.call_args_list), 2)
        self.assertIn("both TRUE and FALSE", llm.generate.call_args_list[0].args[0])
        self.assertIn("both values of used_promotion", llm.generate.call_args_list[1].args[0])
        self.assertEqual(result["observations"][0]["used_promotion"], True)
        self.assertEqual(result["observations"][1]["used_promotion"], False)

    def test_promotion_query_repairs_incomplete_campaign_attribution(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [{"campaign": "Spring Sale 2022", "net_sales": 90}]
        llm = Mock()
        llm.generate.side_effect = [
            '{"sql":"SELECT p.promo_name, SUM(oi.quantity * oi.unit_price) AS net_sales '
            'FROM commerce.promotions p LEFT JOIN commerce.order_items oi ON oi.promo_id = p.promo_id '
            'LEFT JOIN commerce.orders o ON o.order_id = oi.order_id '
            'WHERE EXTRACT(YEAR FROM p.start_date) = 2022 GROUP BY p.promo_name LIMIT 10"}',
            '{"sql":"SELECT p.promo_name, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS net_sales '
            'FROM commerce.promotions p JOIN commerce.order_items oi ON (oi.promo_id = p.promo_id OR oi.promo_id_2 = p.promo_id) '
            'JOIN commerce.orders o ON o.order_id = oi.order_id WHERE o.order_status = \'delivered\' '
            'AND o.order_date BETWEEN p.start_date AND p.end_date AND EXTRACT(YEAR FROM p.start_date) = 2022 '
            'GROUP BY p.promo_name LIMIT 10"}',
        ]

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Which campaign had the highest net sales during its 2022 campaign window?", "promotion_planning",
        )

        initial_prompt = llm.generate.call_args_list[0].args[0]
        self.assertIn("orders.order_status = 'delivered'", initial_prompt)
        self.assertIn("EXTRACT(YEAR FROM promotions.start_date)", initial_prompt)
        self.assertIn("Place the year predicate in WHERE", initial_prompt)
        repair_prompt = llm.generate.call_args_list[1].args[0]
        self.assertIn("filter to delivered orders", repair_prompt)
        self.assertIn("Preserve every requested metric and campaign dimension", repair_prompt)
        self.assertIn("year(s) in WHERE, not in a JOIN ON clause", repair_prompt)
        self.assertIn("Campaign outcome SQL must", repair_prompt)
        self.assertIn("promo_id_2", result["sql_query"])
        repository.execute_commerce_analytics.assert_called_once()

    def test_campaign_profit_proxy_prompt_uses_product_catalog_cost_and_exact_campaign_window(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = []
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT p.promo_name AS campaign, '
            'SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS net_sales, '
            'SUM(oi.quantity * oi.unit_price - oi.discount_amount - oi.quantity * pr.cogs) '
            'AS merchandise_gross_profit_proxy FROM commerce.promotions p '
            'JOIN commerce.order_items oi ON (oi.promo_id = p.promo_id OR oi.promo_id_2 = p.promo_id) '
            'JOIN commerce.orders o ON o.order_id = oi.order_id '
            'JOIN commerce.products pr ON pr.product_id = oi.product_id '
            'WHERE o.order_status = \'delivered\' '
            'AND o.order_date BETWEEN p.start_date AND p.end_date '
            'AND EXTRACT(YEAR FROM p.start_date) = 2022 '
            'GROUP BY p.promo_name ORDER BY net_sales DESC LIMIT 100"}'
        )
        question = (
            "Which 2022 campaign led in campaign-window net sales and merchandise gross-profit proxy? "
            "Are they the same campaign?"
        )

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(question, "promotion_planning")

        prompt = llm.generate.call_args.args[0]
        self.assertIn("join commerce.products", prompt)
        self.assertIn("products.cogs", prompt)
        self.assertIn("AS merchandise_gross_profit_proxy", prompt)
        self.assertIn("orders.order_status = 'delivered'", prompt)
        self.assertIn("order_date BETWEEN promotions.start_date AND promotions.end_date", prompt)
        self.assertIn("EXTRACT(YEAR FROM promotions.start_date)", prompt)
        self.assertIn("merchandise_gross_profit_proxy", result["sql_query"])
        repository.execute_commerce_analytics.assert_called_once()

    def test_campaign_guard_rejects_recorded_left_join_query_that_sums_unmatched_orders(self):
        recorded_query = (
            "SELECT p.promo_id, p.promo_name, "
            "SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS net_sales "
            "FROM commerce.promotions AS p "
            "JOIN commerce.order_items AS oi ON (oi.promo_id = p.promo_id OR oi.promo_id_2 = p.promo_id) "
            "LEFT JOIN commerce.orders AS o ON o.order_id = oi.order_id "
            "AND o.order_status = 'delivered' "
            "AND o.order_date BETWEEN p.start_date AND p.end_date "
            "WHERE o.order_date >= '2022-01-01' AND o.order_date <= '2022-12-31' "
            "GROUP BY p.promo_id, p.promo_name ORDER BY net_sales DESC LIMIT 100"
        )

        with self.assertRaisesRegex(UnsafeAnalyticsQuery, "filter every LEFT JOIN aggregate"):
            _validate_campaign_outcome_query(
                "Trong campaign 2022, campaign nào có net sales cao nhất trong thời gian chạy?",
                recorded_query,
            )

    def test_campaign_guard_accepts_date_range_for_requested_year(self):
        query = (
            "SELECT p.promo_name, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS net_sales "
            "FROM commerce.promotions p JOIN commerce.order_items oi "
            "ON (oi.promo_id = p.promo_id OR oi.promo_id_2 = p.promo_id) "
            "JOIN commerce.orders o ON o.order_id = oi.order_id WHERE o.order_status = 'delivered' "
            "AND o.order_date BETWEEN p.start_date AND p.end_date "
            "AND p.start_date >= '2022-01-01' AND p.start_date < '2023-01-01' "
            "GROUP BY p.promo_name LIMIT 100"
        )

        self.assertEqual(
            _validate_campaign_outcome_query(
                "Which 2022 campaign had the highest net sales during its campaign window?", query,
            ),
            query,
        )

    def test_campaign_guard_accepts_multi_year_date_range(self):
        query = (
            "SELECT p.promo_name, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS net_sales "
            "FROM commerce.promotions p JOIN commerce.order_items oi "
            "ON (oi.promo_id = p.promo_id OR oi.promo_id_2 = p.promo_id) "
            "JOIN commerce.orders o ON o.order_id = oi.order_id WHERE o.order_status = 'delivered' "
            "AND o.order_date BETWEEN p.start_date AND p.end_date "
            "AND EXTRACT(YEAR FROM p.start_date) BETWEEN 2020 AND 2022 "
            "GROUP BY p.promo_name LIMIT 100"
        )

        self.assertEqual(
            _validate_campaign_outcome_query(
                "Compare campaign sales from 2020 to 2022", query,
            ),
            query,
        )

    def test_campaign_scope_requires_an_explicit_campaign_breakdown(self):
        self.assertFalse(_asks_for_campaign_scoped_outcomes(
            "Should we expand a campaign based on sales? Compare the sales outcome and profit proxy."
        ))
        self.assertTrue(_asks_for_campaign_scoped_outcomes(
            "Compare sales and profit by campaign."
        ))

    def test_promotion_decision_question_does_not_require_campaign_window_join(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [
            {"used_promotion": True, "delivered_order_items": 40, "net_sales": 900},
            {"used_promotion": False, "delivered_order_items": 60, "net_sales": 1100},
        ]
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT (oi.promo_id IS NOT NULL OR oi.promo_id_2 IS NOT NULL) AS used_promotion, '
            'COUNT(*) AS delivered_order_items, '
            'SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS net_sales '
            'FROM commerce.order_items oi JOIN commerce.orders o ON o.order_id = oi.order_id '
            'WHERE o.order_status = \'delivered\' '
            'GROUP BY (oi.promo_id IS NOT NULL OR oi.promo_id_2 IS NOT NULL) LIMIT 100"}'
        )

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Should the business repeat or expand a promotion based on available order data? "
            "Explain why causal lift and ROI cannot be established without a holdout and campaign spend.",
            "promotion_planning",
        )

        self.assertIn("FROM commerce.order_items", result["sql_query"])
        self.assertEqual(len(llm.generate.call_args_list), 1)
        repository.execute_commerce_analytics.assert_called_once()

    def test_inventory_sql_prompt_identifies_boolean_flag_columns(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [{"category": "Shoes", "stockout_products": 2}]
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT i.category, COUNT(*) FILTER (WHERE i.stockout_flag) AS stockout_products '
            'FROM commerce.inventory i GROUP BY i.category LIMIT 10"}'
        )

        SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Which category has the most stockout products?", "inventory_allocation",
        )

        prompt = llm.generate.call_args.args[0]
        self.assertIn("stockout_flag, overstock_flag and reorder_flag are BOOLEAN", prompt)
        self.assertIn("do not compare these columns with integer 1/0", prompt)

    def test_question_specific_commerce_query_repairs_one_rejected_select(self):
        repository = Mock()
        repository.latest_commerce_inventory_snapshot.return_value = "2022-12-31"
        repository.execute_commerce_analytics.return_value = [{"category": "Streetwear", "stockout_count": 134}]
        llm = Mock()
        llm.generate.side_effect = [
            '{"sql":"SELECT i.category, COUNT(*) AS stockout_count FROM commerce.inventory i '
            'WHERE i.snapshot_date = (SELECT MAX(snapshot_date) FROM commerce.inventory) '
            'GROUP BY i.category LIMIT 100"}',
            '{"sql":"SELECT i.snapshot_date, i.category, COUNT(*) AS stockout_count '
            'FROM commerce.inventory i GROUP BY i.snapshot_date, i.category '
            'ORDER BY i.snapshot_date DESC LIMIT 100"}',
        ]
        agent = SQLAnalyticsAgent(repository, llm)

        result = agent.commerce_question_observations(
            "Which category had the most stockouts in the latest snapshot?",
            "inventory_allocation",
        )

        self.assertEqual(result["observations"], [{"category": "Streetwear", "stockout_count": 134}])
        self.assertIn("Rejected SQL:", llm.generate.call_args.args[0])
        repository.execute_commerce_analytics.assert_called_once()

    def test_sql_repair_prompt_contains_rejected_query_and_ambiguous_column(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [{"category": "Shoes", "product_count": 4}]
        llm = Mock()
        llm.generate.side_effect = [
            '{"sql":"SELECT category, COUNT(DISTINCT product_id) AS product_count '
            'FROM commerce.inventory i JOIN commerce.products p ON i.product_id = p.product_id '
            'GROUP BY category LIMIT 10"}',
            '{"sql":"SELECT i.category, COUNT(DISTINCT i.product_id) AS product_count '
            'FROM commerce.inventory i JOIN commerce.products p ON i.product_id = p.product_id '
            'GROUP BY i.category LIMIT 10"}',
        ]

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Which inventory categories have the most products?", "inventory_allocation",
        )

        repair_prompt = llm.generate.call_args_list[1].args[0]
        self.assertIn("Unqualified column category is ambiguous", repair_prompt)
        self.assertIn("Rejected SQL: SELECT category, COUNT(DISTINCT product_id)", repair_prompt)
        self.assertIn("i.category", result["sql_query"])
        repository.execute_commerce_analytics.assert_called_once()

    def test_database_error_category_is_included_in_commerce_query_repair_prompt(self):
        repository = Mock()
        repository.execute_commerce_analytics.side_effect = [
            UnsafeAnalyticsQuery("The Commerce SELECT could not be executed (UndefinedFunction, SQLSTATE 42883)"),
            [{"region": "East", "shipment_count": 7}],
        ]
        llm = Mock()
        sql = (
            '{"sql":"SELECT g.region, COUNT(*) AS shipment_count '
            'FROM commerce.shipments s JOIN commerce.orders o ON s.order_id = o.order_id '
            'JOIN commerce.geography g ON o.zip = g.zip GROUP BY g.region LIMIT 100"}'
        )
        llm.generate.side_effect = [sql, sql]

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Which region has the most delivered shipments?", "nationwide_logistics",
        )

        self.assertEqual(result["observations"], [{"region": "East", "shipment_count": 7}])
        self.assertIn("UndefinedFunction, SQLSTATE 42883", llm.generate.call_args_list[1].args[0])

    def test_logistics_sql_prompt_uses_date_subtraction_for_transit_days(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [{"region": "East", "avg_transit_days": 4.5}]
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT g.region, AVG(s.delivery_date - s.ship_date) AS avg_transit_days '
            'FROM commerce.shipments s JOIN commerce.orders o ON s.order_id = o.order_id '
            'JOIN commerce.geography g ON o.zip = g.zip GROUP BY g.region LIMIT 100"}'
        )

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Which region has the longest average transit time?", "nationwide_logistics",
        )

        prompt = llm.generate.call_args.args[0]
        self.assertIn("ship_date and delivery_date are DATE columns", prompt)
        self.assertIn("group by the completed delivery year", prompt)
        self.assertIn("AVG(s.delivery_date - s.ship_date)", prompt)
        self.assertNotIn("EXTRACT(EPOCH", result["sql_query"])
        self.assertEqual(result["observations"], [{"region": "East", "avg_transit_days": 4.5}])

    def test_commerce_sql_generation_uses_configured_huggingface_fallback(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [{"region": "East", "shipment_count": 7}]
        llm = Mock()
        llm.generate.side_effect = RateLimitError(
            "rate limited", response=httpx.Response(429, request=httpx.Request("POST", "https://llm.test")),
            body=None,
        )
        fallback_sql = (
            '{"sql":"SELECT g.region, COUNT(*) AS shipment_count '
            'FROM commerce.shipments s JOIN commerce.orders o ON s.order_id = o.order_id '
            'JOIN commerce.geography g ON o.zip = g.zip GROUP BY g.region LIMIT 100"}'
        )

        with patch.dict(os.environ, {
            "HUGGINGFACE_LLM_FALLBACK": "true", "HUGGINGFACE_API_KEY": "test-token",
        }), patch("core.llm.provider_fallback.HuggingFaceProvider") as fallback_factory:
            fallback_factory.return_value.generate.return_value = fallback_sql
            result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
                "Which region has the most delivered shipments?", "nationwide_logistics",
            )

        self.assertEqual(result["sql_generation_provider"], "huggingface_inference")
        self.assertEqual(result["observations"], [{"region": "East", "shipment_count": 7}])
        repository.execute_commerce_analytics.assert_called_once()
        fallback_factory.return_value.close.assert_called_once()

    def test_latest_inventory_snapshot_is_server_scoped_to_one_date(self):
        repository = Mock()
        repository.latest_commerce_inventory_snapshot.return_value = "2022-12-31"
        repository.execute_commerce_analytics.return_value = [
            {"snapshot_date": "2022-12-31", "category": "Streetwear", "stockouts": 134},
            {"snapshot_date": "2022-12-31", "category": "Outdoor", "stockouts": 95},
        ]
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT i.snapshot_date, i.category, '
            'COUNT(CASE WHEN i.stockout_flag = TRUE THEN 1 END) AS stockouts '
            'FROM commerce.inventory i GROUP BY i.snapshot_date, i.category '
            'ORDER BY i.snapshot_date DESC LIMIT 100"}'
        )
        agent = SQLAnalyticsAgent(repository, llm)

        result = agent.commerce_question_observations(
            "Trong snapshot tồn kho mới nhất, nhóm nào có nhiều stockout nhất?",
            "inventory_allocation",
        )

        self.assertIn("WHERE i.snapshot_date = '2022-12-31'", result["sql_query"])
        self.assertEqual({row["snapshot_date"] for row in result["observations"]}, {"2022-12-31"})
        repository.latest_commerce_inventory_snapshot.assert_called_once_with()

    def test_inventory_reallocation_by_region_is_rejected_when_schema_has_no_region(self):
        repository = Mock()
        llm = Mock()

        with self.assertRaises(UnsupportedCommerceDimension):
            SQLAnalyticsAgent(repository, llm).commerce_question_observations(
                "Có đủ cơ sở để phân bổ lại hàng giữa các vùng nhằm giảm stockout không?",
                "inventory_allocation",
            )

        repository.latest_commerce_inventory_snapshot.assert_not_called()
        repository.execute_commerce_analytics.assert_not_called()
        llm.generate.assert_not_called()

    def test_product_catalog_query_does_not_apply_inventory_snapshot_filter(self):
        repository = Mock()
        repository.execute_commerce_analytics.return_value = [{"category": "Shoes", "avg_price": 42}]
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT p.category, AVG(p.price) AS avg_price '
            'FROM commerce.products p GROUP BY p.category LIMIT 100"}'
        )

        result = SQLAnalyticsAgent(repository, llm).commerce_question_observations(
            "Which product categories have the highest catalog prices?",
            "inventory_allocation",
        )

        self.assertNotIn("snapshot_date", result["sql_query"])
        repository.latest_commerce_inventory_snapshot.assert_not_called()

    def test_commerce_ranking_query_retries_when_having_hides_peer_groups(self):
        repository = Mock()
        repository.latest_commerce_inventory_snapshot.return_value = "2022-12-31"
        repository.execute_commerce_analytics.return_value = [
            {"snapshot_date": "2022-12-31", "category": "Streetwear", "stockouts": 134},
            {"snapshot_date": "2022-12-31", "category": "Outdoor", "stockouts": 95},
        ]
        llm = Mock()
        llm.generate.side_effect = [
            '{"sql":"SELECT i.snapshot_date, i.category, '
            'SUM(i.stockout_flag::int) AS stockouts FROM commerce.inventory i '
            'GROUP BY i.snapshot_date, i.category HAVING SUM(i.overstock_flag::int) = 0 '
            'ORDER BY i.snapshot_date DESC LIMIT 100"}',
            '{"sql":"SELECT i.snapshot_date, i.category, '
            'SUM(i.stockout_flag::int) AS stockouts FROM commerce.inventory i '
            'GROUP BY i.snapshot_date, i.category ORDER BY i.snapshot_date DESC, stockouts DESC LIMIT 100"}',
        ]
        agent = SQLAnalyticsAgent(repository, llm)

        result = agent.commerce_question_observations(
            "Trong snapshot mới nhất, nhóm nào cần ưu tiên theo cờ stockout?",
            "inventory_allocation",
        )

        self.assertEqual(len(result["observations"]), 2)
        self.assertNotIn("HAVING", result["sql_query"].upper())
        self.assertIn("include all peer groups", llm.generate.call_args.args[0])
        self.assertEqual(repository.execute_commerce_analytics.call_count, 1)

    def test_accepts_aggregate_select_and_caps_limit(self):
        sql = """SELECT metric_name, fiscal_year, SUM(metric_value) AS total,
                         ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids
                  FROM authorized_financial_metrics
                  GROUP BY metric_name, fiscal_year LIMIT 900"""
        normalized = validate_analytics_sql(sql)
        self.assertIn("LIMIT 100", normalized)
        self.assertIn("authorized_financial_metrics", normalized)

    def test_accepts_case_expressions_inside_allowlisted_aggregates(self):
        sql = """SELECT company, metric_name, fiscal_year,
                         SUM(CASE WHEN metric_name = 'Revenue' THEN metric_value END) AS revenue,
                         SUM(CASE WHEN metric_name = 'Profit' THEN metric_value END) AS profit,
                         ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids
                  FROM authorized_financial_metrics
                  GROUP BY company, metric_name, fiscal_year"""
        normalized = validate_analytics_sql(sql)
        self.assertIn("SUM(CASE", normalized)
        self.assertIn("LIMIT 100", normalized)

    def test_adds_default_limit(self):
        sql = "SELECT document_id, ARRAY_AGG(document_id) AS evidence_document_ids FROM authorized_documents"
        self.assertTrue(validate_analytics_sql(sql).endswith("LIMIT 100"))

    def test_rejects_non_select_and_multiple_statements(self):
        for sql in (
            "DELETE FROM public.documents",
            "SELECT document_id, ARRAY_AGG(document_id) AS evidence_document_ids FROM authorized_documents; SELECT 1",
        ):
            with self.subTest(sql=sql), self.assertRaises(UnsafeAnalyticsQuery):
                validate_analytics_sql(sql)

    def test_rejects_unapproved_sources_columns_joins_and_functions(self):
        statements = (
            "SELECT id, ARRAY_AGG(document_id) AS evidence_document_ids FROM public.documents",
            "SELECT password, ARRAY_AGG(document_id) AS evidence_document_ids FROM authorized_documents",
            "SELECT d.document_id, ARRAY_AGG(d.document_id) AS evidence_document_ids FROM authorized_documents d JOIN authorized_financial_metrics m ON TRUE",
            "SELECT pg_sleep(5), ARRAY_AGG(document_id) AS evidence_document_ids FROM authorized_documents",
            "SELECT document_id, ARRAY_AGG(document_id) AS evidence_document_ids FROM (SELECT document_id FROM authorized_documents) q",
        )
        for sql in statements:
            with self.subTest(sql=sql), self.assertRaises(UnsafeAnalyticsQuery):
                validate_analytics_sql(sql)

    def test_requires_aggregated_source_ids_for_citations(self):
        sql = "SELECT document_id AS evidence_document_ids FROM authorized_documents"
        with self.assertRaises(UnsafeAnalyticsQuery):
            validate_analytics_sql(sql)

    def test_financial_analytics_must_keep_metric_and_year_dimensions(self):
        sql = (
            "SELECT SUM(metric_value) AS total, "
            "ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids "
            "FROM authorized_financial_metrics"
        )
        with self.assertRaisesRegex(UnsafeAnalyticsQuery, "metric_name and fiscal_year"):
            validate_analytics_sql(sql)

    def test_rejects_duplicate_result_names_that_could_hide_citation_array(self):
        sql = (
            "SELECT ARRAY_AGG(document_id) AS evidence_document_ids, "
            "document_id AS evidence_document_ids FROM authorized_documents"
        )
        with self.assertRaises(UnsafeAnalyticsQuery):
            validate_analytics_sql(sql)

    def test_agent_generates_sql_executes_it_and_returns_provenance(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [{"metric_name": "net_revenue", "fiscal_year": 2024,
                         "total": 61824, "evidence_metric_ids": [1]}],
            "evidence": [{"company": "Example Retailer", "fiscal_year": 2024,
                          "metric_name": "net_revenue", "metric_label": "Net revenue",
                          "metric_value": 61824, "unit": "billion VND", "document_id": "AR24",
                          "metric_id": 1, "page_number": 12, "source_url": "https://example.test/ar24",
                          "source_quote": "Total revenue 18,624 billion VND", "source_chunk_id": 90,
                          "source_chunk_index": 4, "source_content_hash": "chunk-sha256"}],
            "documents": [],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT metric_name, fiscal_year, SUM(metric_value) AS total, '
            'ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids '
            'FROM authorized_financial_metrics WHERE fiscal_year = 2024 '
            'AND metric_name = \'net_revenue\' GROUP BY metric_name, fiscal_year"}'
        )
        agent = SQLAnalyticsAgent(repository, llm)
        result = agent.run(AgentRequest(
            question="Total verified revenue in 2024?", user_id="analyst",
            metadata={"role": "finance_analyst", "company": "Example Retailer"},
        ))
        self.assertIn("total: 61824", result.answer)
        self.assertIn("[M1]", result.answer)
        self.assertEqual(result.evidence[0].metadata["document_id"], "AR24")
        self.assertEqual(result.evidence[0].metadata["source_chunk_id"], 90)
        self.assertEqual(result.evidence[0].metadata["chunk_index"], 4)
        self.assertEqual(result.evidence[0].metadata["source_content_hash"], "chunk-sha256")
        repository.execute_authorized_analytics.assert_called_once()
        self.assertEqual(repository.execute_authorized_analytics.call_args.args[1:],
                         ("finance_analyst", "analyst", "Example Retailer"))
        self.assertIn("LIMIT 100", repository.execute_authorized_analytics.call_args.args[0])
        prompt = llm.generate.call_args.args[0]
        self.assertIn("total_consolidated_revenue", prompt)
        self.assertIn("profit_after_tax", prompt)
        self.assertIn("project metric_name and fiscal_year directly", prompt)
        self.assertIn("do not add a company equality filter", prompt.lower())

    def test_empty_aggregate_result_with_null_evidence_is_reported_as_no_verified_data(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [{"total": None, "evidence_metric_ids": None}],
            "evidence": [],
            "documents": [],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT metric_name, fiscal_year, SUM(metric_value) AS total, '
            'ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids '
            'FROM authorized_financial_metrics GROUP BY metric_name, fiscal_year"}'
        )
        result = SQLAnalyticsAgent(repository, llm).run(AgentRequest(
            question="Total verified revenue?", user_id="viewer",
            metadata={"role": "employee", "company": "Example Retailer"},
        ))

        self.assertEqual(result.answer, "No verified, role-visible data matched this analytics request.")
        self.assertEqual(result.data["results"], [])
        self.assertEqual(result.evidence, [])

    def test_repository_executes_inside_read_only_timeout_and_role_filtered_ctes(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.description = [SimpleNamespace(name="matched_rows"), SimpleNamespace(name="evidence_document_ids")]
        cursor.fetchall.return_value = [{"matched_rows": 0, "evidence_document_ids": []}]
        query = (
            "SELECT COUNT(document_id) AS matched_rows, "
            "ARRAY_AGG(DISTINCT document_id) AS evidence_document_ids FROM authorized_documents"
        )
        result = repository.execute_authorized_analytics(query, "employee", "viewer", "Example Retailer")
        executed = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn("SET TRANSACTION READ ONLY", executed)
        self.assertIn("SET LOCAL statement_timeout = '3s'", executed)
        repository.conn.rollback.assert_called_once()
        cte_call = next(call for call in cursor.execute.call_args_list if "WITH authorized_financial_metrics" in call.args[0])
        self.assertIn("allowed_roles && %s::text[]", cte_call.args[0])
        self.assertIn("case when d.fiscal_year ~ '^[0-9]{4}$' then d.fiscal_year::integer end as fiscal_year", " ".join(cte_call.args[0].lower().split()))
        self.assertIn("company = %s", cte_call.args[0])
        self.assertEqual(cte_call.args[1], (
            ["employee"], "employee", "Example Retailer", "Example Retailer",
            ["employee"], "employee", "employee", "viewer", "Example Retailer", "Example Retailer",
        ))
        self.assertEqual(result["results"][0]["matched_rows"], 0)

    def test_repository_revalidates_sql_before_opening_a_transaction(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()

        with self.assertRaises(UnsafeAnalyticsQuery):
            repository.execute_authorized_analytics("DELETE FROM public.documents", "employee", "viewer")

        repository.conn.rollback.assert_not_called()
        repository.conn.cursor.assert_not_called()

    def test_metric_result_cites_only_matching_metric_and_year_within_same_document(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [{"metric_name": "net_revenue", "fiscal_year": 2024,
                         "total": 61824, "evidence_metric_ids": [1]}],
            "evidence": [
                {"company": "Example Retailer", "fiscal_year": 2024, "metric_name": "net_revenue",
                 "metric_label": "Consolidated revenue", "metric_value": 61824, "unit": "billion VND",
                 "document_id": "AR24", "metric_id": 1, "page_number": 12, "source_url": "https://example.test/ar24",
                 "source_quote": "Consolidated revenue 18,624 billion VND"},
                {"company": "Example Retailer", "fiscal_year": 2024, "metric_name": "profit_after_tax",
                 "metric_label": "Profit after tax", "metric_value": 9453, "unit": "billion VND",
                 "document_id": "AR24", "page_number": 12, "source_url": "https://example.test/ar24",
                 "source_quote": "Profit after tax 9,453 billion VND"},
                {"company": "Example Retailer", "fiscal_year": 2023, "metric_name": "net_revenue",
                 "metric_label": "Consolidated revenue", "metric_value": 60479, "unit": "billion VND",
                 "document_id": "AR24", "page_number": 12, "source_url": "https://example.test/ar24",
                 "source_quote": "Prior-year consolidated revenue 60,479 billion VND"},
            ],
            "documents": [],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT metric_name, fiscal_year, SUM(metric_value) AS total, '
            'ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids '
            'FROM authorized_financial_metrics WHERE metric_name = \'net_revenue\' '
            'AND fiscal_year = 2024 GROUP BY metric_name, fiscal_year"}'
        )

        result = SQLAnalyticsAgent(repository, llm).run(AgentRequest(
            question="Total net revenue in 2024?", metadata={"role": "finance_analyst"}
        ))

        self.assertIn("[M1]", result.answer)
        self.assertNotIn("[M2]", result.answer)
        self.assertNotIn("[M3]", result.answer)
        self.assertEqual([item.citation_id for item in result.evidence], ["M1"])
        self.assertEqual([row["metric_name"] for row in result.data["financial"]], ["net_revenue"])

    def test_document_analytics_cites_visible_documents_not_unrelated_metric_rows(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [{"domain": "finance", "document_count": 1,
                         "evidence_document_ids": ["AR24"]}],
            "evidence": [{"company": "Example Retailer", "fiscal_year": 2024, "metric_name": "net_revenue",
                          "metric_label": "Revenue", "metric_value": 61824, "unit": "billion VND",
                          "document_id": "AR24", "page_number": 12, "source_url": "https://example.test/ar24",
                          "source_quote": "Revenue 18,624 billion VND"}],
            "documents": [{"document_id": "AR24", "company": "Example Retailer", "domain": "finance",
                           "title": "Annual report 2024", "source_url": "https://example.test/ar24"}],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT domain, COUNT(document_id) AS document_count, '
            'ARRAY_AGG(DISTINCT document_id) AS evidence_document_ids '
            'FROM authorized_documents GROUP BY domain"}'
        )

        result = SQLAnalyticsAgent(repository, llm).run(AgentRequest(
            question="How many finance documents?", metadata={"role": "finance_analyst"}
        ))

        self.assertIn("[D1]", result.answer)
        self.assertEqual([item.source_type for item in result.evidence], ["document"])
        self.assertEqual(result.data["financial"], [])


if __name__ == "__main__":
    unittest.main()
