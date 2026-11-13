import copy
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.agents.dashboard_agent import DashboardAgent
from core.agents.router import AgentRouter
from core.agents.sql_analytics_agent import AnalyticsPermissionDenied
from core.models.agents import AgentRequest, VerifiedIdentity

IDENTITY = VerifiedIdentity(subject='analyst', permissions={'analytics:read'})


def payload(rows=None, sql=None):
    return {'ok': True, 'rows': rows or [{'category': 'A', 'sessions': Decimal('12.5')},
                                        {'category': 'B', 'sessions': Decimal('25')}],
            'sql': sql or 'SELECT w.traffic_source AS category, SUM(w.sessions) AS sessions '
                         'FROM commerce.web_traffic AS w GROUP BY w.traffic_source LIMIT 20',
            'parameters': [], 'query_status': 'executed',
            'evidence': [{'source': 'commerce.web_traffic'}],
            'limitations': ['Historical data only.'],
            'metadata': {'source': ['commerce.web_traffic'], 'columns': [
                {'name': 'category', 'unit': None}, {'name': 'sessions', 'unit': 'sessions'}]}}


class DashboardTest(unittest.IsolatedAsyncioTestCase):
    async def run_chart(self, question='Sessions by source in 2022', data=None, metadata=None):
        self.sql = AsyncMock()
        self.sql.run_payload.return_value = copy.deepcopy(data if data is not None else payload())
        request = AgentRequest(question=question, identity=IDENTITY, metadata=metadata or {})
        result = await DashboardAgent(self.sql).run(request)
        self.sql.run_payload.assert_awaited_once_with(request)
        return result

    async def test_requires_verified_permission_before_calling_sql(self):
        sql = AsyncMock()
        with self.assertRaises(AnalyticsPermissionDenied):
            await DashboardAgent(sql).run(AgentRequest(question='Chart sessions'))
        sql.run_payload.assert_not_awaited()

    async def test_bar_uses_sql_rows_and_preserves_provenance(self):
        result = await self.run_chart()
        chart = result.data['visualization']
        self.assertEqual(chart['type'], 'bar')
        self.assertEqual(chart['categories'], ['A', 'B'])
        self.assertEqual(chart['series'][0]['values'], [12.5, 25.0])
        self.assertEqual(result.data['rows'][0]['sessions'], Decimal('12.5'))
        self.assertEqual(result.evidence[0].source, 'commerce.web_traffic')
        self.assertIn('Historical data only.', result.metadata['limitations'])
        self.assertEqual(result.agent, 'dashboard')
        self.assertEqual(result.metadata['chart_status'], 'rendered')

    async def test_line_orders_dates_preserves_nulls_and_negative_values(self):
        data = payload([{'month': date(2022, 3, 1), 'profit': -3},
                        {'month': date(2022, 1, 1), 'profit': 10},
                        {'month': date(2022, 2, 1), 'profit': None}],
                       "SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue)-SUM(s.cogs) AS profit "
                       'FROM commerce.sales AS s GROUP BY 1 LIMIT 20')
        data['metadata']['columns'] = [{'name': 'month'}, {'name': 'profit', 'unit': 'currency'}]
        result = await self.run_chart('Monthly profit during 2022', data)
        chart = result.data['visualization']
        self.assertEqual(chart['type'], 'line')
        self.assertEqual(chart['categories'], ['2022-01-01', '2022-02-01', '2022-03-01'])
        self.assertEqual(chart['series'][0]['values'], [10, None, -3])
        self.assertIn('unconfirmed', chart['unit'])

    async def test_explicit_donut_accepts_complete_additive_groups(self):
        result = await self.run_chart('Donut of session share by source in 2022')
        self.assertEqual(result.data['visualization']['type'], 'donut')

    async def test_ineligible_donut_keeps_table_and_reason(self):
        cases = [
            payload([{'category': 'A', 'sessions': -1}, {'category': 'B', 'sessions': 2}]),
            payload(sql='SELECT w.traffic_source AS category, AVG(w.sessions) AS sessions '
                        'FROM commerce.web_traffic AS w GROUP BY w.traffic_source LIMIT 20'),
            payload(sql='SELECT w.traffic_source AS category, SUM(w.sessions) AS sessions '
                        'FROM commerce.web_traffic AS w GROUP BY w.traffic_source LIMIT 2'),
            payload(sql='SELECT w.traffic_source AS category, SUM(w.sessions) AS sessions '
                        'FROM commerce.web_traffic AS w GROUP BY w.traffic_source HAVING SUM(w.sessions)>1 LIMIT 20'),
            payload([{'category': 'A', 'sessions': 0}, {'category': 'B', 'sessions': 0}]),
            payload([{'category': 'A', 'sessions': None}, {'category': 'B', 'sessions': 2}]),
        ]
        for data in cases:
            with self.subTest(data=data):
                result = await self.run_chart('Donut of session share by source in 2022', data)
                self.assertNotIn('visualization', result.data)
                self.assertEqual(result.metadata['chart_status'], 'table_only')
                self.assertTrue(result.metadata['chart_reason'])
                self.assertTrue(result.data['rows'])

    async def test_donut_rejects_overlapping_flags(self):
        data = payload([{'category': 'A', 'stockout': 5, 'overstock': 7}],
                       'SELECT i.category AS category, COUNT(*) FILTER (WHERE i.stockout_flag) AS stockout, '
                       'COUNT(*) FILTER (WHERE i.overstock_flag) AS overstock FROM commerce.inventory AS i '
                       "WHERE i.snapshot_date = '2022-12-31' GROUP BY i.category LIMIT 20")
        result = await self.run_chart('Donut inventory flags', data)
        self.assertNotIn('visualization', result.data)

    async def test_duplicate_dimensions_nonfinite_and_mixed_units_are_table_only(self):
        cases = [payload([{'category': 'A', 'sessions': 2}, {'category': 'A', 'sessions': 3}]),
                 payload([{'category': 'A', 'sessions': float('inf')}]),
                 payload([{'category': 'A', 'sessions': True}])]
        mixed = payload([{'category': 'A', 'sessions': 2, 'rate': .5}])
        mixed['metadata']['columns'].append({'name': 'rate', 'unit': 'percent'})
        cases.append(mixed)
        for data in cases:
            result = await self.run_chart(data=data)
            self.assertNotIn('visualization', result.data)

    async def test_explicit_line_requires_temporal_axis(self):
        result = await self.run_chart('Line chart of sessions by source in 2022')
        self.assertNotIn('visualization', result.data)

    async def test_failure_clarification_and_empty_results_do_not_create_charts(self):
        for state in ('clarification_required', 'failed', 'empty'):
            data = {'ok': False, 'rows': [], 'answer': state,
                    'metadata': {'status': state}, 'query_status': 'executed' if state == 'empty' else 'error'}
            result = await self.run_chart(data=data)
            self.assertNotIn('visualization', result.data)
            self.assertEqual(result.answer, state)

    async def test_multiple_compatible_series_use_grouped_bar(self):
        data = payload([{'category': 'A', 'received': 4, 'sold': 2}])
        data['metadata']['columns'] = [{'name': 'category'}, {'name': 'received', 'unit': 'units'},
                                       {'name': 'sold', 'unit': 'units'}]
        result = await self.run_chart(data=data)
        self.assertEqual(len(result.data['visualization']['series']), 2)

    async def test_constant_snapshot_is_scope_not_a_second_dimension(self):
        data = payload([{'snapshot_date': date(2022, 12, 31), 'category': 'A', 'stock_on_hand': 12},
                        {'snapshot_date': date(2022, 12, 31), 'category': 'B', 'stock_on_hand': 20}],
                       'SELECT i.snapshot_date, i.category, SUM(i.stock_on_hand) AS stock_on_hand '
                       "FROM commerce.inventory AS i WHERE i.snapshot_date='2022-12-31' "
                       'GROUP BY i.snapshot_date, i.category LIMIT 20')
        result = await self.run_chart('Stock by category at 2022-12-31', data)
        self.assertEqual(result.data['visualization']['type'], 'bar')
        self.assertEqual(result.data['visualization']['scope']['dates'], {'snapshot_date': '2022-12-31'})

    async def test_dashboard_clarification_is_separate_from_sql_and_other_users(self):
        sql = AsyncMock()
        sql.run_payload.side_effect = [
            {'ok': False, 'answer': 'Which year?', 'rows': [], 'metadata': {
                'status': 'clarification_required', 'clarification_required': True}}, payload(), payload()]
        router = AgentRouter(None, None, None, dashboard_agent=DashboardAgent(sql))
        request = AgentRequest(question='Donut of session share by source', identity=IDENTITY, conversation_id='one')
        result = await router.run_mode(request, 'dashboard')
        self.assertEqual(result.metadata['status'], 'clarification_required')
        result = await router.run_mode(request.model_copy(update={'question': 'During 2022'}), 'dashboard')
        self.assertEqual(result.data['visualization']['type'], 'donut')
        combined = sql.run_payload.await_args_list[1].args[0]
        self.assertIn('Donut of session share', combined.question)
        self.assertIn('During 2022', combined.question)
        self.assertNotIn('_sql_context', combined.metadata)
        self.assertEqual(result.metadata['selected_route'], 'dashboard')
        self.assertFalse(router.sql_conversations.entries)
        other = request.model_copy(update={'identity': VerifiedIdentity(subject='other', permissions={'analytics:read'})})
        await router.run_mode(other, 'dashboard')
        self.assertEqual(sql.run_payload.await_args_list[2].args[0].question, request.question)

    async def test_router_denial_and_timeout_do_not_save_dashboard_state(self):
        import asyncio
        sql = AsyncMock()
        router = AgentRouter(None, None, None, dashboard_agent=DashboardAgent(sql), request_timeout=.01)
        request = AgentRequest(question='Chart sessions', conversation_id='one')
        with self.assertRaises(PermissionError):
            await router.run_mode(request, 'dashboard')
        self.assertFalse(router.dashboard_conversations.entries)
        sql.run_payload.assert_not_awaited()
        async def slow(_request):
            await asyncio.sleep(1)
        sql.run_payload.side_effect = slow
        result = await router.run_mode(request.model_copy(update={'identity': IDENTITY}), 'dashboard')
        self.assertEqual(result.metadata['chart_status'], 'unavailable')
        self.assertEqual(result.agent, 'dashboard')
        self.assertEqual(router.dashboard_conversations.entries[('analyst', 'one')].history, [])

    async def test_both_backend_entrypoints_share_the_existing_sql_agent(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.agents import _get_runtime
        from core.agents.main import create_app
        from core.agents.sql_analytics_agent import SQLAnalyticsAgent
        with patch.object(SQLAnalyticsAgent, 'run_payload', new_callable=AsyncMock, return_value=payload()), \
                patch('app.agents.load_dotenv'), patch('core.agents.main.load_dotenv'):
            application = FastAPI()
            runtime = await _get_runtime(application)
            self.assertIs(runtime.dashboard_agent.sql_agent, runtime.analytics_agent.sql_agent)
            result = await runtime.run_mode(AgentRequest(question='Sessions by source during 2022', identity=IDENTITY), 'dashboard')
            self.assertEqual(result.data['visualization']['type'], 'bar')
            app = create_app(commerce_repository=AsyncMock(), identity_resolver=lambda _: IDENTITY)
            with TestClient(app) as client:
                response = client.post('/api/chat', json={
                    'question': 'Donut of session share by source during 2022', 'agent_mode': 'dashboard'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['data']['visualization']['type'], 'donut')
                self.assertEqual(response.json()['data']['rows'][0]['sessions'], '12.5')

    async def test_chart_schema_rejects_misaligned_and_nonfinite_series(self):
        from core.models.agents import ChartSpec
        result = await self.run_chart()
        valid = result.data['visualization']
        for values in ([1], [float('inf'), 2]):
            malformed = copy.deepcopy(valid)
            malformed['series'][0]['values'] = values
            with self.assertRaises(ValueError):
                ChartSpec.model_validate(malformed)

    async def test_explicit_bar_overrides_composition_wording(self):
        result = await self.run_chart('Bar chart of session share by source during 2022')
        self.assertEqual(result.data['visualization']['type'], 'bar')

    async def test_existing_category_filter_is_forwarded_and_validated(self):
        sql = AsyncMock()
        sql.run_payload.return_value = payload()
        agent = DashboardAgent(sql)
        request = AgentRequest(question='Stockouts at 2022-12-31', identity=IDENTITY,
                               metadata={'category': ' Casual '})
        await agent.run(request)
        self.assertIn('Inventory category filter: "Casual"', sql.run_payload.await_args.args[0].question)
        self.assertIs(sql.run_payload.await_args.args[0].identity, IDENTITY)
        for invalid in (['Casual'], 'x' * 101):
            with self.assertRaises(ValueError):
                await agent.run(request.model_copy(update={'metadata': {'category': invalid}}))
        self.assertEqual(sql.run_payload.await_count, 1)


if __name__ == '__main__':
    unittest.main()
