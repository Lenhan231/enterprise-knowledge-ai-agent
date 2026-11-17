import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.agents.sql.agent import SQLAnalyticsAgent
from core.dashboards.agent import DashboardDocumentAgent
from core.dashboards.generation import SQLResponse
from core.models.agents import AgentRequest, VerifiedIdentity


def plan():
    period = ['2031-01-01', '2032-01-01']
    queries = [
        {'question': 'Monthly revenue in 2031', 'sql': "SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue FROM commerce.sales s WHERE s.date >= $1 AND s.date < $2 GROUP BY 1 ORDER BY 1 LIMIT 200", 'parameters': period, 'explanation': 'Monthly revenue'},
        {'question': 'Monthly sessions in 2031', 'sql': "SELECT DATE_TRUNC('month', w.date) AS month, SUM(w.sessions) AS sessions FROM commerce.web_traffic w WHERE w.date >= $1 AND w.date < $2 GROUP BY 1 ORDER BY 1 LIMIT 200", 'parameters': period, 'explanation': 'Monthly sessions'},
        {'question': 'Overall revenue KPI in 2031', 'sql': 'SELECT SUM(s.revenue) AS revenue FROM commerce.sales s WHERE s.date >= $1 AND s.date < $2 LIMIT 1', 'parameters': period, 'explanation': 'Overall revenue'},
    ]
    return {'queries': queries, 'outputs': [
        {'kind': 'line', 'query': 0, 'dimension': 'month', 'measures': ['revenue'], 'group_by': []},
        {'kind': 'line', 'query': 1, 'dimension': 'month', 'measures': ['sessions'], 'group_by': []},
        {'kind': 'kpi', 'query': 2, 'dimension': None, 'measures': ['revenue'], 'group_by': []}]}


class ThreeQueryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.value = plan()
        self.provider = SimpleNamespace(generate=Mock(side_effect=lambda prompt: json.dumps(self.value)))
        self.active, self.peak = 0, 0
        async def execute(sql, *parameters):
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                await asyncio.sleep(0.01)
                if 'GROUP BY' not in sql:
                    return [{'revenue': 41}]
                measure = 'sessions' if 'web_traffic' in sql else 'revenue'
                return [{'month': '2031-01-01', measure: 10}, {'month': '2031-02-01', measure: 20}]
            finally:
                self.active -= 1
        self.repo = SimpleNamespace(execute_approved_query=AsyncMock(side_effect=execute))
        self.agent = DashboardDocumentAgent(SQLAnalyticsAgent(self.repo, llm=self.provider, inventory_only=False))
        self.question = 'Tạo dashboard doanh thu và sessions theo từng tháng và tổng KPI doanh thu trong năm 2031'
        self.request = AgentRequest(question=self.question, identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}))
        self.selector = patch('core.agents.sql.agent.select_jev_schema_tables', side_effect=RuntimeError('Use schema fallback in tests'))
        self.selector.start()
        self.addCleanup(self.selector.stop)

    async def test_three_datasets_share_one_generation_and_keep_separate_grains(self):
        doc = await self.agent.build(self.request, self.question)
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(['q0', 'q1', 'q2'], [r.id for r in doc.results])
        self.assertEqual(['line', 'line', 'kpi'], [t.kind for t in doc.tiles])
        self.assertEqual(41, doc.results[2].payload['rows'][0]['revenue'])
        self.provider.generate.assert_called_once()
        prompt = self.provider.generate.call_args.args[0]
        self.assertNotIn('then join the CTEs on those complete grouped keys', prompt)
        self.assertIn('different fact sources use separate datasets', prompt)
        self.assertIn('"end_exclusive": "2032-01-01"', prompt)
        self.assertEqual(3, self.repo.execute_approved_query.await_count)
        self.assertLessEqual(self.peak, 2)
        # Saved intents retain their period; refresh still uses at most two concurrent queries.
        self.peak = 0
        self.provider.generate.side_effect = [json.dumps(q) for q in self.value['queries']]
        refreshed = await self.agent.refresh(self.request, doc)
        self.assertEqual('complete', refreshed.status)
        self.assertEqual(2, self.peak)

    def test_structured_contract_accepts_three_queries_and_the_third_output(self):
        SQLResponse.model_validate({'result': {'operation': 'queries', **self.value}})

    async def test_invalid_third_query_never_executes_any_query_and_retains_the_reason(self):
        variants = [
            lambda p: p['queries'][2].update(sql='DELETE FROM commerce.sales'),
            lambda p: p['queries'][2].update(parameters=['2031-01-01', '2031-06-01']),
            lambda p: p['queries'][2].update(depends_on='q0'),
            lambda p: p['queries'].append(deepcopy(p['queries'][0])),
            lambda p: p['queries'].__setitem__(2, deepcopy(p['queries'][0])),
            lambda p: p['queries'][2].update(question='Overall order count in 2031'),
            lambda p: p.update(parameters=['2031-01-01', '2032-01-01']),
        ]
        for change in variants:
            with self.subTest(change=change):
                self.value = plan()
                change(self.value)
                self.provider.generate.reset_mock()
                self.repo.execute_approved_query.reset_mock()
                doc = await self.agent.build(self.request, self.question)
                self.assertEqual('failed', doc.status)
                self.repo.execute_approved_query.assert_not_awaited()
                self.assertNotIn('The dashboard plan could not be validated after repair.', doc.results[0].message)
                self.assertTrue(doc.results[0].payload.get('metadata', {}).get('error_detail'))

    async def test_grouped_rows_cannot_supply_an_overall_kpi_and_failure_explains_why(self):
        self.value['queries'].pop()
        self.value['outputs'][2]['query'] = 0
        doc = await self.agent.build(self.request, self.question)
        self.assertEqual('failed', doc.status)
        self.assertIn('overall KPI', doc.results[0].message)
        self.assertNotIn('The dashboard plan could not be validated after repair.', doc.results[0].message)
        self.assertFalse(doc.results[0].payload['metadata']['clarification_required'])
        self.repo.execute_approved_query.assert_not_awaited()

    async def test_subquestion_cannot_lose_the_confirmed_period_on_refresh(self):
        self.value['queries'][0]['question'] = 'Monthly revenue'
        doc = await self.agent.build(self.request, self.question)
        self.assertEqual('failed', doc.status)
        self.repo.execute_approved_query.assert_not_awaited()
