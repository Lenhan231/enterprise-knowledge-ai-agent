import tempfile
import unittest
from html import unescape

from core.dashboards.models import DashboardDocument, QuerySpec, QueryResult, TileSpec
from core.dashboards.render import render_dashboard
from core.dashboards.store import DashboardStore, Conflict


def document(**changes):
    values = dict(title='<script>alert(1)</script>', description='Sales overview',
                  queries=[QuerySpec(id='sales', question='Monthly revenue in 2026')],
                  tiles=[TileSpec(id='total', title='Revenue', kind='kpi', query_id='sales', measures=['revenue'])],
                  results=[QueryResult(id='sales', question='Monthly revenue in 2026', status='complete',
                                       payload={'rows': [{'revenue': 12.5}]})])
    return DashboardDocument(**(values | changes))


class DashboardDocumentsTest(unittest.TestCase):
    def test_html_escapes_text_and_uses_observed_kpi(self):
        html = render_dashboard(document())
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('12.5', html)
        self.assertIn("script-src 'none'", unescape(html))

    def test_kpi_does_not_sum_grouped_rows(self):
        doc = document()
        doc.results[0].payload['rows'].append({'revenue': 10})
        self.assertIn('one aggregate row', render_dashboard(doc))

    def test_private_store_and_stale_revision(self):
        with tempfile.TemporaryDirectory() as path:
            store = DashboardStore(path)
            doc = document()
            store.create('alice', doc)
            self.assertIsNone(store.get('bob', doc.id))
            self.assertEqual([], store.list('bob'))
            store.save('alice', doc, expected_revision=1)
            with self.assertRaises(Conflict):
                store.save('alice', doc, expected_revision=1)
            self.assertEqual(2, store.get('alice', doc.id).revision)

    def test_rejects_dangling_tile_reference(self):
        with self.assertRaises(ValueError):
            document(tiles=[TileSpec(id='bad', title='Bad', kind='table', query_id='unknown')])

    def test_saved_decimal_strings_render_line_and_summary(self):
        doc = document(tiles=[TileSpec(id='trend', title='Revenue', kind='line', query_id='sales',
                                      dimension='month', measures=['revenue']),
                              TileSpec(id='stats', title='Summary', kind='summary', query_id='sales', measures=['revenue'])])
        doc.results[0].payload = {'rows': [{'month': '2026-07-01', 'revenue': '12.5'}, {'month': '2026-08-01', 'revenue': '25'}],
                                 'sql': "SELECT DATE_TRUNC('month', date) AS month, SUM(revenue) AS revenue FROM commerce.sales GROUP BY 1"}
        html = render_dashboard(doc)
        self.assertIn('<svg', html)
        self.assertNotIn('Chart unavailable', html)
        self.assertIn('mean 18.75', html)

    def test_incompatible_line_falls_back_to_source_table(self):
        doc = document(tiles=[TileSpec(id='trend', title='Bad line', kind='line', query_id='sales')])
        doc.results[0].payload = {'rows': [{'category': 'A', 'revenue': 12}, {'category': 'B', 'revenue': 25}],
                                 'sql': 'SELECT category, SUM(revenue) AS revenue FROM commerce.sales GROUP BY category'}
        html = render_dashboard(doc)
        self.assertIn('Chart unavailable', html)
        self.assertIn('<table>', html)


if __name__ == '__main__':
    unittest.main()
