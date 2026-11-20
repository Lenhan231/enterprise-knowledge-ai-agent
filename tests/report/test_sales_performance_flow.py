"""Report integration and opt-in PostgreSQL arithmetic fixtures; no database writes."""
from copy import deepcopy
import asyncio
from datetime import date, timedelta
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from core.agents.report.agent import ReportAgent
from core.agents.sql.agent import SQLAnalyticsAgent
from core.agents.sql.sales_report import plans
from core.agents.sql.text_to_sql import validate_commerce_sql
from core.models.agents import AgentRequest, VerifiedIdentity
from core.agents.report.sales_performance import parse_request, validate_report, load_contract


def request(text='Monthly revenue report May 2026', authorized=True):
    return AgentRequest(question=text, identity=VerifiedIdentity(subject='test', permissions={'analytics:read'} if authorized else set()))


class SalesFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_year_range_covers_both_years_in_report_and_monthly_decisions(self):
        from core.agents.report.presentation import calendar_rows
        repo = type('Repository', (), {'execute_approved_query': AsyncMock(return_value=[])})()
        agent = ReportAgent(None, SQLAnalyticsAgent(repo, inventory_only=False))
        result, raw, _ = await agent.generate_from_template(request('sales performance from 2025 to 2026'), source_mode='analytics')
        report = json.loads(raw)
        self.assertEqual(report['request']['period'], {'start':'2025-01-01', 'end_exclusive':'2027-01-01'})
        self.assertEqual(report['request']['granularity'], 'month')
        self.assertEqual(len(result.data['monthly_decisions']), 24)
        trend = next(w for w in report['dashboard']['widgets'] if w['id']=='sales_trend')
        rows = calendar_rows(trend, report['request'])
        self.assertEqual(len(rows), 24)
        self.assertEqual((rows[0]['period'], rows[-1]['period']), ('2025-01-01', '2026-12-01'))
        self.assertTrue(all(row['company_revenue'] is None for row in rows))
        validate_report(report)

    async def test_monthly_decisions_use_each_month_and_its_prior_month(self):
        calls = []
        async def execute(sql, *args):
            if 'WITH monthly AS' in sql:
                return [{**(await execute('WITH totals AS', date(2026,m,1), date(2026,m+1,1), date(2026,m-1,1) if m>1 else date(2025,12,1)))[0],
                         'period':date(2026,m,1)} for m in range(1,6)]
            if 'WITH totals AS' not in sql:
                return []
            calls.append(args)
            start, end, prior = args
            complete = end == date(2026, 6, 1) and start == date(2026, 5, 1)
            return [dict(company_revenue=620, company_cogs=465, company_gross_profit=155,
                         company_gross_margin_pct=25, company_revenue_change_pct=106 if complete else None,
                         comparable=complete, prior_gross_profit=180, source_count=31,
                         current_days=31, prior_days=30 if complete else 0,
                         expected_current_days=(end-start).days, expected_prior_days=(start-prior).days)]
        repo = type('Repository', (), {'execute_approved_query': staticmethod(execute)})()
        agent = ReportAgent(None, SQLAnalyticsAgent(repo, inventory_only=False))
        result, raw, _ = await agent.generate_from_template(request('Monthly revenue report from Jan to May 2026'), source_mode='analytics')
        monthly = result.data['monthly_decisions']
        insights = result.data['insights']
        self.assertIn('1 of 5 reporting months fully evaluated', insights['decision_summary'])
        self.assertTrue(any('2026-05' in finding['text'] for finding in insights['findings']))
        self.assertTrue(any('Prior-month gross profit was 180 VND' in finding['text'] for finding in insights['findings']))
        self.assertTrue(any(action['title']=='Positive revenue with negative profit trend' for action in insights['actions']))
        self.assertEqual([m['period']['start'] for m in monthly], [f'2026-{m:02d}-01' for m in range(1,6)])
        self.assertEqual([d['triggered'] for d in monthly[-1]['decisions']], [False, False, True, False])
        self.assertIsNone(json.loads(raw)['decisions'][0]['triggered'])
        self.assertEqual(monthly[-1]['metrics'][0]['evidence'][0]['filters']['period'], monthly[-1]['period'])
        self.assertIn((date(2026,1,1), date(2026,2,1), date(2025,12,1)), calls)
        from core.agents.report.document import ReportDocument
        document = ReportDocument(report=json.loads(raw), monthly_decisions=monthly)
        import tempfile
        from core.agents.report.store import ReportStore
        with tempfile.TemporaryDirectory() as directory:
            store = ReportStore(directory)
            saved = store.create('monthly-owner', document)
            self.assertEqual(store.get('monthly-owner', saved.id).monthly_decisions, monthly)
            self.assertIsNone(store.get('different-owner', saved.id))
        import fitz
        from core.agents.report.export import export_pdf
        pdf = fitz.open(stream=export_pdf(document), filetype='pdf')
        copy = ''.join(page.get_text() for page in pdf)
        self.assertIn('2026-05', copy)
        self.assertIn('Company revenue month-over-month change (2026-05 vs 2026-04)', ' '.join(copy.split()))
        from core.agents.report.presentation import decision_text
        import unicodedata
        self.assertIn(decision_text(monthly[-1]['decisions'][2], monthly[-1]), unicodedata.normalize('NFKC',' '.join(copy.split())))
        self.assertNotIn(monthly[-1]['metrics'][0]['evidence'][0]['query_id'], copy)
        changed = document.model_dump()
        changed['monthly_decisions'][-1]['decisions'][2]['triggered'] = False
        with self.assertRaises(ValueError): ReportDocument.model_validate(changed)
        changed = document.model_dump()
        changed['monthly_decisions'].pop(0)
        with self.assertRaises(ValueError): ReportDocument.model_validate(changed)
        changed = document.model_dump()
        changed['monthly_decisions'][0]['coverage']['current_days'] = '<img src=x>'
        with self.assertRaises(ValueError): ReportDocument.model_validate(changed)
        changed = document.model_dump()
        changed['monthly_decisions'][0]['comparison']['comparable'] = 'true'
        with self.assertRaises(ValueError): ReportDocument.model_validate(changed)
        repo.execute_approved_query = AsyncMock(return_value=[])
        for text in ('Monthly revenue report May 2026 by category', 'Monthly revenue report from Jan to May 2026 by category'):
            result, _, _ = await agent.generate_from_template(request(text), source_mode='analytics')
            for item in result.data['monthly_decisions']:
                self.assertIsNone(item['comparison']['prior_gross_profit'])
                self.assertTrue(all(v is None for v in item['coverage'].values()))
                self.assertTrue(all(m['value'] is None and not m['evidence'] for m in item['metrics']))
        repo.execute_approved_query.reset_mock()
        with self.assertRaisesRegex(ValueError, '200 calendar months'):
            await agent.generate_from_template(request('Monthly revenue report from Jan 1900 to Dec 2099'), source_mode='analytics')
        repo.execute_approved_query.assert_not_awaited()

    async def test_omitted_sources_infer_analytics_and_explicit_documents_are_preserved(self):
        repo = type('Repository', (), {'execute_approved_query': AsyncMock(return_value=[])})()
        agent = ReportAgent(None, SQLAnalyticsAgent(repo, inventory_only=False))
        for text in ('Sales report last month', 'Revenue report this quarter', 'Sales report May'):
            _, raw, media = await agent.generate_from_template(request(text))
            self.assertEqual(media, 'application/json')
            self.assertEqual(json.loads(raw)['report_type'], 'sales_performance')
        agent.analytics_agent.sales_report_latest = AsyncMock(side_effect=AssertionError('Unnecessary latest lookup'))
        _, raw, _ = await agent.generate_from_template(request("Sales report May 2026 for region 'Latest'"))
        self.assertEqual(json.loads(raw)['request']['dimension_value'], 'Latest')
        agent.analytics_agent.sales_report_latest.assert_not_awaited()
        repo.execute_approved_query.reset_mock()
        with self.assertRaises(PermissionError):
            await agent.generate_from_template(request(), source_mode='documents')
        repo.execute_approved_query.assert_not_awaited()

    async def test_missing_sources_and_authorization(self):
        repo = type('Repository', (), {'execute_approved_query': AsyncMock(side_effect=ConnectionError())})()
        agent = ReportAgent(None, SQLAnalyticsAgent(repo, inventory_only=False))
        with self.assertRaises(PermissionError):
            await agent.generate_from_template(request(authorized=False), source_mode='analytics')
        repo.execute_approved_query.assert_not_awaited()
        result, raw, media = await agent.generate_from_template(request(), source_mode='analytics')
        report = json.loads(raw)
        self.assertEqual(media, 'application/json')
        self.assertEqual(result.metadata['status'], 'partial')
        self.assertTrue(all(m['value'] is None and m['status'] == 'not_available' for m in report['metrics']))
        self.assertTrue(all(d['triggered'] is None for d in report['decisions']))
        self.assertEqual(len(report['dashboard']['widgets']), 6)
        validate_report(report)

    async def test_inventory_scope_cannot_be_bypassed(self):
        repo = type('Repository', (), {'execute_approved_query': AsyncMock()})()
        agent = ReportAgent(None, SQLAnalyticsAgent(repo, inventory_only=True))
        _, raw, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertTrue(all(m['value'] is None for m in json.loads(raw)['metrics']))
        repo.execute_approved_query.assert_not_awaited()

    def test_plans_validate_and_filters_are_parameters(self):
        for dimension in load_contract()['supported_request']['dimensions']:
            scope = parse_request('Monthly revenue report May 2026')
            scope.update(dimension=dimension, dimension_value='1' if dimension == 'product' else "x' OR TRUE --" if dimension != 'all' else None)
            for name, plan in plans(scope).items():
                if plan:
                    sql, args = plan
                    validate_commerce_sql(sql)
                    self.assertNotIn("x' OR TRUE", sql)
                    if len(args) == 3 and name not in {'company', 'monthly_company'}:
                        self.assertEqual(args[-1], 1 if dimension == 'product' else "x' OR TRUE --")

    async def test_both_apis_return_json_and_enforce_rbac(self):
        import jwt
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from app.agents import router
        from core.agents.main import create_app
        secret = 'sales-test-secret-with-at-least-32-characters'
        for production in (False, True):
            repo = type('Repository', (), {'execute_approved_query': AsyncMock(return_value=[])})()
            agent = ReportAgent(None, SQLAnalyticsAgent(repo, inventory_only=False))
            if production:
                app = FastAPI(); app.include_router(router)
                app.state.agent_router = type('Runtime', (), {'report_agent': agent})()
                path = '/api/agents/report'
            else:
                app = create_app(chat_agent=object(), report_agent=agent, identity_resolver=lambda _: request().identity)
                path = '/api/report'
            token = jwt.encode({'sub': 'sales-test', 'role': 'finance_analyst', 'exp': 4102444800}, secret, algorithm='HS256')
            with patch.dict(os.environ, {'AUTH_SECRET_KEY': secret}), patch('app.agents._record_agent_run'), TestClient(app) as client:
                response = client.post(path, data={'question': request().question, 'source_mode': 'analytics'}, headers={'Authorization': 'Bearer ' + token})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(list(response.json()['sections']), load_contract()['sections'])
                self.assertEqual(response.headers['content-type'], 'application/json')
                self.assertEqual(response.headers['cache-control'], 'no-store')
                if production:
                    denied = jwt.encode({'sub': 'employee', 'role': 'employee', 'exp': 4102444800}, secret, algorithm='HS256')
                    response = client.post(path, data={'question': request().question, 'source_mode': 'analytics'}, headers={'Authorization': 'Bearer ' + denied})
                    self.assertEqual(response.status_code, 403)


@unittest.skipUnless(os.getenv('SALES_REPORT_TEST_URL'), 'Opt-in read-only PostgreSQL fixture connection required')
class SalesSQLAccuracyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncpg
        self.connection = await asyncpg.connect(os.environ['SALES_REPORT_TEST_URL'], timeout=15)
        self.lock = asyncio.Lock()
        self.missing_day = self.empty = self.zero = self.empty_delivered_order = self.fail_widget = False
        test = self
        class Repository:
            async def execute_approved_query(self, sql, *args):
                validate_commerce_sql(sql)
                if test.fail_widget and 'GROUP BY' in sql and 'discount_amount' in sql:
                    raise ConnectionError('Fixture widget failure')
                return await test.execute_fixture(sql, *args)
        self.agent = ReportAgent(None, SQLAnalyticsAgent(Repository(), inventory_only=False))

    async def asyncTearDown(self):
        await self.connection.close()

    async def execute_fixture(self, sql, *args):
        sales = []
        for start, days, revenue, cogs in ((date(2026, 4, 1), 30, 10, 4), (date(2026, 5, 1), 31, 20, 15)):
            for offset in range(days):
                if self.missing_day and offset == 8 or self.empty:
                    continue
                sales.append(f"(DATE '{start + timedelta(days=offset)}', {0 if self.zero else revenue}::numeric, {cogs}::numeric)")
        fixtures = {
            'sales': ('date,revenue,cogs', ','.join(sales) if sales else '(NULL::date,NULL::numeric,NULL::numeric)'),
            'orders': ('order_id,order_date,order_status,zip,order_source', "(1,DATE '2026-05-01','delivered','a','web'),(2,DATE '2026-05-02','pending',NULL,'store')"),
            'order_items': ('order_item_id,order_id,product_id,quantity,unit_price,discount_amount', '(1,1,1,2,50::numeric,5::numeric),(2,1,2,1,20::numeric,0::numeric),(3,2,1,1,100::numeric,10::numeric)'),
            'products': ('product_id,product_name,category', "(1,'One','A'),(2,'Two','B')"),
            'geography': ('zip,region', "('a','North')"),
            'web_traffic': ('date,sessions', "(DATE '2026-05-01',0)")}
        definitions = []
        if self.empty_delivered_order:
            columns, values = fixtures['orders']
            fixtures['orders'] = (columns, values + ",(3,DATE '2026-05-03','delivered','a','web')")
        for table, (columns, values) in fixtures.items():
            if 'commerce.' + table in sql:
                name = 'fixture_' + table
                definitions.append(f'{name} ({columns}) AS (VALUES {values})')
                sql = sql.replace('commerce.' + table, name)
        prefix = 'WITH ' + ','.join(definitions) + (' ,' if sql.lstrip().upper().startswith('WITH ') else ' ')
        if sql.lstrip().upper().startswith('WITH '):
            sql = sql.lstrip()[5:]
        async with self.lock:
            async with self.connection.transaction(readonly=True):
                return [dict(row) for row in await self.connection.fetch(prefix + sql, *args)]

    async def test_metric_formulas_and_decisions(self):
        _, payload, _ = await self.agent.generate_from_template(request(), source_mode='analytics')
        report = json.loads(payload)
        values = {m['id']: m['value'] for m in report['metrics']}
        self.assertEqual(values['company_revenue'], 620)
        self.assertEqual(values['company_cogs'], 465)
        self.assertEqual(values['company_gross_profit'], 155)
        self.assertEqual(values['company_gross_margin_pct'], 25)
        self.assertAlmostEqual(values['company_revenue_change_pct'], 100 * (620 - 300) / 300)
        self.assertEqual(values['order_count'], 2)
        self.assertEqual(values['delivered_line_revenue'], 115)
        self.assertEqual(values['delivered_average_order_value'], 115)
        self.assertEqual(values['promotion_discount'], 15)
        self.assertEqual(values['sessions'], 0)
        self.assertEqual([d['triggered'] for d in report['decisions']], [False, False, True, False])
        self.assertFalse(report['data_quality']['partial_period'])
        self.assertEqual(report['dashboard']['widgets'][1]['data'][0]['company_revenue'], 620)
        validate_report(report)

    async def test_requested_range_has_independent_monthly_decisions(self):
        result, raw, _ = await self.agent.generate_from_template(request('Monthly revenue report from Jan to May 2026'), source_mode='analytics')
        self.assertIsNone(json.loads(raw)['decisions'][0]['triggered'])
        monthly = result.data['monthly_decisions']
        self.assertEqual(len(monthly), 5)
        self.assertTrue(all(d['triggered'] is None for d in monthly[0]['decisions']))
        self.assertEqual([d['triggered'] for d in monthly[3]['decisions']], [None, False, None, None])
        self.assertEqual([d['triggered'] for d in monthly[4]['decisions']], [False, False, True, False])
        self.assertEqual(monthly[4]['coverage'], {'current_days':31, 'expected_current_days':31, 'prior_days':30, 'expected_prior_days':30})

    async def test_missing_days_zero_denominator_and_empty_period(self):
        for mode in ('missing_day', 'zero', 'empty'):
            self.missing_day = mode == 'missing_day'; self.zero = mode == 'zero'; self.empty = mode == 'empty'
            _, payload, _ = await self.agent.generate_from_template(request(), source_mode='analytics')
            report = json.loads(payload)
            metrics = {m['id']: m for m in report['metrics']}
            if mode == 'zero':
                self.assertEqual(metrics['company_revenue']['value'], 0)
                self.assertIsNone(metrics['company_gross_margin_pct']['value'])
            else:
                self.assertIsNone(metrics['company_revenue_change_pct']['value'])
                self.assertIsNone(report['decisions'][0]['triggered'])
                self.assertIsNone(report['decisions'][3]['triggered'])
            if mode == 'empty':
                self.assertIsNone(metrics['company_revenue']['value'])
                self.assertEqual(metrics['company_revenue']['status'], 'no_data')

    async def test_period_structure_and_dashboard_are_immutable(self):
        reports = []
        for text in ('Monthly revenue report May 2026', 'Monthly revenue report July 2026', 'Monthly revenue report 2026'):
            _, raw, _ = await self.agent.generate_from_template(request(text), source_mode='analytics')
            report = json.loads(raw); validate_report(report); reports.append(report)
        for report in reports[1:]:
            self.assertEqual(list(report), list(reports[0]))
            self.assertEqual(list(report['sections']), list(reports[0]['sections']))
            self.assertEqual([{k:v for k,v in w.items() if k != 'data'} for w in report['dashboard']['widgets']],
                             [{k:v for k,v in w.items() if k != 'data'} for w in reports[0]['dashboard']['widgets']])
        changed = deepcopy(reports[0]); changed['sections']['executive_summary']['revenue_overview'] = 'Promotions caused growth.'
        with self.assertRaises(ValueError): validate_report(changed)

    async def test_year_scope_defaults_to_monthly_chart_observations(self):
        from core.agents.report.presentation import calendar_rows, comparison_metrics
        result, raw, _ = await self.agent.generate_from_template(request('sales performance in 2026'), source_mode='analytics')
        report = json.loads(raw)
        self.assertEqual(report['request']['granularity'], 'month')
        trend = next(w for w in report['dashboard']['widgets'] if w['id'] == 'sales_trend')
        self.assertEqual(trend['data'], [
            {'period':'2026-04-01', 'company_revenue':300, 'company_gross_profit':180},
            {'period':'2026-05-01', 'company_revenue':620, 'company_gross_profit':155}])
        rows = calendar_rows(trend, report['request'])
        self.assertEqual(len(rows), 12)
        self.assertIsNone(rows[0]['company_revenue'])
        self.assertEqual(sum(row['company_revenue'] or 0 for row in rows), 920)
        self.assertEqual(len(result.data['monthly_decisions']), 12)
        shown = {m['id']:m for m in comparison_metrics(report, result.data['monthly_decisions'])}
        self.assertEqual(shown['company_revenue']['value'], 920)
        self.assertAlmostEqual(shown['company_revenue_change_pct']['value'], 100*(620-300)/300)
        self.assertIn('2026-05 vs 2026-04', shown['company_revenue_change_pct']['label'])
        self.assertIsNone(next(m for m in report['metrics'] if m['id']=='company_revenue_change_pct')['value'])
        incomplete = deepcopy(result.data['monthly_decisions'])
        incomplete[4]['coverage']['current_days'] = 1
        next(m for m in incomplete[4]['metrics'] if m['id']=='company_revenue_change_pct').update(value=None, status='not_available')
        shown = {m['id']:m for m in comparison_metrics(report, incomplete)}
        self.assertIn('2026-05 vs 2026-04', shown['company_revenue_change_pct']['label'])
        self.assertIsNone(shown['company_revenue_change_pct']['value'])

    async def test_dimensions_preserve_source_definitions(self):
        _, raw, _ = await self.agent.generate_from_template(request('Monthly revenue report May 2026 by category'), source_mode='analytics')
        report = json.loads(raw); metrics = {m['id']: m for m in report['metrics']}
        self.assertEqual(metrics['company_revenue']['status'], 'not_available')
        self.assertEqual(metrics['order_count']['status'], 'not_available')
        self.assertEqual(metrics['delivered_line_revenue']['value'], 115)
        self.assertEqual(report['dashboard']['widgets'][3]['data'], [{'dimension': 'A', 'delivered_line_revenue': 95}, {'dimension': 'B', 'delivered_line_revenue': 20}])

    async def test_delivered_orders_without_items_stay_in_all_scope_aov_denominator(self):
        self.empty_delivered_order = True
        _, raw, _ = await self.agent.generate_from_template(request(), source_mode='analytics')
        metrics = {m['id']: m['value'] for m in json.loads(raw)['metrics']}
        self.assertEqual(metrics['order_count'], 3)
        self.assertEqual(metrics['delivered_line_revenue'], 115)
        self.assertEqual(metrics['delivered_average_order_value'], 57.5)
        _, raw, _ = await self.agent.generate_from_template(request('Monthly revenue report May 2026 by category'), source_mode='analytics')
        metrics = {m['id']: m['value'] for m in json.loads(raw)['metrics']}
        self.assertEqual(metrics['delivered_average_order_value'], 115)

    async def test_widget_failure_marks_report_partial_even_with_available_metrics(self):
        self.fail_widget = True
        result, raw, _ = await self.agent.generate_from_template(request(), source_mode='analytics')
        report = json.loads(raw)
        self.assertEqual(result.metadata['status'], 'partial')
        self.assertTrue(all(m['status'] == 'available' for m in report['metrics']))
        self.assertEqual(report['dashboard']['widgets'][4]['data'], [])


if __name__ == '__main__': unittest.main()
