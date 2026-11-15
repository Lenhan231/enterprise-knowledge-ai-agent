import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from core.agents.sql.agent import SQLAnalyticsAgent
from core.dashboards.agent import DashboardDocumentAgent
from core.models.agents import AgentRequest, VerifiedIdentity


def response():
    return {'queries': [
        {'question': 'Monthly revenue from commerce.sales in 2026',
         'sql': "SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue FROM commerce.sales s WHERE s.date >= $1 AND s.date < $2 GROUP BY 1 ORDER BY 1 LIMIT 200",
         'parameters': ['2026-01-01', '2027-01-01']},
        {'question': 'Total revenue from commerce.sales in 2026',
         'sql': 'SELECT SUM(s.revenue) AS revenue FROM commerce.sales s WHERE s.date >= $1 AND s.date < $2 LIMIT 1',
         'parameters': ['2026-01-01', '2027-01-01']}],
        'outputs': [
            {'kind': 'line', 'query': 0, 'dimension': 'month', 'measures': ['revenue']},
            {'kind': 'kpi', 'query': 1, 'measures': ['revenue']},
            {'kind': 'summary', 'query': 0, 'measures': ['revenue']}]}


class DashboardRequirementsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = SimpleNamespace(generate=Mock(return_value=json.dumps(response())))
        self.repo = SimpleNamespace(execute_approved_query=AsyncMock(side_effect=[
            [{'month': '2026-01-01', 'revenue': 10}, {'month': '2026-02-01', 'revenue': 20}], [{'revenue': 300}]]))
        self.agent = DashboardDocumentAgent(SQLAnalyticsAgent(self.repo, llm=self.provider, inventory_only=False))
        self.request = AgentRequest(question='Dashboard', identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}))

    async def build(self):
        return await self.agent.build(self.request, 'Monthly revenue in 2026, line chart, total revenue KPI and statistical summary')

    async def test_one_generation_covers_trend_total_and_summary_without_summing_chart_rows(self):
        doc = await self.build()
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertCountEqual(['line', 'kpi', 'summary'], [tile.kind for tile in doc.tiles])
        kpi = next(tile for tile in doc.tiles if tile.kind == 'kpi')
        self.assertEqual('q1', kpi.query_id)
        self.assertEqual(300, next(r for r in doc.results if r.id == kpi.query_id).payload['rows'][0]['revenue'])
        self.provider.generate.assert_called_once()
        self.assertEqual(2, self.repo.execute_approved_query.await_count)

    async def test_invalid_or_unsupported_requirements_never_execute(self):
        for defect in ('kpi_grain', 'missing_query', 'measure', 'grouped_summary', 'unsupported', 'too_many', 'missing_manifest', 'wrong_period'):
            with self.subTest(defect=defect):
                value = response()
                if defect == 'kpi_grain': value['outputs'][1]['query'] = 0
                elif defect == 'missing_query': value['outputs'][0]['query'] = 2
                elif defect == 'measure': value['outputs'][0]['measures'] = ['invented']
                elif defect == 'grouped_summary': value['outputs'][2]['group_by'] = ['month']
                elif defect == 'unsupported': value['outputs'][0]['kind'] = 'scatter'
                elif defect == 'too_many': value['outputs'] *= 3
                elif defect == 'missing_manifest': del value['outputs']
                else: value['queries'][1]['parameters'][1] = '2026-06-01'
                self.provider.generate.return_value = json.dumps(value)
                doc = await self.build()
                self.assertEqual('clarification_required', doc.results[0].status)
                self.repo.execute_approved_query.assert_not_awaited()

    async def test_summary_can_bind_a_measure_without_any_chart(self):
        query = response()['queries'][0]
        self.provider.generate.return_value = json.dumps({**query, 'outputs': [
            {'kind': 'table', 'query': 0}, {'kind': 'summary', 'query': 0, 'measures': ['revenue']}]})
        doc = await self.agent.build(self.request, 'Monthly revenue in 2026 as a table with descriptive statistics')
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(['table', 'summary'], [t.kind for t in doc.tiles])
        self.provider.generate.assert_called_once()

    async def test_same_output_contract_works_for_other_metrics_and_sources(self):
        for metric, source in [('sessions', 'commerce.web_traffic'), ('cogs', 'commerce.sales')]:
            with self.subTest(metric=metric):
                value = json.loads(json.dumps(response()).replace('revenue', metric).replace('commerce.sales', source))
                self.provider.generate.reset_mock()
                self.provider.generate.return_value = json.dumps(value)
                self.repo.execute_approved_query.reset_mock()
                self.repo.execute_approved_query.side_effect = [
                    [{'month': '2026-01-01', metric: 10}, {'month': '2026-02-01', metric: 20}], [{metric: 300}]]
                doc = await self.agent.build(self.request, f'Monthly {metric} in 2026, line chart, total {metric} KPI and statistical summary')
                self.assertEqual('complete', doc.status, [r.message for r in doc.results])
                self.assertCountEqual(['line', 'kpi', 'summary'], [tile.kind for tile in doc.tiles])
                self.provider.generate.assert_called_once()
                self.assertEqual(2, self.repo.execute_approved_query.await_count)

    async def test_invalid_mapping_can_be_repaired_before_any_execution(self):
        invalid = response()
        invalid['outputs'][1]['query'] = 0
        generated = []
        def generate(prompt):
            self.repo.execute_approved_query.assert_not_awaited()
            generated.append(prompt)
            return json.dumps(invalid if len(generated) == 1 else response())
        self.provider.generate.side_effect = generate
        doc = await self.build()
        self.assertEqual('complete', doc.status)
        self.assertEqual(2, len(generated))
        self.assertIn('overall aggregate query', generated[-1])
        self.assertEqual(2, self.repo.execute_approved_query.await_count)

    async def test_summary_can_use_a_returned_measure_that_has_no_chart(self):
        query = response()['queries'][0]
        query['sql'] = query['sql'].replace('AS revenue FROM', 'AS revenue, SUM(s.cogs) AS cogs FROM')
        self.provider.generate.return_value = json.dumps({**query, 'outputs': [
            {'kind': 'line', 'query': 0, 'dimension': 'month', 'measures': ['revenue']},
            {'kind': 'summary', 'query': 0, 'measures': ['cogs']}]})
        self.repo.execute_approved_query.side_effect = None
        self.repo.execute_approved_query.return_value = [
            {'month': '2026-01-01', 'revenue': 10, 'cogs': 3}, {'month': '2026-02-01', 'revenue': 20, 'cogs': 4}]
        doc = await self.agent.build(self.request, 'Monthly revenue in 2026 as a line chart and a statistical summary of monthly cogs')
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual([['revenue'], ['cogs']], [tile.measures for tile in doc.tiles])
        self.repo.execute_approved_query.assert_awaited_once()

    async def test_inventory_interpretation_declares_outputs_in_its_existing_call(self):
        mapping = {'metrics': ['stock_on_hand'], 'dimensions': ['category'],
                   'time': {'mode': 'snapshot', 'start': '2022-12-31'},
                   'outputs': [{'kind': 'bar', 'query': 0, 'dimension': 'category', 'measures': ['stock_on_hand']}]}
        self.provider.generate.return_value = json.dumps(mapping)
        self.repo.execute_approved_query.side_effect = None
        self.repo.execute_approved_query.return_value = [
            {'snapshot_date': '2022-12-31', 'category': 'A', 'stock_on_hand': 10},
            {'snapshot_date': '2022-12-31', 'category': 'B', 'stock_on_hand': 20}]
        doc = await self.agent.build(self.request, 'Stock on hand by category at snapshot 2022-12-31')
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(['bar'], [tile.kind for tile in doc.tiles])
        self.provider.generate.assert_called_once()
        self.repo.execute_approved_query.assert_awaited_once()

    async def test_table_can_select_grouping_columns_alongside_chart_measures(self):
        for dimension, measure in [('month', 'revenue'), ('period', 'value')]:
            with self.subTest(dimension=dimension, measure=measure):
                value = response()['queries'][0]
                value['sql'] = value['sql'].replace('AS month', 'AS ' + dimension).replace('AS revenue', 'AS ' + measure)
                value['parameters'] = ['2026-07-01', '2026-10-01']
                value['outputs'] = [
                    {'kind': 'line', 'query': 0, 'dimension': dimension, 'measures': [measure]},
                    {'kind': 'table', 'query': 0, 'measures': [dimension, measure]}]
                self.provider.generate.reset_mock()
                self.provider.generate.return_value = json.dumps(value)
                self.repo.execute_approved_query.side_effect = None
                self.repo.execute_approved_query.return_value = [
                    {dimension: '2026-07-01', measure: 10}, {dimension: '2026-09-01', measure: 20}]
                doc = await self.agent.build(self.request, 'Create a dashboard showing the monthly revenue trend and a table of the underlying monthly observations for July to September 2026.')
                self.assertEqual('complete', doc.status, [r.message for r in doc.results])
                self.assertEqual(['line', 'table'], [tile.kind for tile in doc.tiles])
                self.assertEqual([dimension, measure], doc.tiles[1].measures)
                self.provider.generate.assert_called_once()

    async def test_latest_inventory_chart_and_category_observation_table(self):
        mapping = {'metrics': ['stockout_rate'], 'dimensions': ['category'], 'time': {'mode': 'latest'},
            'outputs': [{'kind': 'bar', 'query': 0, 'dimension': 'category', 'measures': ['stockout_rate']},
                        {'kind': 'table', 'query': 0, 'measures': ['snapshot_date', 'category', 'stockout_rate']}]}
        self.provider.generate.return_value = json.dumps(mapping)
        self.repo.execute_approved_query.side_effect = None
        self.repo.execute_approved_query.return_value = [
            {'snapshot_date': '2022-12-31', 'category': 'A', 'stockout_rate': 0.2},
            {'snapshot_date': '2022-12-31', 'category': 'B', 'stockout_rate': 0.3}]
        doc = await self.agent.build(self.request, 'Compare stockout rates across product categories in the latest inventory snapshot and include a table of category-level observations.')
        self.assertEqual('complete', doc.status, [r.message for r in doc.results])
        self.assertEqual(['bar', 'table'], [tile.kind for tile in doc.tiles])
        self.provider.generate.assert_called_once()
        self.repo.execute_approved_query.assert_awaited_once()

    async def test_grouped_columns_remain_invalid_numeric_measures(self):
        for kind in ('line', 'kpi', 'summary'):
            with self.subTest(kind=kind):
                value = response()['queries'][0]
                value['outputs'] = [{'kind': kind, 'query': 0, 'measures': ['month']}]
                if kind == 'line':
                    value['outputs'][0]['dimension'] = 'month'
                self.provider.generate.return_value = json.dumps(value)
                doc = await self.agent.build(self.request, 'Monthly revenue in 2026')
                self.assertEqual('clarification_required', doc.results[0].status)
                self.repo.execute_approved_query.assert_not_awaited()
