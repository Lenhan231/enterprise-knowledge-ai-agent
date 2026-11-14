import unittest

from core.agents.dashboard_agent import build_chart


class DashboardChartTest(unittest.TestCase):
    def payload(self, sql=None, rows=None):
        return {'sql': sql or 'SELECT traffic_source, SUM(sessions) AS sessions FROM commerce.web_traffic GROUP BY traffic_source LIMIT 200',
                'rows': rows or [{'traffic_source': 'Direct', 'sessions': 10}, {'traffic_source': 'Search', 'sessions': 20}]}

    def test_additive_composition_renders(self):
        chart = build_chart(self.payload(), 'donut chart')
        self.assertEqual('donut', chart.type)
        self.assertEqual([10, 20], chart.series[0].values)

    def test_incomplete_or_nonadditive_composition_is_rejected(self):
        payload = self.payload()
        for sql in [payload['sql'].replace('LIMIT 200', 'LIMIT 2'), payload['sql'].replace('SUM(sessions)', 'AVG(sessions)')]:
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                build_chart(self.payload(sql=sql), 'donut chart')

    def test_negative_donut_and_duplicate_groups_are_rejected(self):
        for rows in [[{'traffic_source': 'Direct', 'sessions': -1}],
                     [{'traffic_source': 'Direct', 'sessions': 1}, {'traffic_source': 'Direct', 'sessions': 2}]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                build_chart(self.payload(rows=rows), 'donut chart')

    def test_monthly_revenue_composition_remains_supported(self):
        payload = {'sql': "SELECT DATE_TRUNC('month', date) AS month, SUM(revenue) AS revenue FROM commerce.sales GROUP BY 1 LIMIT 200",
                   'rows': [{'month': '2026-07-01', 'revenue': 10}, {'month': '2026-08-01', 'revenue': 20}]}
        self.assertEqual('donut', build_chart(payload, 'donut chart').type)

    def test_incompatible_units_are_rejected(self):
        payload = {'sql': 'SELECT category, SUM(revenue) AS revenue, COUNT(*) AS products FROM commerce.sales GROUP BY category LIMIT 200',
                   'rows': [{'category': 'A', 'revenue': 10, 'products': 2}]}
        with self.assertRaises(ValueError):
            build_chart(payload, 'bar chart')
