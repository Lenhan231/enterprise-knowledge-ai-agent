import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from core.agents.dashboard.formatting import format_number, format_datetime, format_value, axis_date


class DashboardFormattingTest(unittest.TestCase):
    def test_browser_formatting(self):
        import subprocess
        root=Path(__file__).resolve().parents[2]
        result=subprocess.run(['node','--test','tests/dashboard/test_dashboard_formatting.cjs'],cwd=root,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)

    def test_numbers_have_vietnamese_grouping_without_scientific_notation(self):
        self.assertEqual(format_number(Decimal('1234567.5')), '1.234.567,5')
        self.assertEqual(format_number(Decimal('0.0000001')), '0')
        self.assertEqual(format_number(Decimal('-0.001')), '0')
        self.assertEqual(format_number(None), '—')
        self.assertEqual(format_number(float('inf')), '—')
        self.assertEqual(format_number(1234.56, unit='count'), '1.235')
        self.assertEqual(format_number(12.56, unit='percent'), '12,6%')
        self.assertEqual(format_number(.1256, unit='fraction'), '12,6%')

    def test_currency_is_only_added_when_confirmed(self):
        from core.agents.dashboard.render import display_context
        self.assertEqual(format_number(1234567.5, unit='currency (unconfirmed)'), '1.234.568')
        self.assertEqual(format_number(1234567.5, unit='currency', currency='VND'), '1.234.568 ₫')
        for sql in ("SELECT SUM(s.revenue) AS total, 'VND' AS currency FROM commerce.sales s",
                    "WITH x AS (SELECT 'VND' AS currency FROM commerce.sales s) SELECT x.currency FROM x"):
            self.assertIsNone(display_context({'sql':sql,'rows':[{'total':1234,'currency':'VND'}]})[1])

    def test_dates_use_vietnam_time_and_calendar_labels(self):
        instant=datetime(2026,11,17,16,7,41,123456,tzinfo=timezone.utc)
        self.assertEqual(format_datetime(instant), '17/11/2026 23:07')
        self.assertEqual(format_value('2026-11-17'), '17/11/2026')
        self.assertEqual(format_value(instant.isoformat()), '17/11/2026 23:07')
        self.assertEqual(axis_date('2026-01-01','month'), '01/2026')
        self.assertEqual(axis_date('2026-11-17','day'), '17/11')

    def test_rendered_values_are_formatted_without_modifying_the_payload(self):
        from copy import deepcopy
        from core.agents.dashboard.models import TileSpec, QueryResult
        from core.agents.dashboard.render import tile_content, table
        payload={'sql':'SELECT SUM(i.total_amount) AS total, i.currency FROM commerce.invoices AS i GROUP BY i.currency LIMIT 1',
                 'rows':[{'total':Decimal('1234567.5'),'currency':'VND'}]}
        before=deepcopy(payload)
        tile=TileSpec(id='money',query_id='money',title='Total',kind='kpi',measures=['total'])
        result=QueryResult(id='money',question='Total',status='complete',payload=payload)
        self.assertIn('1.234.568 ₫',tile_content(tile,result))
        self.assertEqual(payload,before)
        result.payload['rows'][0]['currency']=None
        self.assertNotIn('₫',tile_content(tile,result))
        html=table([{'product_id':12345,'date':'2026-11-17','value':Decimal('1234.567891'),'unsafe':'<script>'}])
        self.assertIn('12345',html)
        self.assertIn('17/11/2026',html)
        self.assertIn('1.234,57',html)
        self.assertIn('&lt;script&gt;',html)

    def test_provenance_parameters_stay_exact_and_currency_labels_agree(self):
        from core.agents.dashboard.render import render_dashboard, chart_svg
        from core.agents.dashboard.models import DashboardDocument, QuerySpec, QueryResult, TileSpec
        from core.models.agents import ChartSpec, ChartSeries
        document=DashboardDocument(title='Audit',description='Exact SQL provenance',queries=[QuerySpec(id='q',question='Audit')],
            tiles=[TileSpec(id='t',query_id='q',title='Rows',kind='table')],
            results=[QueryResult(id='q',question='Audit',status='complete',payload={'rows':[{'value':1}], 'parameters':['00123',Decimal('0.0001')]})])
        self.assertIn('00123, 0.0001',render_dashboard(document))
        chart=ChartSpec(type='bar',title='Revenue',categories=['A'],series=[ChartSeries(name='Revenue',values=[1234])],unit='currency (unconfirmed)',x_label='Category',y_label='Revenue')
        html=chart_svg(chart,currency='VND')
        self.assertIn('VND',html)
        self.assertNotIn('unconfirmed',html)
