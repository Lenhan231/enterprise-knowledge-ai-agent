import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.agents.sql.agent import SQLAnalyticsAgent
from core.analytics.sql_validation import APPROVED_COLUMNS
from core.dashboards.sql_runtime import DashboardSQLAgent
from core.models.agents import AgentRequest, VerifiedIdentity


class InventoryScopeTest(unittest.IsolatedAsyncioTestCase):
    def request(self, question):
        return AgentRequest(question=question, identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}),
            metadata={'_dashboard_request': True, '_dashboard_allow_multiple': True})

    async def test_vietnamese_bounded_latest_reaches_unchanged_sql_validator(self):
        from core.dashboards.agent import DashboardDocumentAgent
        selected = '2024-05-17'
        value = {'domain': 'inventory', 'metrics': ['stockout_rate'], 'dimensions': ['category'],
                 'filters': [], 'time': {'mode': 'snapshot', 'start': selected},
                 'representation': 'aggregate', 'outputs': [
                     {'kind': 'bar', 'query': 0, 'dimension': 'category', 'measures': ['stockout_rate']},
                     {'kind': 'table', 'query': 0, 'measures': ['snapshot_date', 'category', 'stockout_rate']}]}
        provider = SimpleNamespace(generate=Mock(return_value=json.dumps(value)))
        repo = SimpleNamespace(execute_approved_query=AsyncMock(side_effect=[
            [{'snapshot_date': selected}],
            [{'snapshot_date': selected, 'category': 'A', 'stockout_rate': 0.25},
             {'snapshot_date': selected, 'category': 'B', 'stockout_rate': 0.5}]]))
        question = 'So sánh stockout_rate theo danh mục tại snapshot mới nhất có trong năm 2024. Hiển thị biểu đồ cột và bảng số liệu.'
        selection = {'tables': set(APPROVED_COLUMNS), 'required_tables': {'commerce.inventory', 'commerce.products'}, 'candidate_tables': set(APPROVED_COLUMNS)}
        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value=selection):
            doc = await DashboardDocumentAgent(SQLAnalyticsAgent(repo, llm=provider, inventory_only=False)).build(self.request(question), question)
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(['bar', 'table'], [tile.kind for tile in doc.tiles])
        self.assertEqual(question, doc.description)
        self.assertEqual(selected, doc.results[0].payload['metadata']['dashboard_snapshot_scope']['snapshot_date'])
        provider.generate.assert_called_once()
        self.assertEqual(2, repo.execute_approved_query.await_count)
        self.assertIn('stockout_rate', repo.execute_approved_query.call_args.args[0])

    async def test_latest_within_requested_period_is_resolved_before_main_interpretation(self):
        for period, selected, bounds in [('2031', '2031-09-04', ('2031-01-01', '2032-01-01')),
                                        ('Q2 2024', '2024-05-17', ('2024-04-01', '2024-07-01'))]:
            repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[{'snapshot_date': selected}]))
            agent = DashboardSQLAgent(repo, llm=SimpleNamespace(), inventory_only=False)
            question = 'Compare stockout_rate by category at the latest available inventory snapshot within ' + period
            context = {}
            with patch.object(SQLAnalyticsAgent, '_run_payload', AsyncMock(return_value={'ok': True, 'rows': []})) as run:
                result = await agent._run_payload(self.request(question), context, APPROVED_COLUMNS, (), {}, ())
            self.assertTrue(result['ok'])
            self.assertIn(selected, run.call_args.args[0].question)
            self.assertNotIn('latest', run.call_args.args[0].question)
            self.assertEqual(question, context['dashboard_snapshot_scope']['requested_question'])
            self.assertEqual(selected, context['dashboard_snapshot_scope']['snapshot_date'])
            self.assertEqual(bounds, tuple(map(str, repo.execute_approved_query.call_args.args[1:])))
            self.assertNotIn('category', repo.execute_approved_query.call_args.args[0])

    async def test_no_snapshot_or_out_of_period_snapshot_never_calls_the_model(self):
        for selected in (None, '2023-12-31'):
            repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[{'snapshot_date': selected}]))
            agent = DashboardSQLAgent(repo, llm=SimpleNamespace(), inventory_only=False)
            with patch.object(SQLAnalyticsAgent, '_run_payload', AsyncMock()) as run:
                result = await agent._run_payload(self.request('stockout_rate at latest snapshot within 2024'), {}, APPROVED_COLUMNS, (), {}, ())
            self.assertFalse(result.get('ok'))
            self.assertEqual('unsupported', result['metadata']['status'])
            self.assertEqual('unsupported', result['query_status'])
            self.assertFalse(result['metadata']['clarification_required'])
            run.assert_not_called()

    async def test_unbounded_latest_and_noninventory_requests_keep_main_path(self):
        for question in ('stockout_rate at latest snapshot', 'Revenue during 2024'):
            repo = SimpleNamespace(execute_approved_query=AsyncMock())
            agent = DashboardSQLAgent(repo, llm=SimpleNamespace(), inventory_only=False)
            with patch.object(SQLAnalyticsAgent, '_run_payload', AsyncMock(return_value={'ok': True})):
                await agent._run_payload(self.request(question), {}, APPROVED_COLUMNS, (), {}, ())
            repo.execute_approved_query.assert_not_called()

    def test_inventory_prompt_preserves_answered_slots_and_requested_metrics(self):
        agent = DashboardSQLAgent(SimpleNamespace(), llm=SimpleNamespace(), inventory_only=False)
        agent._columns, agent._dates = APPROVED_COLUMNS, ()
        agent._question = 'Compare stockout_rate by category at snapshot 2031-09-04 with a bar chart and table'
        agent._clarifications = [{'question': 'Which measure for the table?', 'reply': 'stockout_rate'},
                                 {'question': 'Which grouping?', 'reply': 'for each category'}]
        prompt = agent._prompt('Catalog candidates (selection summaries only):')
        self.assertIn(json.dumps(agent._clarifications), prompt)
        self.assertIn('requested_metrics', prompt)
        self.assertIn('stockout_rate', prompt)
        repaired = agent._prompt('Repair the inventory time without changing its metrics', inventory_repair=True)
        self.assertIn('flat inventory interpretation', repaired)
        self.assertNotIn('Generate one or two independent', repaired)
