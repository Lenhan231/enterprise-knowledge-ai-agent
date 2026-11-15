import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from core.dashboards.agent import DashboardDocumentAgent
from core.dashboards.models import QuerySpec, QueryResult, TileSpec
from core.models.agents import AgentRequest, VerifiedIdentity
from test_dashboard_documents import document


class DashboardAgentTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = Mock(side_effect=AssertionError('Unexpected dashboard model call'))
        self.sql = SimpleNamespace(_provider=self.provider,
            run_payload=AsyncMock(return_value={'ok': True, 'query_status': 'executed',
                'rows': [{'revenue': 10}],
                'sql': 'SELECT SUM(revenue) AS revenue FROM commerce.sales LIMIT 1'}))
        self.agent = DashboardDocumentAgent(self.sql)
        self.request = AgentRequest(question='Dashboard', identity=VerifiedIdentity(subject='alice', permissions={'analytics:read'}))

    async def test_legacy_multi_dataset_refresh_preserves_definition_without_planning(self):
        doc = document()
        doc.queries.append(QuerySpec(id='other', question='Order count'))
        doc.results.append(QueryResult(id='other', question='Order count', status='failed'))
        doc.tiles.append(TileSpec(id='other', title='Other', kind='table', query_id='other'))
        refreshed = await self.agent.refresh(self.request, doc)
        self.assertEqual(2, self.sql.run_payload.await_count)
        self.assertEqual(['sales', 'other'], [item.id for item in refreshed.queries])
        self.assertEqual(['total', 'other'], [tile.id for tile in refreshed.tiles])
        self.provider.assert_not_called()

    async def test_failed_query_preserves_attempted_sql_and_limitations(self):
        self.sql.run_payload.return_value = {'ok': False, 'query_status': 'error',
            'attempted_sql': 'SELECT SUM(revenue) FROM commerce.sales',
            'limitations': ['Database query did not complete.'],
            'metadata': {'error_type': 'DataError', '_sql_context': {'private': 'state'}}}
        doc = await self.agent.build(self.request, 'Revenue dashboard')
        result = doc.results[0]
        self.assertEqual('failed', result.status)
        self.assertEqual('SELECT SUM(revenue) FROM commerce.sales', result.payload['attempted_sql'])
        self.assertEqual(['Database query did not complete.'], result.payload['metadata']['limitations'])
        self.assertNotIn('_sql_context', result.payload['metadata'])

    async def test_query_exception_remains_explicit_without_leaking_provider_error(self):
        self.sql.run_payload.side_effect = RuntimeError('private connection details')
        with self.assertLogs('core.dashboards.agent', level='ERROR'):
            doc = await self.agent.build(self.request, 'Revenue')
        self.assertEqual('failed', doc.status)
        self.assertNotIn('private connection', doc.results[0].message)

    async def test_refresh_permission_denied_before_sql(self):
        self.request.identity = None
        with self.assertRaises(PermissionError):
            await self.agent.refresh(self.request, document())
        self.sql.run_payload.assert_not_called()

    async def test_alias_binding_does_not_change_selected_metric(self):
        doc = document()
        doc.tiles[0].measures = ['total_revenue']
        await self.agent.refresh(self.request, doc)
        self.assertEqual(['revenue'], doc.tiles[0].measures)
        doc.tiles[0].measures = ['profit']
        self.agent.bind_fields(doc)
        self.assertEqual(['profit'], doc.tiles[0].measures)


if __name__ == '__main__':
    unittest.main()
