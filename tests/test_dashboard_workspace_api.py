import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dashboards import router, get_store, principal
from core.dashboards.store import DashboardStore
from test_dashboard_documents import document


class DashboardApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = DashboardStore(self.temp.name)
        self.user = {'sub': 'alice', 'role': 'admin'}
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_store] = lambda: self.store
        self.app.dependency_overrides[principal] = lambda: self.user
        self.client = TestClient(self.app)
        self.doc = self.store.create('alice', document())

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_private_reads_and_html_headers(self):
        response = self.client.get(f'/api/dashboards/{self.doc.id}/html')
        self.assertEqual(200, response.status_code)
        self.assertIn("script-src 'none'", response.headers['content-security-policy'])
        self.assertEqual('no-store', response.headers['cache-control'])
        self.user = {'sub': 'bob', 'role': 'admin'}
        self.assertEqual(404, self.client.get(f'/api/dashboards/{self.doc.id}').status_code)
        self.assertEqual([], self.client.get('/api/dashboards').json()['dashboards'])

    def test_presentation_edit_does_not_query_and_rejects_stale_write(self):
        body = {'revision': 1, 'title': 'Edited', 'tiles': [tile.model_dump() for tile in self.doc.tiles]}
        with patch('app.dashboards.build', new_callable=AsyncMock) as build:
            response = self.client.patch(f'/api/dashboards/{self.doc.id}', json=body)
            self.assertEqual(200, response.status_code)
            build.assert_not_called()
        self.assertEqual(409, self.client.patch(f'/api/dashboards/{self.doc.id}', json=body).status_code)

    def test_write_cannot_accept_html_sql_or_foreign_dataset(self):
        self.assertEqual(422, self.client.post('/api/dashboards', json={'description': 'test', 'sql': 'delete'}).status_code)
        body = {'revision': 1, 'title': 'Bad', 'tiles': [self.doc.tiles[0].model_dump() | {'query_id': 'foreign'}]}
        self.assertEqual(422, self.client.patch(f'/api/dashboards/{self.doc.id}', json=body).status_code)
        self.assertEqual(403, self.client.delete(f'/api/dashboards/{self.doc.id}?revision=1', headers={'Origin': 'https://foreign.example'}).status_code)

    def test_build_uses_shared_analytics_sql_with_legacy_dashboard_present(self):
        provider = Mock(side_effect=AssertionError('Dashboard must use SQL results directly'))
        sql = SimpleNamespace(inventory_only=False,
            repository=SimpleNamespace(get_schema=AsyncMock(return_value={'tables': {'commerce.sales': {'date', 'revenue'}}})),
            _provider=provider,
            run_payload=AsyncMock(return_value={'ok': True, 'query_status': 'executed', 'rows': [{'revenue': 12.5}],
                                               'sql': 'SELECT SUM(revenue) AS revenue FROM commerce.sales LIMIT 1'}))
        runtime = SimpleNamespace(analytics_agent=SimpleNamespace(sql_agent=sql), dashboard_agent=SimpleNamespace(repository=object()))
        with patch('app.dashboards._get_runtime', AsyncMock(return_value=runtime)):
            response = self.client.post('/api/dashboards', json={'description': 'Revenue dashboard July 2026'})
        self.assertEqual(201, response.status_code, response.text)
        self.assertEqual('complete', response.json()['dashboard']['status'])
        sql.run_payload.assert_awaited_once()
        provider.assert_not_called()

    def test_build_and_refresh_accept_raw_or_wrapped_sql_runtime(self):
        for wrapped in (False, True):
            with self.subTest(wrapped=wrapped):
                sql = SimpleNamespace(run_payload=AsyncMock(return_value={
                    'ok': True, 'query_status': 'executed', 'rows': [{'revenue': 25}],
                    'sql': 'SELECT SUM(revenue) AS revenue FROM commerce.sales LIMIT 1'}))
                analytics = SimpleNamespace(sql_agent=sql) if wrapped else sql
                runtime = SimpleNamespace(analytics_agent=analytics)
                with patch('app.dashboards._get_runtime', AsyncMock(return_value=runtime)):
                    result = self.client.post('/api/dashboards', json={'description': 'Total revenue'})
                    self.assertEqual(201, result.status_code, result.text)
                    saved = result.json()['dashboard']
                    refreshed = self.client.post(f"/api/dashboards/{saved['id']}/refresh", json={'revision': saved['revision']})
                    self.assertEqual(200, refreshed.status_code, refreshed.text)
                    self.assertEqual('complete', refreshed.json()['dashboard']['status'])
                    self.assertEqual(2, sql.run_payload.await_count)

    def test_deleting_tile_removes_unused_failed_source_and_updates_status(self):
        from core.dashboards.models import QuerySpec, QueryResult, TileSpec
        doc = self.doc.model_copy(deep=True)
        doc.queries.append(QuerySpec(id='unused', question='Other data'))
        doc.results.append(QueryResult(id='unused', question='Other data', status='failed'))
        doc.tiles.append(TileSpec(id='redundant', title='Redundant', kind='table', query_id='unused'))
        doc = self.store.save('alice', doc, expected_revision=1)
        body = {'revision': doc.revision, 'title': doc.title, 'tiles': [doc.tiles[0].model_dump()]}
        with patch('app.dashboards.build', new_callable=AsyncMock) as build:
            response = self.client.patch(f'/api/dashboards/{doc.id}', json=body)
            build.assert_not_called()
        saved = response.json()['dashboard']
        self.assertEqual(200, response.status_code)
        self.assertEqual('complete', saved['status'])
        self.assertEqual(['sales'], [query['id'] for query in saved['queries']])
        self.assertEqual(['total'], [tile['id'] for tile in saved['tiles']])
        body.update(revision=saved['revision'], tiles=[])
        self.assertEqual(422, self.client.patch(f'/api/dashboards/{doc.id}', json=body).status_code)

    def test_single_dataset_build_scope_refresh_reopen_and_download_without_dashboard_model(self):
        provider = Mock(side_effect=AssertionError('Unexpected dashboard model call'))
        sql = SimpleNamespace(_provider=provider, run_payload=AsyncMock(return_value={
            'ok': True, 'query_status': 'executed', 'rows': [{'revenue': 12.5}],
            'sql': 'SELECT SUM(revenue) AS revenue FROM commerce.sales LIMIT 1'}))
        runtime = SimpleNamespace(analytics_agent=SimpleNamespace(sql_agent=sql))
        with patch('app.dashboards._get_runtime', AsyncMock(return_value=runtime)):
            response = self.client.post('/api/dashboards', json={'description': 'Total revenue', 'scope': 'July 2026'})
            self.assertEqual(201, response.status_code, response.text)
            saved = response.json()['dashboard']
            self.assertEqual(['kpi'], [tile['kind'] for tile in saved['tiles']])
            tiles = saved['tiles']
            tiles[0]['title'] = 'My revenue'
            response = self.client.patch(f"/api/dashboards/{saved['id']}", json={
                'revision': saved['revision'], 'title': 'My dashboard', 'scope': 'August 2026', 'tiles': tiles})
            self.assertEqual(200, response.status_code, response.text)
            self.assertEqual(2, sql.run_payload.await_count)
            self.assertIn('August 2026', sql.run_payload.call_args.args[0].question)
            self.assertNotIn('July 2026', sql.run_payload.call_args.args[0].question)
        provider.assert_not_called()
        reopened = self.client.get(f"/api/dashboards/{saved['id']}")
        self.assertEqual('My revenue', reopened.json()['dashboard']['tiles'][0]['title'])
        self.assertEqual('August 2026', reopened.json()['dashboard']['scope'])
        html = self.client.get(f"/api/dashboards/{saved['id']}/html?download=true")
        self.assertEqual(200, html.status_code)
        self.assertIn('attachment;', html.headers['content-disposition'])
        self.assertIn('My revenue', html.text)


if __name__ == '__main__':
    unittest.main()
