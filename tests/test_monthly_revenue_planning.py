import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.sql_agent.agent import SQLAnalyticsAgent, _monthly_revenue_plan
from core.models.agents import AgentRequest, VerifiedIdentity


class MonthlyRevenuePlanningTest(unittest.IsolatedAsyncioTestCase):
    def test_compiler_does_not_drop_filters_or_discrete_periods(self):
        for question in ['monthly revenue during 2026 above 1000', 'monthly revenue during 2026 > 1000',
                         'monthly revenue for July and September 2026', 'monthly revenue for Streetwear during 2026',
                         'monthly revenue during 2026 1000', 'monthly revenue for last year']:
            with self.subTest(question=question):
                self.assertIsNone(_monthly_revenue_plan(question, {'revenue'}))

    async def test_clear_monthly_revenue_compiles_without_sql_model(self):
        provider, repository = Mock(), AsyncMock()
        provider.generate.side_effect = AssertionError('No SQL generation is needed for this checked shape')
        repository.execute_approved_query.return_value = [{'month':'2026-07-01','revenue':10}]
        agent = SQLAnalyticsAgent(repository,llm=provider)
        with patch.object(agent,'_check_ambiguity',return_value={
                'choice':'clear','probabilities':{'clear':.95,'ambiguous':.05}}):
            result = await agent.run_payload(AgentRequest(
                question='Create a donut chart for monthly revenue from July to September in 2026',
                identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['metadata']['request_contract']['columns'],['month','revenue'])
        provider.generate.assert_not_called()
        query,*parameters = repository.execute_approved_query.await_args.args
        self.assertIn("DATE_TRUNC('MONTH'",query.upper())
        self.assertEqual([str(p) for p in parameters],['2026-07-01','2026-10-01'])

    async def test_inventory_mapping_can_repair_once_before_execution(self):
        provider, repository = Mock(), AsyncMock()
        provider.generate.side_effect = [json.dumps({'metrics':['observed_product_count'], 'unknown_slot':True}),
            json.dumps({'metrics':['observed_product_count'], 'dimensions':[],
                'time':{'mode':'snapshot','start':'2026-05-31'}})]
        repository.execute_approved_query.return_value = [{'snapshot_date':'2026-05-31','observed_product_count':3}]
        agent=SQLAnalyticsAgent(repository,llm=provider)
        with patch.object(agent,'_check_ambiguity',return_value={
                'choice':'clear','probabilities':{'clear':.95,'ambiguous':.05}}):
            result=await agent.run_payload(AgentRequest(question='Count observed inventory products at 2026-05-31',
                identity=VerifiedIdentity(subject='test',permissions={'analytics:read'})))
        self.assertTrue(result['ok'],result)
        self.assertEqual(provider.generate.call_count,2)
        repository.execute_approved_query.assert_awaited_once()
