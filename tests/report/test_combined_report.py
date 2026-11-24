import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import AsyncMock

from core.agents.report.agent import ReportAgent
from core.agents.sql.agent import SQLAnalyticsAgent
from core.models.agents import AgentRequest, VerifiedIdentity


class CombinedReportTest(unittest.IsolatedAsyncioTestCase):
    async def test_one_request_returns_both_validated_reports_in_the_requested_language(self):
        from core.agents.report.document import ReportDocument
        from core.agents.report.export import export_pdf
        import fitz

        repo = type('Repository', (), {'execute_approved_query': AsyncMock(return_value=[])})()
        agent = ReportAgent(None, SQLAnalyticsAgent(repo, inventory_only=False), llm=object())
        identity = VerifiedIdentity(subject='analyst', permissions={'analytics:read'})
        for question, vi in (
            ('Create an inventory report and sale performance report from January to October 2026', False),
            ('Tạo Inventory report và Sales performance từ tháng 1 đến tháng 10 2026', True),
            ('Tạo báo cáo tồn kho và kết quả bán hàng từ tháng 1 đến tháng 10 2026', True),
        ):
            with self.subTest(question=question):
                result, payload, media = await agent.generate_from_template(AgentRequest(question=question, identity=identity))
                report = json.loads(payload)
                self.assertEqual(media, 'application/json')
                self.assertEqual(report['report_type'], 'inventory_and_sales')
                self.assertEqual(set(report['reports']), {'inventory_operations', 'sales_performance'})
                for part in report['reports'].values():
                    self.assertEqual(part['request']['period'], {'start': '2026-01-01', 'end_exclusive': '2026-11-01'})
                self.assertEqual(result.metadata['status'], 'partial')
                self.assertEqual(len(result.data['monthly_decisions']), 10)
                saved = ReportDocument(report=report, monthly_decisions=result.data['monthly_decisions'])
                reopened = ReportDocument.model_validate_json(saved.model_dump_json())
                with fitz.open(stream=export_pdf(reopened), filetype='pdf') as pdf:
                    text = ' '.join(' '.join(page.get_text() for page in pdf).split())
                self.assertIn('Tổng quan vận hành' if vi else 'Operations Summary', text)
                self.assertIn('Tóm tắt điều hành' if vi else 'Executive Summary', text)
        calls = [call.args[0] for call in repo.execute_approved_query.await_args_list]
        self.assertTrue(any('commerce.inventory' in sql for sql in calls))
        self.assertTrue(any('commerce.sales' in sql for sql in calls))

    async def test_combined_report_clarifies_conflicting_periods_before_querying(self):
        repo = type('Repository', (), {'execute_approved_query': AsyncMock(return_value=[])})()
        agent = ReportAgent(None, SQLAnalyticsAgent(repo, inventory_only=False), llm=object())
        identity = VerifiedIdentity(subject='analyst', permissions={'analytics:read'})
        request = AgentRequest(question='Inventory report in May 2026 and sale performance in July 2026', identity=identity)
        result, payload, _ = await agent.generate_from_template(request)
        self.assertTrue(result.metadata['clarification_required'])
        self.assertIn('one shared reporting period', result.answer)
        self.assertFalse(payload)
        repo.execute_approved_query.assert_not_awaited()
        with self.assertRaises(PermissionError):
            await agent.generate_from_template(request.model_copy(update={'identity': None}))

    async def test_inventory_policy_mentioned_as_context_does_not_add_an_inventory_report(self):
        repo = type('Repository', (), {'execute_approved_query': AsyncMock(return_value=[])})()
        agent = ReportAgent(None, SQLAnalyticsAgent(repo, inventory_only=False), llm=object())
        request = AgentRequest(question='Create a sales performance report for May 2026 using inventory policy as context',
                               identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}))
        result, _, _ = await agent.generate_from_template(request)
        self.assertEqual(result.data['report']['report_type'], 'sales_performance')
        self.assertFalse(any('commerce.inventory' in call.args[0] for call in repo.execute_approved_query.await_args_list))

    async def test_saved_combined_report_rechecks_both_source_permissions_and_renders_both_parts(self):
        import os
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from unittest.mock import patch
        import jwt
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.reports import get_store, router
        from core.agents.report.store import ReportStore
        from core.models.agents import Evidence

        inventory = Evidence(source_type='document', source='04_Inventory_Control_and_Reorder_Planner.xlsx',
                             content='Verify stock levels before approving a reorder.', metadata={'document_id': 'inventory-policy'})
        sales = Evidence(source_type='document', source='Pricing review',
                         content='Pricing changes require approval and supporting sales evidence.', metadata={'document_id': 'sales-policy'})
        knowledge = SimpleNamespace(retrieve=AsyncMock(side_effect=lambda request:
            [inventory] if request.metadata.get('_policy_source_titles') else [sales]))
        repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[]))
        agent = ReportAgent(knowledge, SQLAnalyticsAgent(repo, inventory_only=False), llm=object())
        app = FastAPI()
        app.include_router(router)
        app.state.agent_router = SimpleNamespace(report_agent=agent)
        secret = 'combined-report-test-secret-at-least-32-characters'
        headers = {'Authorization': 'Bearer ' + jwt.encode(
            {'sub': 'owner', 'role': 'finance_analyst', 'exp': 4102444800}, secret, algorithm='HS256')}
        with TemporaryDirectory() as directory, patch.dict(os.environ, {'AUTH_SECRET_KEY': secret}):
            app.dependency_overrides[get_store] = lambda: ReportStore(directory)
            with TestClient(app) as client, patch('app.reports._accessible_document_ids', return_value={'inventory-policy', 'sales-policy'}) as access:
                response = client.post('/api/reports', headers=headers, json={'question': 'Inventory and sales performance report May 2026'})
                self.assertEqual(response.status_code, 201, response.text)
                document = response.json()['document']
                url = '/api/reports/' + document['id']
                access.assert_called_once_with(['inventory-policy', 'sales-policy'], ['finance_analyst'])
                access.return_value = {'inventory-policy'}
                reopened = client.get(url, headers=headers)
                self.assertEqual(reopened.status_code, 200, reopened.text)
                self.assertIn(inventory.content, reopened.text)
                self.assertNotIn(sales.content, reopened.text)
                edited = client.put(url, headers=headers, json={
                    'title': 'Inventory and sales review', 'revision': document['revision'],
                    'presentation': document['presentation'],
                })
                self.assertEqual(edited.status_code, 200, edited.text)
                self.assertEqual(edited.json()['document']['title'], 'Inventory and sales review')
                download = client.get(url + '/pdf', headers=headers)
                self.assertEqual(download.status_code, 200)
                import fitz
                with fitz.open(stream=download.content, filetype='pdf') as pdf:
                    text = ' '.join(' '.join(page.get_text() for page in pdf).split())
                self.assertIn(inventory.content, text)
                self.assertNotIn(sales.content, text)

        script = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute() {}
}
const element = tag => new Element(tag);
const document = {createElement: element, createElementNS: (_,tag) => element(tag)};
const render = vm.runInNewContext(fs.readFileSync('src/app/static/sales-report.js','utf8')+';SalesPerformanceReport.render', {document,Intl});
const saved = JSON.parse(fs.readFileSync(0, 'utf8')), root = element('div');
render(root, saved.report, {insights:saved.insights, monthly_decisions:saved.monthly_decisions, inventory_context:saved.inventory_context});
assert.deepEqual(root.children.filter(n=>n.dataset.reportType).map(n=>n.dataset.reportType), ['inventory_operations','sales_performance']);
const text = el => [el.textContent || '', ...el.children.flatMap(text)];
const copy = text(root).join(' ');
assert.match(copy, /Operations Summary/);
assert.match(copy, /Executive Summary/);
"""
        browser = subprocess.run(['node', '-e', script], input=json.dumps(document),
                                 capture_output=True, text=True, encoding='utf-8', cwd=Path(__file__).resolve().parents[2])
        self.assertEqual(browser.returncode, 0, browser.stderr)
