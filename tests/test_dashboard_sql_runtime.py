import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from pydantic import ValidationError
from core.dashboards.generation import SQLResponse

from core.agents.sql.agent import SQLAnalyticsAgent
from core.dashboards.sql_runtime import DashboardSQLAgent
from core.models.agents import AgentRequest, VerifiedIdentity


class DashboardSQLRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_sql_is_reported_before_misleading_output_mapping(self):
        agent = DashboardSQLAgent(SimpleNamespace(), llm=SimpleNamespace(), inventory_only=False)
        agent._question, agent._responses, agent._clarifications = 'Product observations and summary', [], []
        from core.analytics.sql_validation import SQLValidationError
        with self.assertRaisesRegex(SQLValidationError, 'Exactly one SELECT'):
            await agent._response(json.dumps({'sql': 'SELECT p.product_id FROM commerce.products p LIMIT 1; SELECT p.category FROM commerce.products p LIMIT 1',
                'parameters': [], 'outputs': [{'kind': 'table', 'query': 0},
                                            {'kind': 'summary', 'query': 1, 'measures': ['products']}]}))

    async def test_separate_dashboard_builds_reuse_main_provider_and_cooldowns(self):
        from core.dashboards.agent import DashboardDocumentAgent
        provider = SimpleNamespace(generate=Mock(return_value=json.dumps({
            'sql': 'SELECT SUM(s.revenue) AS revenue FROM commerce.sales s LIMIT 1', 'parameters': [],
            'outputs': [{'kind': 'kpi', 'query': 0, 'measures': ['revenue']}]})))
        main = SQLAnalyticsAgent(SimpleNamespace(execute_approved_query=AsyncMock(return_value=[{'revenue': 3}])),
                                 inventory_only=False)
        def factory(agent):
            if agent.llm is None:
                agent.llm = provider
            return agent.llm
        request = AgentRequest(question='Revenue KPI', identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}))
        with patch.object(SQLAnalyticsAgent, '_provider', factory):
            for _ in range(2):
                result = await DashboardDocumentAgent(main).build(request, 'Revenue KPI')
                self.assertEqual('complete', result.status)
        self.assertIs(provider, main.llm)
        self.assertEqual(2, provider.generate.call_count)

    async def test_unverified_metric_results_cannot_be_displayed_on_refresh(self):
        agent = DashboardSQLAgent(SimpleNamespace(), llm=SimpleNamespace(), inventory_only=False)
        request = AgentRequest(question='Revenue', identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}),
                               metadata={'_dashboard_request': True})
        result = {'ok': True, 'query_status': 'executed', 'rows': [{'revenue': 3}],
                  'metadata': {'metric_validation': {'status': 'unverified'}}}
        with patch.object(SQLAnalyticsAgent, '_run_payload', AsyncMock(return_value=result)):
            response = await agent.run_payload(request)
        self.assertFalse(response.get('ok'), response)
        self.assertEqual([], response['rows'])

    async def test_unverified_sql_fallback_is_not_executed_for_a_dashboard(self):
        from core.analytics.sql_validation import QueryPlan, APPROVED_COLUMNS
        repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[{'value': 3}]), execute_unverified_query=AsyncMock(return_value=[{'value': 3}]))
        agent = DashboardSQLAgent(repo, llm=SimpleNamespace(), inventory_only=False)
        result = await agent._execute_plan(QueryPlan(sql='SELECT s.revenue AS value FROM commerce.sales s LIMIT 1'), {},
            APPROVED_COLUMNS, (), {}, (), allow_unverified=True)
        self.assertFalse(result.get('ok'), result)
        repo.execute_approved_query.assert_not_called()
        repo.execute_unverified_query.assert_not_called()

    async def test_missing_requested_representation_repairs_before_any_query_executes(self):
        value = {'sql': "SELECT DATE_TRUNC('month', w.date) AS month, SUM(w.sessions) AS sessions, SUM(w.page_views) AS page_views FROM commerce.web_traffic w GROUP BY 1 LIMIT 200",
                 'parameters': [], 'explanation': 'monthly',
                 'outputs': [{'kind': 'bar', 'query': 0, 'dimension': 'month', 'measures': ['sessions']}]}
        repaired = {**value, 'outputs': [*value['outputs'],
                    {'kind': 'line', 'query': 0, 'dimension': 'month', 'measures': ['page_views']}]}
        provider = SimpleNamespace(generate=Mock(side_effect=[json.dumps(value), json.dumps(repaired)]))
        repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[{'month': '2026-01-01', 'sessions': 3, 'page_views': 5}]))
        agent = DashboardSQLAgent(repo, llm=provider, inventory_only=False)
        request = AgentRequest(question='A bar chart of monthly sessions and a line chart of page views',
                               identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}),
                               metadata={'_dashboard_request': True, '_dashboard_allow_multiple': True})
        result = await agent.run_payload(request)
        self.assertTrue(result.get('ok'), result)
        self.assertEqual(2, provider.generate.call_count)
        repo.execute_approved_query.assert_awaited_once()

    def test_output_contract_rejects_missing_outputs_and_invalid_chart_or_kpi_shape(self):
        with self.assertRaises(ValidationError):
            SQLResponse.model_validate({'clarification': None, 'queries': []})
        for output in (
            {'kind': 'line', 'query': 0, 'dimension': 'month', 'measures': list('abcde'), 'group_by': []},
            {'kind': 'kpi', 'query': 0, 'dimension': 'revenue', 'measures': ['revenue'], 'group_by': []},
        ):
            with self.subTest(output=output), self.assertRaises(ValidationError):
                SQLResponse.model_validate({'result': {'operation': 'sql', 'sql': 'SELECT 1 LIMIT 1',
                    'parameters': [], 'explanation': 'test', 'outputs': [output]}})

    async def test_catalog_count_does_not_require_an_inventory_snapshot(self):
        response = {'clarification': None, 'interpretation': None,
                    'count_query': {'source': 'commerce.products', 'counts': [
                        {'alias': 'product_count', 'kind': 'distinct', 'field': 'product_id'}],
                        'dimensions': ['category'], 'time': {'mode': 'all'}},
                    'outputs': [{'kind': 'bar', 'query': 0, 'dimension': 'category', 'measures': ['product_count']},
                                {'kind': 'table', 'query': 0, 'measures': ['category', 'product_count']}]}
        provider = SimpleNamespace(generate=Mock(return_value=json.dumps(response)))
        repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[{'category': 'A', 'product_count': 3}]))
        agent = DashboardSQLAgent(repo, llm=provider, inventory_only=False)
        request = AgentRequest(question='Number of distinct products in each category, bar chart and table',
                               identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}),
                               metadata={'_dashboard_request': True, '_dashboard_allow_multiple': True})
        result = await agent.run_payload(request)
        self.assertTrue(result.get('ok'), result)
        self.assertEqual('commerce.products', result['metadata']['count_query']['source'])
        provider.generate.assert_called_once()
        self.assertNotIn('snapshot', repo.execute_approved_query.call_args.args[0])

    def test_general_sql_prompt_is_identical_to_main(self):
        agent = DashboardSQLAgent(SimpleNamespace(), llm=SimpleNamespace(), inventory_only=False)
        prompt = 'General SQL generation with schema and dashboard output instructions.'
        self.assertTrue(agent._prompt(prompt).startswith(prompt))
        self.assertNotIn('count_query', agent._prompt(prompt))

    async def test_parallel_datasets_do_not_share_repair_state_or_modify_main_provider(self):
        async def generate(prompt):
            await asyncio.sleep(0)
            source = 'commerce.customers' if 'Count rows in commerce.customers' in prompt else 'commerce.products'
            return json.dumps({'count_query': {'source': source, 'counts': [{'alias': 'observations', 'kind': 'rows'}],
                                               'time': {'mode': 'all'}},
                               'outputs': [{'kind': 'kpi', 'query': 0, 'measures': ['observations']}]})

        provider = SimpleNamespace(generate=generate)
        repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[{'observations': 3}]))
        main = SQLAnalyticsAgent(repo, llm=provider, inventory_only=False)
        extension = DashboardSQLAgent.from_agent(main)
        requests = [AgentRequest(question='Count rows in ' + source,
                                 identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}),
                                 metadata={'_dashboard_request': True, '_dashboard_allow_multiple': True})
                    for source in ('commerce.products', 'commerce.customers')]
        results = await asyncio.gather(*(extension.run_payload(request) for request in requests))
        self.assertEqual(['commerce.products', 'commerce.customers'],
                         [result['metadata']['count_query']['source'] for result in results])
        self.assertIs(generate, provider.generate)
        self.assertIs(SQLAnalyticsAgent, type(main))
        self.assertFalse(hasattr(main, '_responses'))
        self.assertFalse(hasattr(extension, '_responses'))
        self.assertEqual(2, repo.execute_approved_query.await_count)
