import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.agents.dashboard_agent import build_chart, requested_chart_type
from core.analytics.metric_mapping import requested_ranking_limit, decode_metric_mapping, compile_inventory_query
from core.analytics.metric_validation import MetricDefinitionError
from core.analytics.text_to_sql import relevant_schema_tables


class DashboardImprovementTest(unittest.TestCase):
    def test_supplemental_bilingual_chart_contracts(self):
        fixtures = {
            'C01': ([{'month': '2022-01-01', 'revenue': 10}, {'month': '2022-02-01', 'revenue': 20}],
                    "SELECT DATE_TRUNC('month', date) AS month, SUM(revenue) AS revenue FROM commerce.sales GROUP BY 1 LIMIT 200"),
            'C02': ([{'category': 'A', 'stockout_count': 2}, {'category': 'B', 'stockout_count': 3}],
                    "SELECT category, COUNT(*) AS stockout_count FROM commerce.inventory WHERE stockout_flag=true AND snapshot_date='2022-12-31' GROUP BY category LIMIT 200"),
            'C03': ([{'traffic_source': 'A', 'sessions': 10}, {'traffic_source': 'B', 'sessions': 20}],
                    'SELECT traffic_source, SUM(sessions) AS sessions FROM commerce.web_traffic GROUP BY traffic_source LIMIT 200'),
            'C04': ([{'stockout_count': 2, 'overstock_count': 3}],
                    'SELECT COUNT(*) FILTER (WHERE stockout_flag) AS stockout_count, COUNT(*) FILTER (WHERE overstock_flag) AS overstock_count FROM commerce.inventory'),
            'C05': ([{'traffic_source': name, 'sessions': value} for name, value in [('A', 30), ('B', 20), ('C', 10)]],
                    'SELECT traffic_source, SUM(sessions) AS sessions FROM commerce.web_traffic GROUP BY traffic_source ORDER BY 2 DESC LIMIT 3'),
            'C06': ([{'category': 'A', 'rating': 4.5, 'reviews': 30}],
                    'SELECT p.category, AVG(r.rating) AS rating, COUNT(*) AS reviews FROM commerce.reviews r JOIN commerce.products p ON r.product_id=p.product_id GROUP BY p.category LIMIT 200'),
        }
        questions = json.loads((Path(__file__).resolve().parents[1] /
            'data/evaluation/dashboard_chart_supplement_12.json').read_text(encoding='utf-8'))['questions']
        for case in questions:
            rows, sql = fixtures[case['id']]
            for language in ('english', 'vietnamese'):
                with self.subTest(case=case['id'], language=language):
                    payload = {'rows': rows, 'sql': sql, 'metadata': {}}
                    if case['expected_behavior'] == 'reject_chart':
                        with self.assertRaises(ValueError):
                            build_chart(payload, case[language])
                    else:
                        self.assertEqual(build_chart(payload, case[language]).type, case['expected_chart'])

    def test_b12_explicit_rank_limit_survives_interpretation_and_compilation(self):
        question = ('On 2022-12-31, list the 10 inventory products with the lowest stock_on_hand, '
                    'breaking ties by product_id ascending.')
        mapping = decode_metric_mapping(json.dumps({'metrics': ['stock_on_hand'], 'dimensions': ['product_id'],
            'time': {'mode': 'snapshot', 'start': '2022-12-31'}, 'representation': 'product',
            'ranking': {'metric': 'stock_on_hand', 'direction': 'asc', 'limit': 10}}), question)
        sql, _ = compile_inventory_query(mapping)
        self.assertEqual(mapping.ranking.limit, 10)
        self.assertIn('LIMIT 10', sql)

    def test_bilingual_limits_and_conflicts(self):
        for question in ['ten inventory products', '10 catalog products', 'top ten products',
                         '10 sản phẩm tồn kho', 'mười sản phẩm tồn kho']:
            with self.subTest(question=question):
                self.assertEqual(requested_ranking_limit(question), 10)
        self.assertIsNone(requested_ranking_limit('Products with stock below 10 at 2022-12-31'))
        for question in ['top 10 products limit 5', 'top 201 products', 'limit 0']:
            with self.subTest(question=question), self.assertRaises(MetricDefinitionError):
                requested_ranking_limit(question)

    def test_page_views_and_return_directive_select_web_traffic(self):
        for question in ['Which month of 2022 had the largest number of page views? Return the month and value.',
                         'Show page_views in 2022', 'Tháng nào năm 2022 có lượt xem trang cao nhất?']:
            with self.subTest(question=question):
                tables = relevant_schema_tables(question, {})
                self.assertIn('commerce.web_traffic', tables)
                self.assertNotIn('commerce.returns', tables)
        self.assertIn('commerce.returns', relevant_schema_tables('Sum returned items by return_date in 2022', {}))

    def test_compact_chart_names(self):
        for question, expected in [('barchart', 'bar'), ('bar-chart', 'bar'), ('linechart', 'line'),
                                   ('biểu đồ cột', 'bar'), ('biểu đồ tròn', 'donut')]:
            self.assertEqual(requested_chart_type(question), expected)

    def test_ranked_product_ids_are_dimensions_and_names_stay_in_table(self):
        rows = [{'snapshot_date': '2022-12-31', 'product_id': 1, 'product_name': 'Same name', 'stock_on_hand': 3},
                {'snapshot_date': '2022-12-31', 'product_id': 18, 'product_name': 'Same name', 'stock_on_hand': 4}]
        chart = build_chart({'rows': rows, 'sql': "SELECT i.snapshot_date, i.product_id, i.product_name, i.stock_on_hand FROM commerce.inventory i WHERE i.snapshot_date='2022-12-31' ORDER BY i.stock_on_hand, i.product_id LIMIT 10",
                             'metadata': {}}, 'barchart of lowest 10 products at 2022-12-31')
        self.assertEqual(chart.type, 'bar')
        self.assertEqual(chart.categories, ['1', '18'])
        self.assertEqual(chart.series[0].values, [3, 4])
        self.assertEqual(rows[0]['product_name'], 'Same name')
        without_names = [{key: value for key, value in row.items() if key != 'product_name'} for row in rows]
        second = build_chart({'rows': without_names, 'sql': 'SELECT i.snapshot_date, i.product_id, i.stock_on_hand FROM commerce.inventory i LIMIT 10',
                              'metadata': {}}, 'bar chart of products at 2022-12-31')
        self.assertEqual(second.categories, ['1', '18'])


if __name__ == '__main__':
    unittest.main()
