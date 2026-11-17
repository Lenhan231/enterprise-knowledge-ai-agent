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

    async def test_missing_outputs_after_count_repair_is_generation_failure_not_user_clarification(self):
        value = response()
        value.pop('outputs')
        self.provider.generate.return_value = json.dumps(value)
        doc = await self.agent.build(self.request, QUESTION + ' with KPI tiles')
        self.assertEqual('failed', doc.results[0].status)
        self.assertEqual('generation_failed', doc.results[0].payload['metadata']['status'])
        self.assertFalse(doc.results[0].payload['metadata']['clarification_required'])
        self.assertIn('did not provide any dashboard outputs', doc.results[0].message)
        self.assertEqual(2, self.provider.generate.call_count)
        self.repo.execute_approved_query.assert_not_awaited()

    def test_inventory_count_contract_also_applies_when_main_selects_sql_generation(self):
        from core.analytics.sql_validation import APPROVED_COLUMNS
        from core.dashboards.generation import CountResponseFormat
        from core.llm.groq_provider import GroqProvider
        self.sql._question = 'Count distinct SKUs with stockout_flag=true and reorder_flag=true by category at the latest snapshot'
        self.sql._columns, self.sql._dates = APPROVED_COLUMNS, ()
        self.sql._clarifications = []
        prompt = self.sql._prompt('Generate one read-only PostgreSQL SELECT')
        self.assertIn('Interpret this structural count request', prompt)
        self.assertIn('Declare each requested grouping field in dimensions', prompt)
        provider = GroqProvider(api_keys=['test'])
        try:
            options = self.sql._options(provider, 'Generate one read-only PostgreSQL SELECT', {})
        finally:
            provider.close()
        self.assertEqual(CountResponseFormat.model_json_schema()['title'], options['response_schema']['title'])

    async def test_grouped_count_output_repair_preserves_the_validated_data_plan(self):
        value = response()
        value['count_query']['dimensions'] = ['category']
        measures = [c['alias'] for c in value['count_query']['counts']]
        repaired = {'outputs': [{'kind': 'bar', 'query': 0, 'dimension': 'category', 'measures': measures}]}
        self.provider.generate.side_effect = [json.dumps(value), json.dumps(repaired)]
        self.repo.execute_approved_query.return_value[0]['category'] = 'A'
        doc = await self.agent.build(self.request, QUESTION + ' for each category with a bar chart')
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(['category'], doc.results[0].payload['metadata']['count_query']['dimensions'])
        self.assertEqual(['bar'], [t.kind for t in doc.tiles])
        self.assertIn('Repair only the outputs', self.provider.generate.call_args.args[0])
        self.assertEqual(2, self.provider.generate.call_count)
        self.repo.execute_approved_query.assert_awaited_once()

    async def test_count_output_positions_are_not_dataset_indices(self):
        value = response()
        value['count_query']['dimensions'] = ['category']
        value['outputs'] = [
            {'kind': 'bar', 'query': 0, 'dimension': 'category', 'measures': ['out_count']},
            {'kind': 'bar', 'query': 1, 'dimension': 'category', 'measures': ['over_count']}]
        for repaired_index in (0, 1):
            with self.subTest(repaired_index=repaired_index):
                repaired = json.loads(json.dumps({'outputs': value['outputs']}))
                repaired['outputs'][1]['query'] = repaired_index
                self.provider.generate.side_effect = [json.dumps(value), json.dumps(repaired)]
                self.repo.execute_approved_query.reset_mock()
                self.repo.execute_approved_query.return_value[0]['category'] = 'A'
                doc = await self.agent.build(self.request, QUESTION + ' for each category with bar charts')
                if repaired_index == 0:
                    self.assertEqual('complete', doc.status, [r.message for r in doc.results])
                    self.assertEqual(['q0', 'q0'], [t.query_id for t in doc.tiles])
                    self.repo.execute_approved_query.assert_awaited_once()
                    self.assertIn('Every output must use query: 0', self.provider.generate.call_args.args[0])
                else:
                    self.assertEqual('failed', doc.status)
                    self.assertIn('dataset index 1', doc.results[0].message)
                    self.assertIn('available dataset indices: [0]', doc.results[0].message)
                    self.assertNotIn('within 3', doc.results[0].message)
                    self.repo.execute_approved_query.assert_not_awaited()

    async def test_output_repair_cannot_silently_remove_an_explicit_kpi_request(self):
        value = response()
        value['count_query']['dimensions'] = ['category']
        self.provider.generate.side_effect = [json.dumps(value), json.dumps({'outputs': [
            {'kind': 'bar', 'query': 0, 'dimension': 'category', 'measures': ['out_count', 'over_count']}]})]
        doc = await self.agent.build(self.request, QUESTION + ' by category with an overall KPI')
        self.assertEqual('failed', doc.status)
        self.assertIn('omitted explicitly requested representations: kpi', doc.results[0].message)
        self.repo.execute_approved_query.assert_not_awaited()

    async def test_unrequested_invalid_kpis_do_not_block_a_valid_chart_of_the_same_counts(self):
        value = response()
        value['count_query']['dimensions'] = ['category']
        value['outputs'].append({'kind': 'bar', 'query': 0, 'dimension': 'category',
                                 'measures': [c['alias'] for c in value['count_query']['counts']]})
        self.provider.generate.return_value = json.dumps(value)
        self.repo.execute_approved_query.return_value[0]['category'] = 'A'
        doc = await self.agent.build(self.request, QUESTION + ' for each category')
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(['bar'], [t.kind for t in doc.tiles])
        self.provider.generate.assert_called_once()
        self.repo.execute_approved_query.assert_awaited_once()

    async def test_count_plan_cannot_omit_an_explicit_grouping(self):
        for grouping in ('for each category', 'by category', 'per category', 'theo danh mục',
                         'per segment', 'by category and segment'):
            with self.subTest(grouping=grouping):
                self.provider.generate.reset_mock()
                self.provider.generate.return_value = json.dumps(response())
                self.repo.execute_approved_query.reset_mock()
                doc = await self.agent.build(self.request, QUESTION + ' ' + grouping)
                self.assertEqual('failed', doc.status)
                self.assertIn('omitted requested grouping', doc.results[0].message)
                self.repo.execute_approved_query.assert_not_awaited()

    async def test_count_presentation_defaults_need_no_model_outputs_or_output_repair(self):
        cases = [(['category'], 'latest', 'Counts for each category at latest inventory snapshot', 'bar'),
                 (['category', 'segment'], 'latest', 'Counts by category and segment at latest inventory snapshot', 'table'),
                 ([], 'history', 'Inventory counts across snapshots', 'line')]
        for dimensions, mode, question, kind in cases:
            with self.subTest(kind=kind):
                value = response()
                value.pop('outputs')
                value['count_query']['dimensions'] = dimensions
                value['count_query']['time']['mode'] = mode
                self.provider.generate.return_value = json.dumps(value)
                self.provider.generate.reset_mock()
                self.repo.execute_approved_query.return_value = [
                    {'snapshot_date': '2026-04-30', 'category': 'A', 'segment': 'B', 'sku_count': 3, 'out_count': 2, 'over_count': 2},
                    {'snapshot_date': '2026-05-31', 'category': 'C', 'segment': 'D', 'sku_count': 4, 'out_count': 1, 'over_count': 2}]
                doc = await self.agent.build(self.request, question)
                self.assertEqual('complete', doc.status, [r.message for r in doc.results])
                self.assertEqual([kind], [tile.kind for tile in doc.tiles])
                self.provider.generate.assert_called_once()

    def test_inventory_count_routing_does_not_capture_rates_other_metrics_or_cross_domain_requests(self):
        for question in ('Stockout rate by category at latest snapshot',
                         'SKU count and stock on hand at latest snapshot',
                         'Count stockout SKUs and show revenue in 2031',
                         'Count stockout SKUs from commerce.inventory and commerce.orders'):
            with self.subTest(question=question):
                self.sql._question = question
                self.assertFalse(self.sql._inventory_count_intent())

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
