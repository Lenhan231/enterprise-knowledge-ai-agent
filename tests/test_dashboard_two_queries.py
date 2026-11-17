"""Bounded independent datasets use one SQL generation, with no result arithmetic."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from core.agents.sql.agent import SQLAnalyticsAgent
from core.dashboards.agent import DashboardDocumentAgent
from core.models.agents import AgentRequest, VerifiedIdentity


def plans():
    return [
        {'question': 'Total sessions from commerce.web_traffic',
         'sql': 'SELECT SUM(w.sessions) AS sessions FROM commerce.web_traffic w WHERE w.date >= $1 AND w.date < $2 LIMIT 1',
         'parameters': ['2026-01-01', '2027-01-01']},
        {'question': 'Monthly sessions from commerce.web_traffic',
         'sql': "SELECT DATE_TRUNC('month', w.date) AS month, SUM(w.sessions) AS sessions FROM commerce.web_traffic w WHERE w.date >= $1 AND w.date < $2 GROUP BY 1 ORDER BY 1 LIMIT 200",
         'parameters': ['2026-01-01', '2027-01-01']},
    ]


def outputs(measure='sessions'):
    return [{'kind': 'kpi', 'query': 0, 'measures': ['sessions']},
            {'kind': 'line', 'query': 1, 'dimension': 'month', 'measures': [measure]}]


class TwoQueryDashboardTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = SimpleNamespace(generate=Mock(return_value=json.dumps({'queries': plans(), 'outputs': outputs()})))
        self.repo = SimpleNamespace(execute_approved_query=AsyncMock(side_effect=[
            [{'sessions': 100}], [{'month': '2026-01-01', 'sessions': 30}, {'month': '2026-02-01', 'sessions': 70}]]))
        self.sql = SQLAnalyticsAgent(self.repo, llm=self.provider, inventory_only=False)
        self.agent = DashboardDocumentAgent(self.sql)
        self.request = AgentRequest(question='Dashboard', identity=VerifiedIdentity(subject='alice', permissions={'analytics:read'}))
        self.description = 'Total sessions and monthly session trends from commerce.web_traffic'
        self.scope = '2026-01-01 through 2026-12-31'

    async def build(self):
        return await self.agent.build(self.request, self.description, self.scope)

    async def test_two_grains_one_generation_separate_tiles_and_refresh(self):
        doc = await self.build()
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(['q0', 'q1'], [q.id for q in doc.queries])
        self.assertEqual(['kpi', 'line'], [t.kind for t in doc.tiles])
        self.assertEqual(['q0', 'q1'], [t.query_id for t in doc.tiles])
        self.assertEqual(2, len({t.id for t in doc.tiles}))
        self.assertEqual(100, doc.results[0].payload['rows'][0]['sessions'])
        self.provider.generate.assert_called_once()
        self.assertEqual(2, self.repo.execute_approved_query.await_count)
        self.assertEqual(self.scope, doc.scope)
        # Refresh each saved intent through the unchanged single-query response format.
        self.provider.generate.side_effect = [json.dumps(p) for p in plans()]
        self.repo.execute_approved_query.side_effect = [[{'sessions': 101}], [{'month': '2026-01-01', 'sessions': 101}]]
        refreshed = await self.agent.refresh(self.request, doc)
        self.assertEqual(['q0', 'q1'], [q.id for q in refreshed.queries])
        self.assertEqual(3, self.provider.generate.call_count)
        for call in self.provider.generate.call_args_list[1:]:
            self.assertNotIn('Independent dashboard queries', call.args[0])

    async def test_chart_dimension_repeated_in_grouping_needs_no_repair(self):
        declared = outputs()
        declared[1]['group_by'] = [declared[1]['dimension']]
        self.provider.generate.return_value = json.dumps({'queries': plans(), 'outputs': declared})
        doc = await self.build()
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(['kpi', 'line'], [tile.kind for tile in doc.tiles])
        self.assertEqual([], doc.results[1].payload['metadata']['dashboard_outputs'][0]['group_by'])
        self.provider.generate.assert_called_once()
        self.assertEqual(2, self.repo.execute_approved_query.await_count)

    async def test_missing_summary_preserves_valid_total_and_observation_queries_without_repair(self):
        self.description += ', with a statistical summary and the underlying observation table'
        declared = outputs() + [{'kind': 'table', 'query': 1, 'measures': ['month', 'sessions']}]
        self.provider.generate.return_value = json.dumps({'queries': plans(), 'outputs': declared})
        self.repo.execute_approved_query.side_effect = [
            [{'sessions': 111}], [{'month': '2026-01-01', 'sessions': 30}, {'month': '2026-02-01', 'sessions': 70}]]
        doc = await self.build()
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(['kpi', 'line', 'table', 'summary'], [tile.kind for tile in doc.tiles])
        self.assertEqual(['q0', 'q1', 'q1', 'q1'], [tile.query_id for tile in doc.tiles])
        self.assertEqual(111, doc.results[0].payload['rows'][0]['sessions'])
        self.provider.generate.assert_called_once()
        self.assertEqual(2, self.repo.execute_approved_query.await_count)

    def test_underlying_observation_table_is_an_explicit_representation(self):
        from core.dashboards.requirements import requested_kinds
        self.assertEqual({'summary', 'table'}, requested_kinds(
            'Monthly sessions, a statistical summary, and the underlying observation table'))
        self.assertNotIn('table', requested_kinds('Monthly sessions from the web traffic table'))

    async def test_database_failure_keeps_other_result_and_provenance(self):
        self.repo.execute_approved_query.side_effect = [RuntimeError('private database detail'), [{'month': '2026-01-01', 'sessions': 5}, {'month': '2026-02-01', 'sessions': 6}]]
        doc = await self.build()
        self.assertEqual('partial', doc.status)
        self.assertEqual(['failed', 'complete'], [r.status for r in doc.results])
        self.assertIn('web_traffic', doc.results[0].payload['attempted_sql'])
        self.assertNotIn('private database detail', doc.results[0].message)
        self.provider.generate.assert_called_once()

    async def test_bad_bundle_never_executes_either_query(self):
        for kind in ('duplicate_third', 'write', 'private', 'period', 'conflict', 'metric', 'duplicate', 'reference'):
            with self.subTest(kind=kind):
                items = plans()
                if kind == 'duplicate_third':
                    items.append(dict(items[0], question='Another sessions total'))
                elif kind == 'write':
                    items[1]['sql'] = 'DELETE FROM commerce.web_traffic'
                elif kind == 'private':
                    items[1]['sql'] = 'SELECT password FROM private.users LIMIT 1'
                elif kind == 'period':
                    items[1]['parameters'][1] = '2026-06-01'
                elif kind == 'conflict':
                    items[1]['question'] += ' in 2025'
                elif kind == 'metric':
                    items[1]['sql'] = items[1]['sql'].replace('SUM(w.sessions)', 'AVG(w.sessions)')
                elif kind == 'duplicate':
                    items[1] = items[0]
                else:
                    items[1]['depends_on'] = 'q0'
                self.provider.generate.return_value = json.dumps({'queries': items, 'outputs': outputs()})
                doc = await self.build()
                self.assertEqual('failed', doc.results[0].status)
                self.repo.execute_approved_query.assert_not_awaited()

    async def test_bundle_not_enabled_for_ordinary_sql_call(self):
        result = await self.sql.run_payload(self.request.model_copy(update={'question': self.description}))
        self.assertFalse(result['ok'])
        self.repo.execute_approved_query.assert_not_awaited()

    async def test_clarification_does_not_execute(self):
        self.provider.generate.return_value = json.dumps({'clarification': 'Which traffic source should be included?'})
        doc = await self.build()
        self.assertEqual('clarification_required', doc.results[0].status)
        self.repo.execute_approved_query.assert_not_awaited()

    async def test_single_response_still_uses_one_query(self):
        self.provider.generate.return_value = json.dumps({**plans()[0], 'outputs': [outputs()[0]]})
        doc = await self.agent.build(self.request, 'Total sessions from commerce.web_traffic', self.scope)
        self.assertEqual('complete', doc.status)
        self.assertEqual(['q0'], [q.id for q in doc.queries])
        self.assertEqual(['output0'], [t.id for t in doc.tiles])
        self.provider.generate.assert_called_once()
        self.repo.execute_approved_query.assert_awaited_once()

    async def test_missing_requested_metric_rejects_entire_bundle(self):
        doc = await self.agent.build(self.request, self.description + ' and total revenue from commerce.sales', self.scope)
        self.assertEqual('failed', doc.results[0].status)
        self.repo.execute_approved_query.assert_not_awaited()

    async def test_independent_existing_sources_keep_metrics_separate(self):
        items = plans()
        items[1]['question'] = 'Monthly revenue from commerce.sales'
        items[1]['sql'] = items[1]['sql'].replace('commerce.web_traffic', 'commerce.sales').replace('w.sessions', 'w.revenue').replace('AS sessions', 'AS revenue')
        self.provider.generate.return_value = json.dumps({'queries': items, 'outputs': outputs('revenue')})
        self.repo.execute_approved_query.side_effect = [
            [{'sessions': 100}], [{'month': '2026-01-01', 'revenue': 2}, {'month': '2026-02-01', 'revenue': 3}]]
        doc = await self.agent.build(self.request, 'Total sessions from commerce.web_traffic and monthly revenue from commerce.sales', self.scope)
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual([['sessions'], ['revenue']], [tile.measures for tile in doc.tiles])
        self.assertEqual([['commerce.web_traffic'], ['commerce.sales']], [r.payload['metadata']['source'] for r in doc.results])
        self.assertEqual(['executed', 'executed'], [r.payload['metadata']['execution_status'] for r in doc.results])
        self.assertEqual({'sessions': 100}, doc.results[0].payload['rows'][0])
        self.provider.generate.assert_called_once()
