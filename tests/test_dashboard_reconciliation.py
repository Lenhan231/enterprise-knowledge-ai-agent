import unittest

from core.dashboards.presentation import reconcile
from core.dashboards.models import TileSpec
from test_dashboard_documents import document


class DashboardReconciliationTest(unittest.TestCase):
    def monthly(self, dimension='date'):
        doc = document(tiles=[TileSpec(id='trend', title='Trend', kind='line', query_id='sales',
                                      dimension=dimension, measures=['total_revenue'])])
        doc.results[0].payload = {'sql': "SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue FROM commerce.sales s GROUP BY 1 LIMIT 200",
                                 'rows': [{'month': '2026-01-01', 'revenue': '10'}, {'month': '2026-02-01', 'revenue': '20'}]}
        return doc

    def test_temporal_alias_binds_to_actual_month(self):
        doc = reconcile(self.monthly())
        self.assertEqual('month', doc.tiles[0].dimension)
        self.assertEqual(['revenue'], doc.tiles[0].measures)
        self.assertEqual('complete', doc.status)

    def test_does_not_reinterpret_category_as_month(self):
        doc = reconcile(self.monthly('category'))
        self.assertEqual('category', doc.tiles[0].dimension)
        self.assertEqual('failed', doc.status)
        self.assertEqual('unavailable', doc.tile_status['trend']['status'])

    def test_invalid_kpi_is_not_complete_and_is_not_summed(self):
        doc = self.monthly('month')
        doc.tiles.append(TileSpec(id='total', title='Total', kind='kpi', query_id='sales', measures=['revenue']))
        reconcile(doc)
        self.assertEqual('partial', doc.status)
        self.assertIn('one aggregate row', doc.tile_status['total']['message'])

    def test_grouped_year_is_not_inferred_as_a_measure(self):
        doc = self.monthly(None)
        doc.tiles[0].measures = []
        doc.results[0].payload['sql'] = "SELECT DATE_TRUNC('month', s.date) AS month, EXTRACT(YEAR FROM s.date) AS year, SUM(s.revenue) AS revenue FROM commerce.sales s GROUP BY 1,2 LIMIT 200"
        for row in doc.results[0].payload['rows']:
            row['year'] = 2026
        reconcile(doc)
        self.assertEqual(['revenue'], doc.tiles[0].measures)
        self.assertEqual('month', doc.tiles[0].dimension)
        self.assertEqual('complete', doc.status)

    def test_ambiguous_date_dimensions_are_not_guessed(self):
        doc = self.monthly()
        doc.results[0].payload['sql'] = "SELECT DATE_TRUNC('month', s.date) AS month, s.date AS day, SUM(s.revenue) AS revenue FROM commerce.sales s GROUP BY 1,2 LIMIT 200"
        for row in doc.results[0].payload['rows']:
            row['day'] = row['month']
        reconcile(doc)
        self.assertEqual('date', doc.tiles[0].dimension)
        self.assertEqual('failed', doc.status)

    def test_wide_table_does_not_break_saved_document_validation(self):
        from core.dashboards.models import DashboardDocument
        doc = self.monthly(None)
        doc.tiles[0].kind = 'table'
        doc.tiles[0].measures = []
        doc.results[0].payload = {'sql': 'SELECT ' + ','.join(f'SUM(revenue) AS metric_{i}' for i in range(5)) + ' FROM commerce.sales',
                                 'rows': [{f'metric_{i}': i for i in range(5)}]}
        reconcile(doc)
        self.assertEqual('complete', DashboardDocument.model_validate_json(doc.model_dump_json()).status)
