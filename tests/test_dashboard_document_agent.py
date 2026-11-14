import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from core.dashboards.agent import DashboardDocumentAgent
from core.models.agents import AgentRequest, VerifiedIdentity


class DashboardAgentTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.plan = {'title': 'Sales', 'queries': [{'id': 'sales', 'question': 'Monthly revenue July through September 2026 from commerce.sales'}],
                     'tiles': [{'id': 'trend', 'title': 'Revenue trend', 'kind': 'line', 'query_id': 'sales'}]}
        self.provider = SimpleNamespace(generate=Mock(return_value=json.dumps(self.plan)))
        self.sql = SimpleNamespace(inventory_only=False,
            repository=SimpleNamespace(get_schema=AsyncMock(return_value={'tables': {'commerce.sales': {'date', 'revenue'}}})),
            _provider=lambda: self.provider,
            run_payload=AsyncMock(return_value={'ok': True, 'query_status': 'executed',
                'rows': [{'month': '2026-07-01', 'revenue': 10}, {'month': '2026-08-01', 'revenue': 20}],
                'sql': "SELECT DATE_TRUNC('month', date) AS month, SUM(revenue) AS revenue FROM commerce.sales GROUP BY 1"}))
        self.agent = DashboardDocumentAgent(self.sql)
        self.request = AgentRequest(question='Dashboard', identity=VerifiedIdentity(subject='alice', permissions={'analytics:read'}))

    async def test_uses_verified_sql_for_each_dataset(self):
        doc = await self.agent.build(self.request, 'Revenue dashboard July through September 2026')
        self.assertEqual('complete', doc.status)
        self.assertEqual(1, len(doc.results))
        child = self.sql.run_payload.call_args.args[0]
        self.assertEqual(self.request.identity, child.identity)
        self.assertEqual({}, child.metadata)
        self.assertEqual(self.plan['queries'][0]['question'], child.question)

    async def test_failure_remains_explicit(self):
        self.sql.run_payload.return_value = {'ok': False, 'query_status': 'clarification_required', 'answer': 'Specify date'}
        doc = await self.agent.build(self.request, 'Sales dashboard')
        self.assertEqual('failed', doc.status)
        self.assertEqual('clarification_required', doc.results[0].status)
        self.assertEqual('Specify date', doc.results[0].message)

    async def test_sql_aliases_bind_without_changing_metric(self):
        self.plan['tiles'][0]['measures'] = ['total_revenue']
        self.provider.generate.return_value = json.dumps(self.plan)
        self.sql.run_payload.return_value['rows'] = [{'month': '2026-07-01', 'revenue': 10}]
        doc = await self.agent.build(self.request, 'Monthly revenue')
        self.assertEqual(['revenue'], doc.tiles[0].measures)
        doc.tiles[0].measures = ['profit']
        self.agent.bind_fields(doc)
        self.assertEqual(['profit'], doc.tiles[0].measures)

    async def test_invalid_plan_is_repaired_once(self):
        self.provider.generate.side_effect = ['{}', json.dumps(self.plan)]
        doc = await self.agent.build(self.request, 'Sales dashboard')
        self.assertEqual('Sales', doc.title)
        self.assertEqual(2, self.provider.generate.call_count)

    async def test_denial_before_schema_or_model(self):
        self.request.identity = None
        with self.assertRaises(PermissionError):
            await self.agent.build(self.request, 'Sales dashboard')
        self.sql.repository.get_schema.assert_not_called()
        self.provider.generate.assert_not_called()

    async def test_scope_edit_rewrites_questions_before_sql(self):
        doc = await self.agent.build(self.request, 'Sales dashboard July through September 2026')
        doc.scope = 'October through December 2026'
        self.provider.generate.return_value = json.dumps({'sales': 'Monthly revenue October through December 2026 from commerce.sales'})
        refreshed = await self.agent.refresh(self.request, doc, rescope=True)
        self.assertNotIn('July', refreshed.queries[0].question)
        self.assertIn('October', self.sql.run_payload.call_args.args[0].question)

    async def test_invalid_scope_edit_never_runs_sql(self):
        doc = await self.agent.build(self.request, 'Sales dashboard')
        self.sql.run_payload.reset_mock()
        self.provider.generate.return_value = '{"other":"Invent a metric"}'
        with self.assertRaises(ValueError):
            await self.agent.refresh(self.request, doc, rescope=True)
        self.sql.run_payload.assert_not_called()

    async def test_failed_query_preserves_attempted_sql(self):
        self.sql.run_payload.return_value = {'ok': False, 'query_status': 'error',
            'attempted_sql': 'SELECT SUM(revenue) FROM commerce.sales',
            'metadata': {'error_type': 'DataError'}}
        doc = await self.agent.build(self.request, 'Revenue dashboard')
        self.assertEqual('failed', doc.results[0].status)
        self.assertEqual('SELECT SUM(revenue) FROM commerce.sales', doc.results[0].payload['attempted_sql'])

    async def test_independent_summary_plan_is_repaired_before_sql(self):
        from copy import deepcopy
        bad = deepcopy(self.plan)
        bad['queries'].append({'id': 'stats', 'question': 'AVG MIN MAX raw revenue in July 2026'})
        bad['tiles'].append({'id': 'summary', 'title': 'Statistics', 'kind': 'summary', 'query_id': 'stats'})
        good = deepcopy(bad)
        good['tiles'][1]['query_id'] = 'sales'
        self.provider.generate.side_effect = [json.dumps(bad), json.dumps(good)]
        doc = await self.agent.build(self.request, 'Monthly revenue trend and statistical summary')
        self.assertEqual(1, len(doc.queries))
        self.assertEqual('sales', doc.tiles[1].query_id)
        self.sql.run_payload.assert_awaited_once()
        self.assertEqual('complete', doc.status)

    async def test_grouped_kpi_plan_is_rejected_before_sql(self):
        self.plan['tiles'].append({'id': 'kpi', 'title': 'Total', 'kind': 'kpi', 'query_id': 'sales'})
        self.provider.generate.return_value = json.dumps(self.plan)
        with self.assertRaises(ValueError):
            await self.agent.build(self.request, 'Monthly revenue and total')
        self.sql.run_payload.assert_not_called()

    async def test_8b_schema_echo_does_not_replace_plan_or_execute_trailing_sql(self):
        self.provider.generate.return_value = ('```json\n' + json.dumps(self.plan) + '\n```\n'
            '```json\n{"title":"DashboardPlan","type":"object"}\n```\n'
            '```sql\nDROP TABLE commerce.sales;\n```')
        doc = await self.agent.build(self.request, 'Monthly revenue dashboard')
        self.assertEqual('complete', doc.status)
        self.assertEqual(1, self.provider.generate.call_count)
        self.sql.run_payload.assert_awaited_once()
        self.assertEqual(self.plan['queries'][0]['question'], self.sql.run_payload.call_args.args[0].question)

    async def test_model_cannot_add_metric_authority_or_currency_to_queries(self):
        self.plan['queries'][0]['metric_definitions'] = {'revenue': {'unit': 'USD'}}
        self.provider.generate.return_value = json.dumps(self.plan)
        with self.assertRaises(ValueError):
            await self.agent.build(self.request, 'Revenue dashboard')
        self.sql.run_payload.assert_not_called()


if __name__ == '__main__':
    unittest.main()
