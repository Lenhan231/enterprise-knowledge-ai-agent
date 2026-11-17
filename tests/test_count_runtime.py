import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from core.dashboards.sql_runtime import DashboardSQLAgent as SQLAnalyticsAgent
from core.dashboards.agent import DashboardDocumentAgent
from core.models.agents import AgentRequest, VerifiedIdentity
from test_count_queries import count_query


QUESTION = 'Create an inventory dashboard showing SKU count and stockout and overstock flag counts for the latest available inventory snapshot.'


def response():
    query = count_query()
    return {'count_query': query, 'outputs': [
        {'kind': 'kpi', 'query': 0, 'measures': [c['alias']]} for c in query['counts']]}


class CountRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = SimpleNamespace(generate=Mock(return_value=json.dumps(response())))
        self.repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[
            {'snapshot_date': '2026-05-31', 'sku_count': 3, 'out_count': 2, 'over_count': 2}]))
        self.sql = SQLAnalyticsAgent(self.repo, llm=self.provider, inventory_only=False)
        self.agent = DashboardDocumentAgent(self.sql)
        self.request = AgentRequest(question=QUESTION, identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}))

    async def test_one_model_one_query_three_kpis(self):
        doc = await self.agent.build(self.request, QUESTION)
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(['kpi'] * 3, [tile.kind for tile in doc.tiles])
        self.assertEqual(1, len(doc.queries))
        self.assertEqual('latest', doc.results[0].payload['metadata']['count_query']['time']['mode'])
        self.assertNotIn('JOIN', self.repo.execute_approved_query.call_args.args[0])
        self.provider.generate.assert_called_once()
        self.repo.execute_approved_query.assert_awaited_once()

    async def test_raw_flag_mapping_is_repaired_not_sent_as_user_clarification(self):
        self.provider.generate.side_effect = [json.dumps({'metrics': ['observed_product_count', 'stockout_indicator', 'overstock_indicator'],
            'representation': 'aggregate', 'time': {'mode': 'latest'}}), json.dumps(response())]
        doc = await self.agent.build(self.request, QUESTION)
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(2, self.provider.generate.call_count)
        self.repo.execute_approved_query.assert_awaited_once()
        repair_prompt = self.provider.generate.call_args.args[0]
        self.assertIn('Return the count_query response schema only', repair_prompt)
        self.assertNotIn('Output schema for non-count inventory requests:', repair_prompt)

    async def test_legacy_latest_period_mapping_repairs_to_count_contract(self):
        value = response()
        value['count_query']['time'] = {'mode': 'latest', 'start': '2026-01-01', 'end': '2026-12-31'}
        self.provider.generate.side_effect = [json.dumps({
            'metrics': ['observed_product_count', 'stockout_indicator', 'overstock_indicator'],
            'representation': 'aggregate', 'time': {'mode': 'latest', 'start': '2026-01-01', 'end': '2026-12-31'}}),
            json.dumps(value)]
        doc = await self.agent.build(self.request, QUESTION, 'Jan to Dec 2026')
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(2, self.provider.generate.call_count)
        self.repo.execute_approved_query.assert_awaited_once()

    async def test_bad_count_contract_fails_after_one_repair_without_query(self):
        value = response()
        value['count_query']['joins'] = ['commerce.products']
        self.provider.generate.return_value = json.dumps(value)
        doc = await self.agent.build(self.request, QUESTION)
        self.assertEqual('failed', doc.results[0].status)
        self.assertEqual(2, self.provider.generate.call_count)
        self.assertNotIn('Stored product', doc.results[0].message)
        self.repo.execute_approved_query.assert_not_awaited()

    async def test_failed_flag_interpretation_is_not_a_clarification_question(self):
        self.provider.generate.return_value = json.dumps({'metrics': ['observed_product_count', 'stockout_indicator', 'overstock_indicator'],
            'representation': 'aggregate', 'time': {'mode': 'latest'}})
        doc = await self.agent.build(self.request, QUESTION)
        self.assertEqual('failed', doc.results[0].status)
        self.assertEqual('generation_failed', doc.results[0].payload['metadata']['status'])
        self.assertIn('Stored product values require product-level output', doc.results[0].message)
        self.assertIn('No dashboard data query was executed', doc.results[0].message)
        self.assertFalse(doc.results[0].payload['metadata']['clarification_required'])
        self.assertEqual(2, self.provider.generate.call_count)
        self.repo.execute_approved_query.assert_not_awaited()

    async def test_genuine_missing_snapshot_still_asks_specific_question(self):
        self.provider.generate.return_value = json.dumps({'metrics': ['observed_product_count']})
        doc = await self.agent.build(self.request, 'Count observed inventory products')
        self.assertEqual('clarification_required', doc.results[0].status)
        self.assertIn('snapshot', doc.results[0].message.lower())
        self.provider.generate.assert_called_once()
        self.repo.execute_approved_query.assert_not_awaited()

    async def test_absent_snapshot_is_unavailable_not_a_zero_inventory_claim(self):
        self.repo.execute_approved_query.return_value = [{'snapshot_date': None, 'sku_count': 0, 'out_count': 0, 'over_count': 0}]
        doc = await self.agent.build(self.request, QUESTION)
        self.assertEqual('failed', doc.results[0].status)
        self.assertEqual('unsupported', doc.results[0].payload['metadata']['status'])
        self.assertIn('No inventory snapshots', doc.results[0].message)
        self.assertEqual([], doc.results[0].payload['rows'])

    async def test_generic_counts_use_the_existing_sql_generation_call(self):
        value = {'count_query': {'source': 'commerce.orders', 'time': {'mode': 'all'},
                 'counts': [{'alias': 'order_count', 'kind': 'distinct', 'field': 'order_id'}]},
                 'outputs': [{'kind': 'kpi', 'query': 0, 'measures': ['order_count']}]}
        self.provider.generate.return_value = json.dumps(value)
        self.repo.execute_approved_query.return_value = [{'order_count': 5}]
        doc = await self.agent.build(self.request, 'Count all orders from commerce.orders')
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.provider.generate.assert_called_once()
        self.repo.execute_approved_query.assert_awaited_once()

    async def test_authentication_is_still_required_before_generation(self):
        with self.assertRaises(PermissionError):
            await self.agent.build(self.request.model_copy(update={'identity': None}), QUESTION)
        self.provider.generate.assert_not_called()
