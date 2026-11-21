import os
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.agents.dashboard.store import create_dashboard_store, DashboardStore, StoreUnavailable


class PersistentStoreTest(unittest.TestCase):
    def test_configured_database_selects_shared_storage_without_connecting_on_startup(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://unused/test'}, clear=True):
            store = create_dashboard_store()
        from core.agents.dashboard.postgres_store import PostgresDashboardStore
        self.assertIsInstance(store, PostgresDashboardStore)

    def test_explicit_postgres_never_silently_falls_back_to_sqlite(self):
        with patch.dict(os.environ, {'DASHBOARD_STORAGE_BACKEND': 'postgres'}, clear=True):
            with self.assertRaises(StoreUnavailable):
                create_dashboard_store()

    def test_failed_database_returns_sanitized_503_on_reads(self):
        from app.dashboards import router, principal
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[principal] = lambda: {'sub': 'alice', 'role': 'admin'}
        store = Mock()
        store.list.side_effect = StoreUnavailable('internal connection information')
        with patch('app.dashboards._get_store', return_value=store), TestClient(app) as client:
            result = client.get('/api/dashboards')
        self.assertEqual(503, result.status_code)
        self.assertNotIn('internal connection', result.text)
