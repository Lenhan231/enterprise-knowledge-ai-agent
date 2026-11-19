import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from core.analytics.query_contract import verify_query_contract
from core.analytics.sql_validation import SQLSecurityError, validate_sql_security
from core.analytics.text_to_sql import APPROVED_COLUMNS
from core.agents.sql.query_intent import QueryIntent


REGIONAL_SQL = (
    'SELECT g.region, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue '
    'FROM commerce.orders AS o '
    'JOIN commerce.order_items AS oi ON oi.order_id = o.order_id '
    'JOIN commerce.geography AS g ON g.zip = o.zip '
    'WHERE o.order_status = $1 AND o.order_date >= $2 AND o.order_date < $3 '
    'GROUP BY g.region LIMIT 200'
)


def regional_intent(**changes):
    value = {
        'original_question': 'Revenue by region for May 2026',
        'operation': 'aggregate', 'metrics': ['regional_revenue'],
        'dimensions': ['region'],
        'filters': [{'field': 'commerce.orders.order_status', 'operator': 'eq',
                     'value': 'delivered', 'provenance': 'ontology_required'}],
        'time_scope': {'mode': 'range', 'ranges': [
            {'start': '2026-05-01', 'end_exclusive': '2026-06-01'}]},
        'requested_sources': [
            {'name': 'commerce.orders', 'provenance': 'ontology_required'},
            {'name': 'commerce.order_items', 'provenance': 'ontology_required'},
            {'name': 'commerce.geography', 'provenance': 'ontology_required'},
        ],
        'explicit_source_restriction': False,
        'geographic_basis': 'order_destination', 'geographic_coverage': 'all',
        'ranking': None, 'unresolved_slots': [],
    }
    value.update(changes)
    return QueryIntent.model_validate_json(json.dumps(value))


class QueryContractTest(unittest.TestCase):
    def verify(self, intent=None, sql=REGIONAL_SQL, parameters=('delivered', '2026-05-01', '2026-06-01')):
        return verify_query_contract(intent or regional_intent(), sql, parameters, APPROVED_COLUMNS)

    def test_all_supported_regional_obligations_pass(self):
        self.assertEqual(self.verify().status, 'verified')

    def test_missing_region_filter_is_incomplete(self):
        sql = REGIONAL_SQL.replace('GROUP BY g.region', "AND g.region = 'North' GROUP BY g.region")
        intent = regional_intent(geographic_coverage='filtered', filters=[
            {'field': 'commerce.orders.order_status', 'operator': 'eq', 'value': 'delivered',
             'provenance': 'ontology_required'},
            {'field': 'commerce.geography.region', 'operator': 'eq', 'value': 'South'},
        ])
        self.assertIn('Requested filter is missing or changed', '; '.join(self.verify(intent, sql).issues))

    def test_missing_date_range_is_incomplete(self):
        sql = REGIONAL_SQL.replace(' AND o.order_date >= $2 AND o.order_date < $3', '')
        result = self.verify(sql=sql, parameters=('delivered',))
        self.assertEqual(result.status, 'incomplete')
        self.assertTrue(any('date range' in issue for issue in result.issues))

    def test_missing_grouping_is_incomplete(self):
        result = self.verify(sql=REGIONAL_SQL.replace(' GROUP BY g.region', ''))
        self.assertTrue(any('selected and grouped' in issue for issue in result.issues))

    def test_requested_monthly_grain_requires_month_truncation_and_grouping(self):
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': 'Show monthly revenue in 2022', 'operation': 'trend',
            'metrics': ['revenue'], 'dimensions': [], 'filters': [],
            'time_scope': {'mode': 'range', 'ranges': [
                {'start': '2022-01-01', 'end_exclusive': '2023-01-01'}]},
            'time_grain': 'month', 'requested_sources': [],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None, 'ranking': None, 'unresolved_slots': [],
        }))
        sql = ("SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue "
               'FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 '
               'GROUP BY 1 LIMIT 200')
        parameters = ('2022-01-01', '2023-01-01')
        self.assertEqual(self.verify(intent, sql, parameters).status, 'verified')
        by_alias = sql.replace('GROUP BY 1', 'GROUP BY month')
        self.assertEqual(self.verify(intent, by_alias, parameters).status, 'verified')
        daily = sql.replace("DATE_TRUNC('month'", "DATE_TRUNC('day'")
        result = self.verify(intent, daily, parameters)
        self.assertTrue(any('month time grain' in issue for issue in result.issues))

    def test_date_filter_in_unused_cte_does_not_satisfy_range(self):
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': 'Show monthly revenue in 2022', 'operation': 'trend',
            'metrics': ['revenue'], 'dimensions': [], 'filters': [],
            'time_scope': {'mode': 'range', 'ranges': [
                {'start': '2022-01-01', 'end_exclusive': '2023-01-01'}]},
            'time_grain': None, 'requested_sources': [],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None, 'ranking': None, 'unresolved_slots': [],
        }))
        sql = ('WITH unused AS (SELECT s.date FROM commerce.sales AS s '
               'WHERE s.date >= $1 AND s.date < $2) '
               'SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s LIMIT 1')
        result = self.verify(intent, sql, ('2022-01-01', '2023-01-01'))
        self.assertTrue(any('date range' in issue for issue in result.issues))

    def test_shared_period_must_filter_each_requested_metric_source(self):
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': 'Revenue and rating for 2025', 'operation': 'aggregate',
            'metrics': ['revenue', 'rating'], 'dimensions': [], 'filters': [],
            'time_scope': {'mode': 'range', 'ranges': [
                {'start': '2025-01-01', 'end_exclusive': '2026-01-01'}]},
            'time_grain': None, 'requested_sources': [],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None, 'ranking': None, 'unresolved_slots': [],
        }), strict=True)
        rating_only = (
            'WITH rev AS (SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s), '
            'ratings AS (SELECT AVG(r.rating) AS rating FROM commerce.reviews AS r '
            'WHERE r.review_date >= $1 AND r.review_date < $2) '
            'SELECT rev.revenue, ratings.rating FROM rev CROSS JOIN ratings LIMIT 1'
        )
        result = verify_query_contract(
            intent, rating_only, ('2025-01-01', '2026-01-01'), APPROVED_COLUMNS)
        self.assertEqual(result.status, 'incomplete')
        self.assertTrue(any('metric revenue' in issue and 'date range' in issue
                            for issue in result.issues))

        both_filtered = rating_only.replace(
            'FROM commerce.sales AS s)',
            'FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2)')
        self.assertEqual(verify_query_contract(
            intent, both_filtered, ('2025-01-01', '2026-01-01'), APPROVED_COLUMNS).status, 'verified')

    def test_region_filter_in_unrelated_subquery_does_not_satisfy_request(self):
        sql = REGIONAL_SQL.replace(
            'GROUP BY g.region',
            "AND EXISTS (SELECT 1 FROM commerce.geography AS g2 WHERE g2.region = $4) GROUP BY g.region")
        intent = regional_intent(geographic_coverage='filtered', filters=[
            {'field': 'commerce.orders.order_status', 'operator': 'eq', 'value': 'delivered',
             'provenance': 'ontology_required'},
            {'field': 'commerce.geography.region', 'operator': 'eq', 'value': 'North'},
        ])
        result = self.verify(intent, sql, ('delivered', '2026-05-01', '2026-06-01', 'North'))
        self.assertTrue(any('commerce.geography.region' in issue for issue in result.issues))

    def test_required_filter_in_or_branch_is_not_treated_as_guaranteed(self):
        sql = REGIONAL_SQL.replace(
            'o.order_status = $1 AND ',
            '(o.order_status = $1 OR o.order_status IS NULL) AND ')
        result = self.verify(sql=sql)
        self.assertTrue(any('Requested filter is missing' in issue for issue in result.issues))

    def test_monthly_cte_with_indirect_output_lineage_is_inconclusive(self):
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': 'Show monthly revenue in 2022', 'operation': 'trend',
            'metrics': ['revenue'], 'dimensions': [], 'filters': [],
            'time_scope': {'mode': 'range', 'ranges': [
                {'start': '2022-01-01', 'end_exclusive': '2023-01-01'}]},
            'time_grain': 'month', 'requested_sources': [],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None, 'ranking': None, 'unresolved_slots': [],
        }))
        sql = ("WITH monthly AS (SELECT DATE_TRUNC('month', s.date) AS month, "
               'SUM(s.revenue) AS revenue FROM commerce.sales AS s '
               'WHERE s.date >= $1 AND s.date < $2 GROUP BY 1), '
               'preserved AS (SELECT month, revenue FROM monthly) '
               'SELECT p.month, p.revenue FROM preserved AS p ORDER BY p.month LIMIT 200')
        result = self.verify(intent, sql, ('2022-01-01', '2023-01-01'))
        self.assertEqual(result.status, 'inconclusive')

    def test_bounded_customer_quantity_ranking_checks_aggregate_and_order(self):
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': 'khách hàng nào mua hàng nhiều nhất theo số lượng',
            'operation': 'rank', 'metrics': [],
            'unverified_metric_request': 'sum of purchased item quantity by customer',
            'dimensions': ['commerce.orders.customer_id'], 'filters': [],
            'time_scope': {'mode': 'all', 'ranges': []}, 'time_grain': None,
            'requested_sources': [
                {'name': 'commerce.orders', 'provenance': 'ontology_required'},
                {'name': 'commerce.order_items', 'provenance': 'ontology_required'},
            ],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None, 'ranking': None, 'unresolved_slots': [],
        }))
        sql = ('SELECT o.customer_id, SUM(oi.quantity) AS total_quantity '
               'FROM commerce.orders AS o JOIN commerce.order_items AS oi ON oi.order_id = o.order_id '
               'GROUP BY o.customer_id ORDER BY total_quantity DESC LIMIT 1')
        self.assertEqual(self.verify(intent, sql, ()).status, 'verified')
        wrong_rank = sql.replace('ORDER BY total_quantity DESC', 'ORDER BY o.customer_id DESC')
        result = self.verify(intent, wrong_rank, ())
        self.assertEqual(result.status, 'incomplete')
        self.assertTrue(any('Customer quantity ranking' in issue for issue in result.issues))

    def test_monthly_cte_is_verified_when_final_output_preserves_month(self):
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': 'Show monthly revenue in 2022', 'operation': 'trend',
            'metrics': ['revenue'], 'dimensions': [], 'filters': [],
            'time_scope': {'mode': 'range', 'ranges': [
                {'start': '2022-01-01', 'end_exclusive': '2023-01-01'}]},
            'time_grain': 'month', 'requested_sources': [],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None, 'ranking': None, 'unresolved_slots': [],
        }))
        sql = ("WITH monthly AS (SELECT DATE_TRUNC('month', s.date) AS month, "
               'SUM(s.revenue) AS revenue FROM commerce.sales AS s '
               'WHERE s.date >= $1 AND s.date < $2 GROUP BY 1) '
               'SELECT m.month, m.revenue FROM monthly AS m ORDER BY m.month LIMIT 200')
        self.assertEqual(self.verify(intent, sql, ('2022-01-01', '2023-01-01')).status, 'verified')

    def test_monthly_cte_does_not_satisfy_collapsed_final_output(self):
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': 'Show monthly revenue in 2022', 'operation': 'trend',
            'metrics': ['revenue'], 'dimensions': [], 'filters': [],
            'time_scope': {'mode': 'range', 'ranges': [
                {'start': '2022-01-01', 'end_exclusive': '2023-01-01'}]},
            'time_grain': 'month', 'requested_sources': [],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None, 'ranking': None, 'unresolved_slots': [],
        }))
        sql = ("WITH monthly AS (SELECT DATE_TRUNC('month', s.date) AS month, "
               'SUM(s.revenue) AS revenue FROM commerce.sales AS s '
               'WHERE s.date >= $1 AND s.date < $2 GROUP BY 1) '
               'SELECT SUM(m.revenue) AS revenue FROM monthly AS m LIMIT 1')
        result = self.verify(intent, sql, ('2022-01-01', '2023-01-01'))
        self.assertTrue(any('month time grain' in issue for issue in result.issues))

    def test_monthly_grain_in_unused_cte_does_not_satisfy_result_scope(self):
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': 'Show monthly revenue in 2022', 'operation': 'trend',
            'metrics': ['revenue'], 'dimensions': [], 'filters': [],
            'time_scope': {'mode': 'range', 'ranges': [
                {'start': '2022-01-01', 'end_exclusive': '2023-01-01'}]},
            'time_grain': 'month', 'requested_sources': [],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None, 'ranking': None, 'unresolved_slots': [],
        }))
        sql = ("WITH unused AS (SELECT DATE_TRUNC('month', s.date) AS month, "
               'SUM(s.revenue) AS revenue FROM commerce.sales AS s '
               'WHERE s.date >= $1 AND s.date < $2 GROUP BY 1) '
               'SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s '
               'WHERE s.date >= $1 AND s.date < $2 LIMIT 1')
        result = self.verify(intent, sql, ('2022-01-01', '2023-01-01'))
        self.assertTrue(any('month time grain' in issue for issue in result.issues))

    def test_week_request_rejects_month_grouping(self):
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': 'Show weekly revenue in 2022', 'operation': 'trend',
            'metrics': ['revenue'], 'dimensions': [], 'filters': [],
            'time_scope': {'mode': 'range', 'ranges': [
                {'start': '2022-01-01', 'end_exclusive': '2023-01-01'}]},
            'time_grain': 'week', 'requested_sources': [],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None, 'ranking': None, 'unresolved_slots': [],
        }))
        sql = ("SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue "
               'FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 GROUP BY month LIMIT 200')
        result = self.verify(intent, sql, ('2022-01-01', '2023-01-01'))
        self.assertTrue(any('week time grain' in issue for issue in result.issues))

    def test_filter_in_predicate_subquery_does_not_satisfy_outer_request(self):
        sql = REGIONAL_SQL.replace(
            'WHERE o.order_status = $1 AND ',
            'WHERE EXISTS (SELECT 1 FROM commerce.orders AS o2 WHERE o2.order_status = $1) AND ')
        result = self.verify(sql=sql)
        self.assertTrue(any('Requested filter is missing' in issue for issue in result.issues))

    def test_filter_in_unused_cte_does_not_satisfy_outer_request(self):
        sql = ('WITH unused AS (SELECT o.order_status FROM commerce.orders AS o '
               'WHERE o.order_status = $1) ' + REGIONAL_SQL.replace(
                   'WHERE o.order_status = $1 AND ', 'WHERE '))
        result = self.verify(sql=sql)
        self.assertTrue(any('Requested filter is missing' in issue for issue in result.issues))

    def test_wrong_geographic_zip_basis_is_rejected(self):
        sql = REGIONAL_SQL.replace('g.zip = o.zip', 'g.zip = c.zip').replace(
            'FROM commerce.orders AS o ',
            'FROM commerce.orders AS o JOIN commerce.customers AS c ON c.customer_id = o.customer_id ')
        result = self.verify(sql=sql)
        self.assertTrue(any('ZIP join' in issue for issue in result.issues))

    def test_sales_revenue_substitution_fails_canonical_formula(self):
        sql = ('SELECT g.region, SUM(s.revenue) AS revenue FROM commerce.sales AS s '
               'JOIN commerce.geography AS g ON g.zip = s.zip GROUP BY g.region LIMIT 200')
        result = self.verify(sql=sql, parameters=())
        self.assertEqual(result.status, 'incomplete')
        self.assertTrue(any('Canonical metric validation failed' in issue for issue in result.issues))

    def test_metric_formula_in_unused_cte_does_not_verify_constant_result(self):
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': 'Total revenue', 'operation': 'aggregate',
            'metrics': ['revenue'], 'dimensions': [], 'filters': [],
            'time_scope': {'mode': 'all', 'ranges': []}, 'time_grain': None,
            'requested_sources': [], 'explicit_source_restriction': False,
            'geographic_basis': None, 'geographic_coverage': None,
            'ranking': None, 'unresolved_slots': [],
        }))
        sql = ('WITH unused AS (SELECT SUM(s.revenue) AS revenue '
               'FROM commerce.sales AS s) SELECT 1 AS revenue LIMIT 1')
        result = self.verify(intent, sql, ())
        self.assertNotEqual(result.status, 'verified')

    def test_missing_ontology_delivered_filter_fails(self):
        sql = REGIONAL_SQL.replace('o.order_status = $1 AND ', '').replace(
            'o.order_date >= $2', 'o.order_date >= $1').replace('o.order_date < $3', 'o.order_date < $2')
        result = self.verify(sql=sql, parameters=('2026-05-01', '2026-06-01'))
        self.assertEqual(result.status, 'incomplete')
        self.assertTrue(any('Canonical metric validation failed' in issue for issue in result.issues))

    def test_ranking_direction_and_limit_are_preserved(self):
        intent = regional_intent(ranking={'metric': 'regional_revenue', 'direction': 'desc', 'limit': 5})
        sql = REGIONAL_SQL.replace('GROUP BY g.region LIMIT 200',
                                   'GROUP BY g.region ORDER BY revenue ASC LIMIT 4')
        result = self.verify(intent, sql)
        self.assertIn('Requested ranking direction changed', result.issues)
        self.assertIn('Requested ranking limit changed', result.issues)

    def test_ranking_alias_must_resolve_to_the_requested_metric(self):
        intent = regional_intent(ranking={'metric': 'regional_revenue', 'direction': 'desc', 'limit': 5})
        sql = REGIONAL_SQL.replace('GROUP BY g.region LIMIT 200',
                                   'GROUP BY g.region ORDER BY revenue DESC LIMIT 5')
        self.assertEqual(self.verify(intent, sql).status, 'verified')

    def test_ranking_by_a_different_aggregate_is_incomplete(self):
        intent = regional_intent(ranking={'metric': 'regional_revenue', 'direction': 'desc', 'limit': 5})
        sql = REGIONAL_SQL.replace('GROUP BY g.region LIMIT 200',
                                   'GROUP BY g.region ORDER BY COUNT(DISTINCT o.order_id) DESC LIMIT 5')
        result = self.verify(intent, sql)
        self.assertTrue(any('Ranking metric validation failed' in issue for issue in result.issues))

    def test_product_filter_must_be_present_with_bound_value(self):
        intent = regional_intent(filters=[
            {'field': 'commerce.orders.order_status', 'operator': 'eq', 'value': 'delivered',
             'provenance': 'ontology_required'},
            {'field': 'commerce.products.category', 'operator': 'eq', 'value': 'shoes'},
        ])
        result = self.verify(intent)
        self.assertTrue(any('commerce.products.category' in issue for issue in result.issues))

    def test_confirmed_all_regions_does_not_accept_region_filter(self):
        predicates = (
            "g.region = 'North'", "g.region IN ('North')",
            "g.region <> 'North'", "g.region IS NOT NULL",
        )
        for predicate in predicates:
            with self.subTest(predicate=predicate):
                sql = REGIONAL_SQL.replace('GROUP BY g.region', f'AND {predicate} GROUP BY g.region')
                result = self.verify(sql=sql)
                self.assertTrue(any('All-region coverage' in issue for issue in result.issues))

    def test_unrestricted_time_does_not_accept_an_added_date_filter(self):
        intent = regional_intent(time_scope={'mode': 'all', 'ranges': []})
        sql = REGIONAL_SQL.replace(
            ' AND o.order_date >= $2 AND o.order_date < $3', '')
        sql = sql.replace('GROUP BY g.region', "AND o.order_date >= '2026-05-01' GROUP BY g.region")
        result = self.verify(intent, sql, ('delivered',))
        self.assertTrue(any('unrestricted time scope' in issue for issue in result.issues))

    def test_unsupported_time_mode_is_explicitly_inconclusive(self):
        intent = regional_intent(time_scope={'mode': 'snapshot', 'ranges': [
            {'start': '2026-05-01', 'end_exclusive': '2026-05-02'}]})
        self.assertEqual(self.verify(intent).status, 'inconclusive')

    def test_write_sql_still_fails_existing_security_validator(self):
        with self.assertRaises(SQLSecurityError):
            validate_sql_security('DELETE FROM commerce.orders', allowed_sources=set(APPROVED_COLUMNS))

    def test_list_fields_do_not_require_aggregate_grouping(self):
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': 'List product IDs, names and categories.',
            'operation': 'list', 'metrics': [], 'dimensions': ['product_id', 'product_name', 'category'],
            'filters': [], 'time_scope': {'mode': 'all', 'ranges': []},
            'requested_sources': [{'name': 'commerce.products', 'provenance': 'user'}],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None, 'ranking': None, 'unresolved_slots': [],
        }))
        sql = ('SELECT p.product_id, p.product_name, p.category '
               'FROM commerce.products AS p ORDER BY p.product_id LIMIT 200')
        self.assertEqual(self.verify(intent, sql, ()).status, 'verified')


if __name__ == '__main__':
    unittest.main()
