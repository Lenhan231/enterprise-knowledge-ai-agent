import tempfile
import unittest
from unittest.mock import AsyncMock, patch

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


if __name__ == '__main__':
    unittest.main()
