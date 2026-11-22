import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from core.agents.sql.query_contract import verify_query_contract
from core.agents.sql.sql_validation import SQLSecurityError, validate_sql_security
from core.agents.sql.text_to_sql import APPROVED_COLUMNS
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
        daily = sql.replace("DATE_TRUNC('month'", "DATE_TRUNC('day'")
        result = self.verify(intent, daily, parameters)
        self.assertTrue(any('month time grain' in issue for issue in result.issues))

    def test_wrong_geographic_zip_basis_is_rejected(self):
        sql = REGIONAL_SQL.replace('g.zip = o.zip', 'g.zip = c.zip').replace(
            'FROM commerce.orders AS o ',
            'FROM commerce.orders AS o JOIN commerce.customers AS c ON c.customer_id = o.customer_id ')
        result = self.verify(sql=sql)
        self.assertTrue(any('ZIP join' in issue for issue in result.issues))

    def test_wrong_metric_formula_does_not_fail_scope_contract(self):
        sql = REGIONAL_SQL.replace(
            'SUM(oi.quantity * oi.unit_price - oi.discount_amount)', 'SUM(oi.quantity)')
        self.assertEqual(self.verify(sql=sql).status, 'verified')

    def test_missing_ontology_delivered_filter_fails(self):
        sql = REGIONAL_SQL.replace('o.order_status = $1 AND ', '').replace(
            'o.order_date >= $2', 'o.order_date >= $1').replace('o.order_date < $3', 'o.order_date < $2')
        result = self.verify(sql=sql, parameters=('2026-05-01', '2026-06-01'))
        self.assertEqual(result.status, 'incomplete')
        self.assertTrue(any('Requested filter is missing or changed' in issue for issue in result.issues))

    def test_ranking_direction_and_limit_are_preserved(self):
        intent = regional_intent(ranking={'metric': 'regional_revenue', 'direction': 'desc', 'limit': 5})
        sql = REGIONAL_SQL.replace('GROUP BY g.region LIMIT 200',
                                   'GROUP BY g.region ORDER BY revenue ASC LIMIT 4')
        result = self.verify(intent, sql)
        self.assertIn('Requested ranking direction changed', result.issues)
        self.assertIn('Requested ranking limit changed', result.issues)

    def test_ranking_alias_keeps_requested_direction_and_limit(self):
        intent = regional_intent(ranking={'metric': 'regional_revenue', 'direction': 'desc', 'limit': 5})
        sql = REGIONAL_SQL.replace('GROUP BY g.region LIMIT 200',
                                   'GROUP BY g.region ORDER BY revenue DESC LIMIT 5')
        self.assertEqual(self.verify(intent, sql).status, 'verified')

    def test_ranking_by_an_unapproved_metric_does_not_fail_scope_contract(self):
        intent = regional_intent(ranking={'metric': 'regional_revenue', 'direction': 'desc', 'limit': 5})
        sql = REGIONAL_SQL.replace('GROUP BY g.region LIMIT 200',
                                   'GROUP BY g.region ORDER BY COUNT(DISTINCT o.order_id) DESC LIMIT 5')
        self.assertEqual(self.verify(intent, sql).status, 'verified')

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
