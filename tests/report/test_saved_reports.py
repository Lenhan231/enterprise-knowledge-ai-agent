from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import os
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from core.agents.report.document import ReportDocument, ReportPresentation
from core.agents.report.sales_performance import load_contract, parse_request, populate_sections, evaluate_decisions
from core.agents.report.store import ReportStore
from core.agents.dashboard.store import Conflict


def sample_report():
    report = deepcopy(load_contract()['runtime_output_template'])
    report['request'] = parse_request('Monthly revenue report 2026')
    for metric in report['metrics']:
        metric['status'] = 'not_available'
    metric = report['metrics'][0]
    metric.update(value=18881151.9, status='available', evidence=[dict(source_table='commerce.sales', query_id='08eb2ef823288614', filters=report['request'], row_count=1, document_id=None, citation=None)])
    report['data_quality']['limitations'] = ['Comparison period does not have complete daily records.']
    populate_sections(report); evaluate_decisions(report, {})
    return report


class SavedReportTest(unittest.TestCase):
    def test_single_month_defaults_to_kpis_and_preserves_explicit_chart_choices(self):
        from core.agents.report.presentation import default_chart_types
        report = sample_report()
        report['request'] = parse_request('Monthly revenue report May 2026')
        for widget in report['dashboard']['widgets']:
            if widget['type'] == 'line':
                widget['data'] = [{'period':'2026-05-01', **{key:1 for key in widget['metric_ids']}}]
        defaults = default_chart_types(report)
        self.assertTrue(all(defaults[key] == 'kpi_row' for key in ('sales_trend','sales_discount','web_sessions','line_breakdown')))
        self.assertEqual(ReportDocument(report=report).presentation.chart_types, defaults)
        import fitz
        from core.agents.report.export import export_pdf
        pdf = fitz.open(stream=export_pdf(ReportDocument(report=report)),filetype='pdf')
        self.assertEqual(sum(len(page.get_image_info()) for page in pdf),0)
        chosen = ReportDocument(report=report, presentation=ReportPresentation(chart_types={'sales_trend':'bar'}))
        self.assertEqual(chosen.presentation.chart_types['sales_trend'], 'bar')
        chosen_pdf = fitz.open(stream=export_pdf(chosen),filetype='pdf')
        self.assertEqual(sum(len(page.get_image_info()) for page in chosen_pdf),1)
        report['request'] = parse_request('Monthly revenue report for 2026')
        self.assertNotIn('sales_trend', default_chart_types(report))

    def test_saved_2025_chart_keeps_twelve_calendar_months_without_imputing_sales(self):
        from core.agents.report.presentation import calendar_rows
        scope = parse_request('Monthly revenue report for 2025')
        widget = dict(x_dimension='period', metric_ids=['company_revenue','company_gross_profit'], data=[
            dict(period='2025-11-01',company_revenue=1132584,company_gross_profit=214065.64),
            dict(period='2025-12-01',company_revenue=2237062.71,company_gross_profit=326091.25)])
        original = deepcopy(widget)
        rows = calendar_rows(widget, scope)
        self.assertEqual(scope['period'],dict(start='2025-01-01',end_exclusive='2026-01-01'))
        self.assertEqual([r['period'] for r in rows],[f'2025-{month:02d}-01' for month in range(1,13)])
        self.assertTrue(all(r['company_revenue'] is None and r['company_gross_profit'] is None for r in rows[:10]))
        self.assertEqual(rows[10:],widget['data'])
        self.assertEqual(widget,original)

    def test_owner_isolation_revision_conflicts_and_edit_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReportStore(directory)
            original = sample_report()
            doc = store.create('alice', ReportDocument(report=original))
            self.assertEqual(len(store.list('alice')), 1)
            self.assertEqual(store.list('bob'), [])
            self.assertIsNone(store.get('bob', doc.id))
            doc.presentation.section_order.reverse()
            doc.presentation.hidden_sections = ['performance_analysis']
            doc.presentation.chart_types['sales_trend'] = 'bar'
            doc = store.save('alice', doc, 1)
            self.assertEqual(store.get('alice', doc.id).report, original)
            self.assertEqual(ReportStore(directory).get('alice', doc.id).presentation, doc.presentation)
            with self.assertRaises(Conflict): store.save('alice', doc, 1)
            with self.assertRaises(Conflict): store.delete('bob', doc.id, 2)
            store.delete('alice', doc.id, 2)
            self.assertEqual(store.list('alice'), [])

    def test_layout_validation(self):
        for values in ({'section_order': ['invented']}, {'chart_types': {'sales_trend': 'script'}}, {'hidden_sections': list(load_contract()['sections'])}):
            with self.assertRaises(ValueError): ReportPresentation(**values)

    def test_pdf_has_vnd_and_edits_without_citation_tokens(self):
        import fitz
        from core.agents.report.export import export_pdf
        doc = ReportDocument(report=sample_report())
        doc.presentation.hidden_sections = ['performance_analysis']
        doc.presentation.text_edits['executive_summary'] = 'Edited executive summary.'
        payload = export_pdf(doc)
        pdf = fitz.open(stream=payload, filetype='pdf')
        text = ''.join(page.get_text() for page in pdf)
        self.assertIn('Edited executive summary.', text)
        self.assertIn('VND', text)
        self.assertNotIn('Performance Analysis', text)
        self.assertNotIn('08eb2ef823288614', text)
        self.assertNotIn('unknown_currency_amount', text)
        self.assertEqual(sum(len(page.get_links()) for page in pdf), 0)

    def test_pdf_charts_do_not_shrink_into_page_remainders(self):
        import fitz
        from core.agents.report.export import export_pdf
        report = sample_report()
        for widget in report['dashboard']['widgets']:
            if widget['type'] == 'line':
                widget['data'] = [{'period': period, **{key: value for key in widget['metric_ids']}}
                                  for period, value in (('2026-01-01',10),('2026-02-01',20))]
        pdf = fitz.open(stream=export_pdf(ReportDocument(report=report)), filetype='pdf')
        boxes = [image['bbox'] for page in pdf for image in page.get_image_info()]
        self.assertEqual(len(boxes),3)
        self.assertTrue(all(box[2]-box[0]>450 and box[3]-box[1]>150 for box in boxes))
        document = ReportDocument(report=report)
        document.presentation.section_order.remove('performance_analysis')
        document.presentation.section_order.insert(0,'performance_analysis')
        reordered = fitz.open(stream=export_pdf(document),filetype='pdf')
        self.assertIn('Performance Analysis', reordered[0].get_text())


class SavedReportAPITest(unittest.TestCase):
    def test_generate_reopen_edit_export_and_access_boundaries(self):
        import jwt
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.reports import router, get_store
        from core.models.agents import AgentResult
        secret = 'saved-report-test-secret-at-least-32-characters'
        def token(subject, role='finance_analyst'):
            return {'Authorization': 'Bearer ' + jwt.encode({'sub':subject,'role':role,'exp':4102444800},secret,algorithm='HS256')}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'AUTH_SECRET_KEY':secret}):
            app = FastAPI(); app.include_router(router)
            store = ReportStore(directory); app.dependency_overrides[get_store] = lambda: store
            report = sample_report()
            agent = SimpleNamespace(generate_from_template=AsyncMock(return_value=(AgentResult(answer='report',agent='report',data={'report':report}), b'', 'application/json')))
            app.state.agent_router = SimpleNamespace(report_agent=agent)
            with TestClient(app) as client:
                self.assertEqual(client.get('/api/reports').status_code,401)
                self.assertEqual(client.get('/api/reports',headers=token('employee','employee')).status_code,403)
                response = client.post('/api/reports',json={'question':'Monthly revenue report 2026'},headers=token('alice'))
                self.assertEqual(response.status_code,201,response.text)
                doc = response.json()['document']; path = '/api/reports/' + doc['id']
                self.assertEqual(agent.generate_from_template.await_args.args[0].identity.subject,'alice')
                self.assertEqual(client.get(path,headers=token('bob')).status_code,404)
                self.assertEqual(client.get('/api/reports',headers=token('bob')).json()['reports'],[])
                edit = dict(title='Edited report', revision=1, presentation=doc['presentation'])
                edit['presentation']['section_order'].reverse()
                edit['presentation']['hidden_sections']=['performance_analysis']
                edit['presentation']['chart_types']['sales_trend']='bar'
                self.assertEqual(client.put(path,json={**edit,'report':{}},headers=token('alice')).status_code,422)
                from core.agents.report.document import InventoryPresentation
                wrong_layout = {**edit, 'presentation': InventoryPresentation().model_dump()}
                self.assertEqual(client.put(path,json=wrong_layout,headers=token('alice')).status_code,422)
                self.assertEqual(client.put(path,json=edit,headers={**token('alice'),'Origin':'https://untrusted.example'}).status_code,403)
                saved = client.put(path,json=edit,headers=token('alice'))
                self.assertEqual(saved.status_code,200,saved.text)
                self.assertEqual(saved.json()['document']['report'],report)
                self.assertEqual(client.put(path,json=edit,headers=token('alice')).status_code,409)
                self.assertEqual(client.get(path+'/pdf',headers=token('bob')).status_code,404)
                pdf = client.get(path+'/pdf',headers=token('alice'))
                self.assertEqual(pdf.headers['content-type'],'application/pdf')
                self.assertTrue(pdf.content.startswith(b'%PDF'))
                self.assertEqual(client.get(path+'/pdf?revision=1',headers=token('alice')).status_code,409)
                self.assertEqual(client.get(path+'/pdf?revision=2',headers=token('alice')).status_code,200)
                self.assertEqual(client.delete(path+'?revision=2',headers=token('alice')).status_code,204)
                self.assertEqual(client.get('/api/reports',headers=token('alice')).json()['reports'],[])


@unittest.skipUnless(os.getenv('REPORT_POSTGRES_TEST_URL'), 'Explicit report integration database required')
class SavedReportPostgresTest(unittest.TestCase):
    def test_owner_rls_reopen_edits_and_dashboard_library_separation(self):
        from uuid import uuid4
        from core.agents.report.store import PostgresReportStore
        from core.agents.dashboard.postgres_store import PostgresDashboardStore
        store = PostgresReportStore(os.environ['REPORT_POSTGRES_TEST_URL'])
        subject = 'report-test-' + uuid4().hex
        doc = store.create(subject,ReportDocument(report=sample_report()))
        try:
            self.assertEqual(len(store.list(subject)),1)
            self.assertEqual(PostgresDashboardStore(os.environ['REPORT_POSTGRES_TEST_URL']).list(subject),[])
            self.assertIsNone(store.get(subject+'-other',doc.id))
            with store.connect_owner(store.owner(subject+'-other')) as cursor:
                cursor.execute('SELECT id FROM dashboard_private.reports WHERE id=%s',(doc.id,))
                self.assertEqual(cursor.fetchall(),[])
            doc.title = 'Revised saved report'
            doc = store.save(subject,doc,1)
            self.assertEqual(store.get(subject,doc.id).title,doc.title)
            with self.assertRaises(Conflict): store.save(subject,doc,1)
        finally:
            store.delete(subject,doc.id,doc.revision)


if __name__ == '__main__': unittest.main()
