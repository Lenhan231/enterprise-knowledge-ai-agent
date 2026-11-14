import json
import unittest
from datetime import date

from core.analytics.text_to_sql import decode_query_plan, SQLValidationError


class BetweenDateBindingTest(unittest.TestCase):
    sql = "SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue FROM commerce.sales AS s WHERE s.date BETWEEN $1 AND $2 GROUP BY 1 ORDER BY 1 LIMIT 200"

    def test_monthly_revenue_between_binds_native_dates(self):
        plan = decode_query_plan(json.dumps({'sql': self.sql, 'parameters': ['2026-01-01', '2026-12-31']}))
        self.assertEqual((date(2026, 1, 1), date(2026, 12, 31)), plan.parameters)
        self.assertIn('BETWEEN $1 AND $2', plan.sql)

    def test_invalid_date_is_rejected_before_execution(self):
        with self.assertRaises(SQLValidationError):
            decode_query_plan(json.dumps({'sql': self.sql, 'parameters': ['2026-99-01', '2026-12-31']}))

    def test_numeric_range_does_not_receive_date_conversion(self):
        sql = 'SELECT SUM(s.revenue) AS revenue FROM commerce.sales s WHERE s.revenue BETWEEN $1 AND $2 LIMIT 1'
        plan = decode_query_plan(json.dumps({'sql': sql, 'parameters': [10, 20]}))
        self.assertEqual((10, 20), plan.parameters)

    def test_discovered_date_column_and_negated_between(self):
        sql = self.sql.replace('s.date', 's.business_date').replace(' BETWEEN ', ' NOT BETWEEN ')
        plan = decode_query_plan(json.dumps({'sql': sql, 'parameters': ['2026-01-01', '2026-12-31']}),
            schema_columns={'commerce.sales': {'business_date', 'revenue'}},
            allowed_sources={'commerce.sales'}, date_columns={('commerce.sales', 'business_date')})
        self.assertEqual((date(2026, 1, 1), date(2026, 12, 31)), plan.parameters)
