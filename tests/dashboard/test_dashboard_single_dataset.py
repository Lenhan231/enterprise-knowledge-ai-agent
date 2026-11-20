import unittest
import json
import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.agents.dashboard.agent import DashboardDocumentAgent
from core.agents.dashboard.models import DashboardDocument
from core.agents.dashboard.render import render_dashboard
from core.models.agents import AgentRequest, VerifiedIdentity


class SingleDatasetDashboardTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = Mock(side_effect=AssertionError('Dashboard must not call a model'))
        self.sql = SimpleNamespace(
            _provider=self.provider,
            run_payload=AsyncMock(return_value={
                'ok': True, 'query_status': 'executed',
                'rows': [{'month': '2026-07-01', 'revenue': 10},
                         {'month': '2026-08-01', 'revenue': 20}],
                'sql': "SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue FROM commerce.sales s GROUP BY 1 LIMIT 200",
                'parameters': [], 'metadata': {'source': ['commerce.sales']},
                'evidence': [{'source': 'commerce.sales'}],
            }))
        self.agent = DashboardDocumentAgent(self.sql)
        self.request = AgentRequest(question='Dashboard', metadata={'category': 'ignore'},
                                    identity=VerifiedIdentity(subject='alice', permissions={'analytics:read'}))

    async def test_one_sql_request_builds_one_chart_without_unrequested_summary_or_table(self):
        description = 'Monthly revenue July through September 2026'
        doc = await self.agent.build(self.request, description)
        self.sql.run_payload.assert_awaited_once()
        self.provider.assert_not_called()
        child = self.sql.run_payload.call_args.args[0]
        self.assertEqual(description, child.question)
        self.assertEqual(self.request.identity, child.identity)
        self.assertEqual({'_dashboard_request': True, '_dashboard_allow_multiple': True, '_dashboard_scope': ''}, child.metadata)
        self.assertIsNone(child.conversation_id)
        self.assertEqual(['line'], [tile.kind for tile in doc.tiles])
        self.assertEqual({'q0'}, {tile.query_id for tile in doc.tiles})
        self.assertEqual('complete', doc.status)
        self.assertNotIn('mean 15', render_dashboard(doc))
        self.assertEqual(1, render_dashboard(doc).count('<table>'))
        self.assertEqual(self.sql.run_payload.return_value['evidence'], doc.results[0].payload['evidence'])

    async def test_chart_mapping_works_with_unrelated_sources_and_aliases(self):
        self.sql.run_payload.return_value.update(
            sql="SELECT DATE_TRUNC('month', a.created_at) AS period, SUM(a.net_amount) AS net_amount, SUM(a.units) AS units FROM analytics.activity a GROUP BY 1 LIMIT 200",
            rows=[{'period': '2026-01-01', 'net_amount': 15, 'units': 2},
                  {'period': '2026-02-01', 'net_amount': 30, 'units': 3}],
            metadata={'request_contract': {'columns': ['period', 'net_amount', 'units'], 'dimensions': ['period'],
                'chart_type': None, 'charts': [{'type': 'line', 'dimension': 'period', 'measures': ['net_amount']},
                                               {'type': 'bar', 'dimension': 'period', 'measures': ['units']}]}})
        doc = await self.agent.build(self.request, 'A line chart of net amount and a bar chart of units')
        self.assertEqual('complete', doc.status)
        self.assertEqual([['net_amount'], ['units']], [tile.measures for tile in doc.tiles])
        self.assertEqual(['line', 'bar'], [tile.kind for tile in doc.tiles])
        self.assertEqual(1, len(doc.queries))
        self.assertNotIn('Chart unavailable', render_dashboard(doc))
        self.provider.assert_not_called()

    async def test_single_aggregate_row_gets_separate_kpis_without_summing(self):
        self.sql.run_payload.return_value.update(
            sql='SELECT SUM(s.revenue) AS revenue, COUNT(*) AS observations FROM commerce.sales s LIMIT 1',
            rows=[{'revenue': 30, 'observations': 2}])
        doc = await self.agent.build(self.request, 'Total revenue and observation count')
        self.assertEqual(['kpi', 'kpi'], [tile.kind for tile in doc.tiles])
        self.assertEqual([['revenue'], ['observations']], [tile.measures for tile in doc.tiles])
        self.assertEqual(1, render_dashboard(doc).count('<table>'))

    async def test_one_group_is_not_an_overall_kpi(self):
        self.sql.run_payload.return_value['rows'] = [self.sql.run_payload.return_value['rows'][0]]
        doc = await self.agent.build(self.request, 'Monthly revenue')
        self.assertNotIn('kpi', [tile.kind for tile in doc.tiles])

    async def test_unprojected_group_is_not_mistaken_for_overall_kpi(self):
        self.sql.run_payload.return_value.update(
            sql='SELECT SUM(revenue) AS revenue FROM commerce.sales GROUP BY category LIMIT 1',
            rows=[{'revenue': 10}])
        doc = await self.agent.build(self.request, 'Revenue')
        self.assertEqual(['table'], [tile.kind for tile in doc.tiles])

    async def test_identifiers_and_raw_rows_are_not_kpis_or_summary_measures(self):
        self.sql.run_payload.return_value.update(sql='SELECT p.product_id, p.price FROM commerce.products p LIMIT 200',
                                                 rows=[{'product_id': 7, 'price': 40}])
        doc = await self.agent.build(self.request, 'Product details')
        self.assertEqual(['table'], [tile.kind for tile in doc.tiles])

    async def test_mixed_units_use_separate_charts_without_another_query(self):
        self.sql.run_payload.return_value.update(
            sql='SELECT category, AVG(rating) AS rating, COUNT(*) AS review_count FROM commerce.reviews GROUP BY 1 LIMIT 200',
            rows=[{'category': 'A', 'rating': 4, 'review_count': 10}],
            metadata={'metrics': {'rating': {'unit': 'score'}, 'review_count': {'unit': 'reviews'}}})
        doc = await self.agent.build(self.request, 'Rating and reviews by category')
        self.assertEqual(['bar', 'bar'], [tile.kind for tile in doc.tiles])
        self.assertEqual([['rating'], ['review_count']], [tile.measures for tile in doc.tiles])
        self.assertEqual('complete', doc.status)
        self.sql.run_payload.assert_awaited_once()
        self.provider.assert_not_called()

    async def test_explicit_ineligible_chart_retains_fallback_reason(self):
        self.sql.run_payload.return_value.update(
            sql='SELECT category, SUM(revenue) AS revenue FROM commerce.sales GROUP BY 1 LIMIT 200',
            rows=[{'category': 'A', 'revenue': 10}, {'category': 'B', 'revenue': 20}])
        doc = await self.agent.build(self.request, 'Line chart of revenue by category')
        self.assertEqual('failed', doc.status)
        self.assertIn('Chart unavailable', render_dashboard(doc))
        self.assertIn('<table>', render_dashboard(doc))

    async def test_empty_and_clarification_are_preserved_without_charts(self):
        for payload, status in [
            ({'ok': False, 'query_status': 'executed', 'rows': [], 'sql': 'SELECT 1 LIMIT 1'}, 'empty'),
            ({'ok': False, 'metadata': {'clarification_required': True}, 'answer': 'Specify dates'}, 'clarification_required'),
        ]:
            with self.subTest(status=status):
                self.sql.run_payload.return_value = payload
                doc = await self.agent.build(self.request, 'Revenue')
                self.assertEqual(status, doc.results[0].status)
                self.assertEqual(['table'], [tile.kind for tile in doc.tiles])
                self.assertNotIn('<svg', render_dashboard(doc))

    async def test_scope_refresh_reuses_question_and_preserves_presentation_without_model(self):
        doc = await self.agent.build(self.request, 'Monthly revenue', 'July 2026')
        doc.tiles[0].title = 'My trend'
        doc.scope = 'August 2026'
        self.sql.run_payload.reset_mock()
        refreshed = await self.agent.refresh(self.request, doc)
        self.sql.run_payload.assert_awaited_once()
        self.provider.assert_not_called()
        question = self.sql.run_payload.call_args.args[0].question
        self.assertIn('August 2026', question)
        self.assertNotIn('July 2026', question)
        self.assertEqual('My trend', refreshed.tiles[0].title)

    async def test_conflicting_scope_requires_explicit_description_edit_before_sql(self):
        with self.assertRaisesRegex(ValueError, 'description'):
            await self.agent.build(self.request, 'Revenue July 2026', 'August 2026')
        self.sql.run_payload.assert_not_called()
        self.provider.assert_not_called()

    async def test_full_description_is_not_truncated_to_old_query_limit(self):
        description = 'Monthly revenue ' + 'context ' * 180
        doc = await self.agent.build(self.request, description)
        self.assertEqual(description.strip(), doc.queries[0].question)
        DashboardDocument.model_validate_json(doc.model_dump_json())

    async def test_permission_denied_before_sql_or_model(self):
        self.request.identity = None
        with self.assertRaises(PermissionError):
            await self.agent.build(self.request, 'Revenue')
        self.sql.run_payload.assert_not_called()
        self.provider.assert_not_called()

    async def test_null_aggregate_is_unknown_and_never_zero(self):
        self.sql.run_payload.return_value.update(
            sql='SELECT SUM(revenue) AS revenue FROM commerce.sales LIMIT 1', rows=[{'revenue': None}])
        doc = await self.agent.build(self.request, 'Total revenue')
        self.assertEqual(['kpi'], [tile.kind for tile in doc.tiles])
        self.assertIn('No observed value', render_dashboard(doc))

    async def test_year_dimension_and_saved_numeric_strings_render_as_a_line(self):
        self.sql.run_payload.return_value.update(
            sql="SELECT EXTRACT(YEAR FROM s.date) AS year, SUM(s.revenue) AS revenue FROM commerce.sales s GROUP BY 1 LIMIT 200",
            rows=[{'year': Decimal('2025'), 'revenue': '10.25'}, {'year': Decimal('2026'), 'revenue': '20.75'}])
        doc = await self.agent.build(self.request, 'Revenue by year')
        self.assertEqual('line', doc.tiles[0].kind)
        self.assertEqual('year', doc.tiles[0].dimension)
        restored = DashboardDocument.model_validate_json(doc.model_dump_json())
        self.assertIn('<svg', render_dashboard(restored))
        self.assertNotIn('Chart unavailable', render_dashboard(restored))
        self.assertNotIn('mean 15.5', render_dashboard(restored))

    async def test_explicit_table_does_not_add_chart_or_kpis(self):
        doc = await self.agent.build(self.request, 'Table of monthly revenue')
        self.assertEqual(['table'], [tile.kind for tile in doc.tiles])

    async def test_naming_a_source_table_does_not_force_table_representation(self):
        doc = await self.agent.build(self.request, 'Monthly revenue from table commerce.sales')
        self.assertEqual(['line'], [tile.kind for tile in doc.tiles])

    async def test_source_table_keeps_all_columns_including_currency_and_other_dimensions(self):
        self.sql.run_payload.return_value.update(
            sql='SELECT category, currency, SUM(revenue) AS revenue FROM commerce.sales GROUP BY 1,2 LIMIT 200',
            rows=[{'category': 'A', 'currency': 'EUR', 'revenue': 10}])
        doc = await self.agent.build(self.request, 'Revenue by category and currency')
        self.assertEqual(1, len(doc.tiles))
        self.assertIn('<th>currency</th>', render_dashboard(doc))
        self.assertIn('<th>category</th>', render_dashboard(doc))

    async def test_explicit_chart_on_aggregate_row_does_not_silently_become_kpi(self):
        self.sql.run_payload.return_value.update(
            sql='SELECT SUM(revenue) AS revenue FROM commerce.sales LIMIT 1', rows=[{'revenue': 10}])
        doc = await self.agent.build(self.request, 'Line chart of revenue')
        self.assertEqual(['line'], [tile.kind for tile in doc.tiles])
        self.assertEqual('failed', doc.status)

    async def test_latest_snapshot_is_delegated_to_sql_and_observed_dates_are_retained(self):
        self.sql.run_payload.return_value['metadata']['snapshot_dates'] = ['2026-11-13']
        doc = await self.agent.build(self.request, 'Stock at latest snapshot')
        self.assertEqual('Stock at latest snapshot', self.sql.run_payload.call_args.args[0].question)
        self.assertEqual(['2026-11-13'], doc.results[0].payload['metadata']['snapshot_dates'])
        self.provider.assert_not_called()

    async def test_real_sql_validation_and_execution_add_no_dashboard_generation(self):
        from core.agents.sql.agent import SQLAnalyticsAgent
        sql = ("SELECT DATE_TRUNC('quarter', s.date) AS month, SUM(s.revenue) AS revenue "
               'FROM commerce.sales s WHERE s.date >= $1 AND s.date < $2 GROUP BY 1 ORDER BY 1 LIMIT 200')
        provider = SimpleNamespace(generate=Mock(return_value=json.dumps({
            'sql': sql, 'parameters': ['2022-01-01', '2023-01-01'],
            'outputs': [{'kind': 'line', 'query': 0, 'dimension': 'month', 'measures': ['revenue']}]})))
        repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[
            {'month': '2022-01-01', 'revenue': 10}, {'month': '2022-02-01', 'revenue': 20}]))
        agent = SQLAnalyticsAgent(repo, llm=provider, inventory_only=False)
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': ''}):
            doc = await DashboardDocumentAgent(agent).build(self.request, 'Quarterly revenue during 2022')
        self.assertEqual('complete', doc.status)
        self.assertEqual(['line'], [tile.kind for tile in doc.tiles])
        provider.generate.assert_called_once()
        repo.execute_approved_query.assert_awaited_once()
        self.assertEqual(sql, doc.results[0].payload['sql'])
        self.assertNotIn('jev', doc.results[0].payload.get('metadata', {}))

    async def test_requested_statistics_share_chart_dataset_without_duplicate_table(self):
        doc = await self.agent.build(self.request, 'Dashboard showing monthly revenue and descriptive statistics')
        self.assertEqual(['line', 'summary'], [tile.kind for tile in doc.tiles])
        self.assertIn('mean 15', render_dashboard(doc))
        self.assertEqual(1, render_dashboard(doc).count('<table>'))
        self.sql.run_payload.assert_awaited_once()
        self.provider.assert_not_called()

    async def test_multiple_charts_get_requested_summaries_for_their_own_measures(self):
        for first, second in [('sessions', 'page_views'), ('net_amount', 'units')]:
            with self.subTest(measures=(first, second)):
                self.sql.run_payload.reset_mock()
                self.sql.run_payload.return_value.update(
                    sql=f"SELECT DATE_TRUNC('month', a.observed_at) AS period, SUM(a.{first}) AS {first}, SUM(a.{second}) AS {second} FROM analytics.observations a GROUP BY 1 LIMIT 200",
                    rows=[{'period': '2026-01-01', first: 10, second: 100},
                          {'period': '2026-03-01', first: None, second: 200},
                          {'period': '2026-05-01', first: 30, second: 300}],
                    metadata={'request_contract': {'columns': ['period', first, second], 'dimensions': ['period'],
                        'chart_type': None, 'charts': [
                            {'type': 'line', 'dimension': 'period', 'measures': [first]},
                            {'type': 'bar', 'dimension': 'period', 'measures': [second]}]}})
                doc = await self.agent.build(self.request, 'Comparable monthly charts with a statistical summary of returned months')
                self.assertEqual('complete', doc.status)
                summaries = [tile for tile in doc.tiles if tile.kind == 'summary']
                self.assertEqual([[first], [second]], [tile.measures for tile in summaries])
                self.assertEqual({'q0'}, {tile.query_id for tile in summaries})
                self.assertEqual(4, len({tile.id for tile in doc.tiles}))
                html = render_dashboard(doc)
                self.assertIn(f'{first}: 2 observed; min 10; max 30; mean 20', html)
                self.assertIn(f'{second}: 3 observed; min 100; max 300; mean 200', html)
                self.assertEqual(1, html.count('<table>'))
                self.sql.run_payload.assert_awaited_once()
                self.provider.assert_not_called()

    async def test_no_summary_for_one_month_even_with_multiple_chart_mappings(self):
        self.sql.run_payload.return_value.update(
            sql="SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue FROM commerce.sales s GROUP BY 1 LIMIT 200",
            rows=[{'month': '2026-01-01', 'revenue': 10}],
            metadata={'request_contract': {'columns': ['month', 'revenue'], 'dimensions': ['month'], 'chart_type': None,
                'charts': [{'type': 'bar', 'dimension': 'month', 'measures': ['revenue']}]}})
        doc = await self.agent.build(self.request, 'Revenue chart with summary statistics')
        self.assertNotIn('summary', [tile.kind for tile in doc.tiles])

    async def test_summary_request_applies_to_independent_query_results(self):
        datasets = []
        for metric in ('amount', 'quantity'):
            datasets.append({'question': f'Monthly {metric}', 'payload': {
                'ok': True, 'query_status': 'executed',
                'sql': f"SELECT DATE_TRUNC('month', a.observed_at) AS period, SUM(a.{metric}) AS {metric} FROM analytics.observations a GROUP BY 1 LIMIT 200",
                'rows': [{'period': '2026-01-01', metric: 10}, {'period': '2026-02-01', metric: 20}],
                'metadata': {'request_contract': {'columns': ['period', metric], 'dimensions': ['period'], 'chart_type': None,
                    'charts': [{'type': 'line', 'dimension': 'period', 'measures': [metric]}]}}}})
        self.sql.run_payload.return_value = {'datasets': datasets}
        doc = await self.agent.build(self.request, 'Monthly amount and quantity with summary statistics')
        self.assertEqual('complete', doc.status)
        summaries = [tile for tile in doc.tiles if tile.kind == 'summary']
        self.assertEqual([('q0', ['amount']), ('q1', ['quantity'])], [(tile.query_id, tile.measures) for tile in summaries])
        self.assertEqual(4, len({tile.id for tile in doc.tiles}))
        self.sql.run_payload.assert_awaited_once()
        self.provider.assert_not_called()

    async def test_summary_follows_aggregate_aliases_through_ctes_and_subqueries(self):
        for wrapper in ('cte', 'subquery', 'nested_cte'):
            with self.subTest(wrapper=wrapper):
                source = "SELECT DATE_TRUNC('month', o.observed_at) AS bucket, SUM(o.amount) AS amount, SUM(o.quantity) AS quantity FROM analytics.observations o GROUP BY 1"
                if wrapper == 'cte':
                    sql = f'WITH totals AS ({source}) SELECT t.bucket AS period, t.amount AS net_value, t.quantity AS units FROM totals t ORDER BY 1 LIMIT 200'
                elif wrapper == 'subquery':
                    sql = f'SELECT t.bucket AS period, t.amount AS net_value, t.quantity AS units FROM ({source}) t ORDER BY 1 LIMIT 200'
                else:
                    sql = f'WITH totals AS ({source}), renamed AS (SELECT bucket, amount AS net_value, quantity AS units FROM totals) SELECT bucket AS period, net_value, units FROM renamed ORDER BY 1 LIMIT 200'
                self.sql.run_payload.return_value.update(sql=sql,
                    rows=[{'period': '2026-01-01', 'net_value': 10, 'units': 100},
                          {'period': '2026-05-01', 'net_value': 30, 'units': 300}],
                    metadata={'request_contract': {'columns': ['period', 'net_value', 'units'], 'dimensions': ['period'],
                        'chart_type': None, 'charts': [{'type': 'line', 'dimension': 'period', 'measures': ['net_value']},
                                                       {'type': 'bar', 'dimension': 'period', 'measures': ['units']}]}})
                doc = await self.agent.build(self.request, 'Monthly charts with a statistical summary of returned observations')
                self.assertEqual('complete', doc.status)
                self.assertEqual([['net_value'], ['units']], [tile.measures for tile in doc.tiles if tile.kind == 'summary'])
                self.assertIn('net_value: 2 observed; min 10; max 30; mean 20', render_dashboard(doc))
                self.assertIn('units: 2 observed; min 100; max 300; mean 200', render_dashboard(doc))
                self.provider.assert_not_called()

    async def test_raw_and_windowed_cte_outputs_do_not_become_summary_measures(self):
        for expression in ('o.amount', 'SUM(o.amount) OVER (ORDER BY o.observed_at)'):
            with self.subTest(expression=expression):
                self.sql.run_payload.return_value.update(
                    sql=f'WITH observations AS (SELECT o.observed_at AS period, {expression} AS value FROM analytics.observations o) SELECT period, value FROM observations LIMIT 200',
                    rows=[{'period': '2026-01-01', 'value': 10}, {'period': '2026-05-01', 'value': 30}],
                    metadata={'request_contract': {'columns': ['period', 'value'], 'dimensions': ['period'], 'chart_type': None,
                        'charts': [{'type': 'line', 'dimension': 'period', 'measures': ['value']}]}})
                doc = await self.agent.build(self.request, 'Charts with a statistical summary')
                self.assertNotIn('summary', [tile.kind for tile in doc.tiles])

    async def test_scope_cannot_be_replaced_by_sql_result_or_generated_text(self):
        scope = '2026-01-01 through 2026-05-31'
        self.sql.run_payload.return_value['scope'] = 'Untrusted generated content'
        doc = await self.agent.build(self.request, 'Monthly revenue', scope)
        self.assertEqual(scope, doc.scope)
        self.assertIn(scope, self.sql.run_payload.call_args.args[0].question)


if __name__ == '__main__':
    unittest.main()
