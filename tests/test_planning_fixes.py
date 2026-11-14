import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.analytics.text_to_sql import validate_commerce_sql, SQLValidationError, APPROVED_COLUMNS
from core.analytics.metric_validation import validate_metric_definitions, MetricDefinitionError
from core.analytics.metric_mapping import decode_metric_mapping


class PlanningFixTest(unittest.TestCase):
    def test_order_dimensions_keep_count_formula(self):
        for dimension, join in [('o.payment_method', ''), ('c.city',
                ' JOIN commerce.customers c ON o.customer_id=c.customer_id')]:
            sql = f'SELECT {dimension}, COUNT(DISTINCT o.order_id) AS order_count FROM commerce.orders o{join} GROUP BY {dimension} LIMIT 200'
            validate_commerce_sql(sql)
            self.assertIn('order_count', validate_metric_definitions(sql, {'order_count'}, [], APPROVED_COLUMNS))

    def test_monthly_revenue_lag_and_security_boundary(self):
        sql = "WITH monthly AS (SELECT DATE_TRUNC('month',s.date) AS month, SUM(s.revenue) AS revenue FROM commerce.sales s GROUP BY 1) SELECT m.month, m.revenue, (m.revenue-LAG(m.revenue) OVER (ORDER BY m.month))/NULLIF(LAG(m.revenue) OVER (ORDER BY m.month),0) AS growth FROM monthly m ORDER BY 1 LIMIT 200"
        validate_commerce_sql(sql)
        self.assertIn('revenue', validate_metric_definitions(sql, {'revenue'}, [], APPROVED_COLUMNS))
        for unsafe in ['DELETE FROM commerce.orders', 'SELECT pg_sleep(1) FROM commerce.orders o LIMIT 1',
                       'SELECT x.secret FROM public.secrets x LIMIT 1']:
            with self.assertRaises(SQLValidationError):
                validate_commerce_sql(unsafe)
        with self.assertRaises(MetricDefinitionError):
            validate_metric_definitions(sql.replace('SUM(s.revenue)', 'AVG(s.revenue)'), {'revenue'}, [], APPROVED_COLUMNS)

    def test_separate_flag_counts_cannot_become_intersection(self):
        mapping = json.dumps({'metrics': ['observed_product_count'], 'dimensions': [],
            'time': {'mode': 'snapshot', 'start': '2022-12-31'},
            'filters': [{'field': 'stockout_indicator', 'operator': 'eq', 'value': True},
                        {'field': 'overstock_indicator', 'operator': 'eq', 'value': True}]})
        with self.assertRaises(MetricDefinitionError) as error:
            decode_metric_mapping(mapping, 'Count products with stockout_flag=true and count products with overstock_flag=true at 2022-12-31')
        self.assertEqual(error.exception.code, 'interpretation_invalid')
