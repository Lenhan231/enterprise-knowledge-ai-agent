"""Opt-in tests against the migrated database; every row belongs to random test users."""
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import tempfile
import unittest
from uuid import uuid4

import psycopg
from core.database.connection_limit import connect_database, close_database_connection
from core.agents.dashboard.postgres_store import PostgresDashboardStore
from core.agents.dashboard.store import Conflict, StoreUnavailable
from core.agents.dashboard.store import DashboardStore
from tests.dashboard.test_dashboard_documents import document


@unittest.skipUnless(os.getenv('DASHBOARD_POSTGRES_TEST_URL'), 'Explicit dashboard integration database required')
class PostgresDashboardTest(unittest.TestCase):
    def setUp(self):
        self.store = PostgresDashboardStore(os.environ['DASHBOARD_POSTGRES_TEST_URL'])
        self.alice, self.bob = 'dashboard-test-' + uuid4().hex, 'dashboard-test-' + uuid4().hex

    def tearDown(self):
        for subject in (self.alice, self.bob):
            owner = self.store.owner(subject)
            with self.store.connect_owner(owner, write=True) as cursor:
                cursor.execute('DELETE FROM dashboard_private.dashboards WHERE owner=%s', (owner,))

    def test_reopen_is_private_and_stale_writes_cannot_overwrite(self):
        saved = self.store.create(self.alice, document())
        reopened = PostgresDashboardStore(self.store.database_url)
        self.assertEqual(saved.model_dump(), reopened.get(self.alice, saved.id).model_dump())
        self.assertEqual([], reopened.list(self.bob))
        self.assertIsNone(reopened.get(self.bob, saved.id))
        self.assertIsNone(reopened.html(self.bob, saved.id))
        with self.assertRaises(Conflict):
            reopened.save(self.bob, saved, 1)
        with self.assertRaises(Conflict):
            reopened.delete(self.bob, saved.id, 1)
        updated = reopened.save(self.alice, saved, 1)
        self.assertEqual(2, updated.revision)
        with self.assertRaises(Conflict):
            self.store.save(self.alice, saved, 1)
        self.assertNotIn('<script>', reopened.html(self.alice, saved.id))

    def test_sqlite_import_preserves_owners_revisions_and_is_safe_to_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            source = DashboardStore(directory)
            first = source.create(self.alice, document())
            first = source.save(self.alice, first, 1)
            second = source.create(self.bob, document())
            self.assertEqual({'imported': 2, 'existing': 0}, self.store.import_sqlite(source.path))
            self.assertEqual({'imported': 0, 'existing': 2}, self.store.import_sqlite(source.path))
            self.assertEqual(first.model_dump(), self.store.get(self.alice, first.id).model_dump())
            self.assertIsNone(self.store.get(self.alice, second.id))
            self.assertEqual(2, self.store.get(self.alice, first.id).revision)
            self.assertTrue(source.path.exists())

    def test_rls_still_protects_rows_if_an_owner_predicate_is_omitted(self):
        saved = self.store.create(self.alice, document())
        with self.store.connect_owner(self.store.owner(self.bob)) as cursor:
            cursor.execute('SELECT id FROM dashboard_private.dashboards')
            self.assertEqual([], cursor.fetchall())
            cursor.execute('SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user')
            self.assertFalse(cursor.fetchone()['rolbypassrls'])
        with self.assertRaises(StoreUnavailable):
            with self.store.connect_owner(self.store.owner(self.alice), write=True) as cursor:
                cursor.execute('UPDATE dashboard_private.dashboards SET owner=%s WHERE id=%s', (self.store.owner(self.bob), saved.id))
        self.assertIsNotNone(self.store.get(self.alice, saved.id))

    def test_anonymous_role_cannot_access_dashboard_schema(self):
        connection = connect_database(self.store.database_url)
        try:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with connection.transaction(), connection.cursor() as cursor:
                    cursor.execute('SET LOCAL ROLE anon')
                    cursor.execute('SELECT id FROM dashboard_private.dashboards LIMIT 1')
        finally:
            close_database_connection(connection)

    def test_concurrent_edits_only_one_revision_wins(self):
        saved = self.store.create(self.alice, document())
        ready = threading.Barrier(2)
        def update(_):
            ready.wait()
            try:
                self.store.save(self.alice, saved, 1)
                return True
            except Conflict:
                return False
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual([False, True], sorted(pool.map(update, range(2))))
        self.assertEqual(2, self.store.get(self.alice, saved.id).revision)

    def test_concurrent_creates_cannot_bypass_per_user_limit(self):
        owner = self.store.owner(self.alice)
        values = []
        for _ in range(99):
            doc, encoded, html = self.store.prepare(document(), None)
            values.append((doc.id, owner, doc.revision, doc.title, doc.updated_at, encoded, html))
        with self.store.connect_owner(owner, write=True) as cursor:
            cursor.executemany('INSERT INTO dashboard_private.dashboards VALUES (%s,%s,%s,%s,%s,%s,%s)', values)
        ready = threading.Barrier(2)
        def create(_):
            ready.wait()
            try:
                self.store.create(self.alice, document())
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual([False, True], sorted(pool.map(create, range(2))))
        self.assertEqual(100, len(self.store.list(self.alice)))
