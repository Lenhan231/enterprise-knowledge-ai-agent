import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.agents.dashboard_agent import build_chart
from core.analytics.metric_ontology import resolve_metric_names
from core.analytics.text_to_sql import APPROVED_COLUMNS, validate_commerce_sql
from core.analytics.metric_validation import validate_metric_definitions


class DashboardRepresentationTest(unittest.TestCase):
    def test_common_separators_plurals_and_review_counts(self):
        self.assertEqual(resolve_metric_names('order-counts'), {'order_count'})
        self.assertIn('fill_rate', resolve_metric_names('average fill-rate'))
        self.assertIn('review_count', resolve_metric_names('number of reviews by category'))
        self.assertNotIn('order_count', resolve_metric_names('count order-items'))

    def test_monthly_donut_accepts_complete_exclusive_buckets(self):
        sql = "SELECT DATE_TRUNC('month',s.date) AS month, SUM(s.revenue) AS revenue FROM commerce.sales s GROUP BY 1 ORDER BY 1 LIMIT 200"
        payload = {'sql': sql, 'rows': [{'month':'2026-07-01','revenue':10}, {'month':'2026-08-01','revenue':20}], 'metadata':{}}
        chart = build_chart(payload, 'Donut chart of monthly revenue')
        self.assertEqual(chart.type, 'donut')
        self.assertEqual(chart.series[0].values, [10,20])
        for wrong in [sql.replace('LIMIT 200','LIMIT 2'), sql.replace('SUM(s.revenue)', 'AVG(s.revenue)'),
                      sql.replace("DATE_TRUNC('month',s.date)", 's.revenue / 100')]:
            with self.subTest(sql=wrong), self.assertRaises(ValueError):
                build_chart({**payload, 'sql':wrong}, 'Donut chart of monthly revenue')

    def test_rating_and_review_count_by_category_have_compatible_sql(self):
        sql = ('SELECT p.category, AVG(r.rating) AS rating, COUNT(DISTINCT r.review_id) AS review_count '
               'FROM commerce.reviews r JOIN commerce.products p ON r.product_id=p.product_id '
               'GROUP BY p.category LIMIT 200')
        validate_commerce_sql(sql)
        definitions = validate_metric_definitions(sql, {'rating','review_count'}, [], APPROVED_COLUMNS)
        self.assertEqual(definitions['rating']['unit'], 'score')
        self.assertEqual(definitions['review_count']['unit'], 'reviews')
        with self.assertRaises(ValueError):
            build_chart({'sql':sql,'rows':[{'category':'A','rating':4.5,'review_count':12}],
                         'metadata':{'metrics':definitions}}, 'Bar chart of rating and review counts')
