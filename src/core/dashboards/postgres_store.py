"""Shared dashboard storage using the backend's Supabase PostgreSQL connection."""
from contextlib import closing, contextmanager
import os
from pathlib import Path
import sqlite3

import psycopg
from psycopg.rows import dict_row

from core.database.connection_limit import connect_database, close_database_connection
from core.dashboards.models import DashboardDocument
from core.dashboards.presentation import reconcile
from core.dashboards.store import DashboardStore, Conflict, StoreUnavailable


class PostgresDashboardStore(DashboardStore):
    # Table identifiers come only from trusted artifact-store subclasses.
    table = 'dashboard_private.dashboards'
    def __init__(self, database_url=None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        if not self.database_url:
            raise StoreUnavailable('Dashboard database is not configured.')

    @contextmanager
    def connect_owner(self, owner, *, write=False):
        connection = None
        try:
            connection = connect_database(self.database_url, row_factory=dict_row)
            with connection.transaction(), connection.cursor() as cursor:
                # Drop the privileged backend role before accessing user-owned rows.
                cursor.execute('SET LOCAL ROLE dashboard_store')
                cursor.execute("SELECT set_config('app.dashboard_owner', %s, true)", (owner,))
                if write:
                    cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (owner,))
                yield cursor
        except psycopg.errors.UniqueViolation as error:
            raise Conflict(f'{self.artifact_label} already exists. Reopen it before saving.') from error
        except psycopg.Error as error:
            raise StoreUnavailable('Dashboard storage is unavailable.') from error
        finally:
            if connection is not None:
                close_database_connection(connection)

    def list(self, subject):
        owner = self.owner(subject)
        with self.connect_owner(owner) as cursor:
            cursor.execute(f'SELECT id,title,revision,updated AS updated_at FROM {self.table} WHERE owner=%s ORDER BY updated DESC,id', (owner,))
            return [{**row, 'updated_at': row['updated_at'].isoformat()} for row in cursor.fetchall()]

    def get(self, subject, identifier):
        owner = self.owner(subject)
        with self.connect_owner(owner) as cursor:
            cursor.execute(f'SELECT document FROM {self.table} WHERE owner=%s AND id=%s', (owner, identifier))
            row = cursor.fetchone()
        return self.decode(row['document']) if row else None

    def html(self, subject, identifier):
        owner = self.owner(subject)
        with self.connect_owner(owner) as cursor:
            cursor.execute(f'SELECT html FROM {self.table} WHERE owner=%s AND id=%s', (owner, identifier))
            row = cursor.fetchone()
        return row['html'] if row else None

    def save(self, subject, document, expected_revision):
        doc, encoded, html = self.prepare(document, expected_revision)
        owner = self.owner(subject)
        with self.connect_owner(owner, write=True) as cursor:
            if expected_revision is None:
                cursor.execute(f'SELECT count(*) AS total FROM {self.table} WHERE owner=%s', (owner,))
                if cursor.fetchone()['total'] >= 100:
                    raise ValueError(f'Saved {self.artifact_label.lower()} limit reached (100). Delete an old {self.artifact_label.lower()} first.')
                cursor.execute(f'INSERT INTO {self.table} (id,owner,revision,title,updated,document,html) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                    (doc.id, owner, doc.revision, doc.title, doc.updated_at, encoded, html))
            else:
                cursor.execute(f'UPDATE {self.table} SET revision=%s,title=%s,updated=%s,document=%s,html=%s WHERE owner=%s AND id=%s AND revision=%s',
                    (doc.revision, doc.title, doc.updated_at, encoded, html, owner, doc.id, expected_revision))
                if not cursor.rowcount:
                    raise Conflict(f'{self.artifact_label} changed. Reopen it before saving.')
        return doc

    def delete(self, subject, identifier, revision):
        owner = self.owner(subject)
        with self.connect_owner(owner, write=True) as cursor:
            cursor.execute(f'DELETE FROM {self.table} WHERE owner=%s AND id=%s AND revision=%s', (owner, identifier, revision))
            if not cursor.rowcount:
                raise Conflict(f'{self.artifact_label} changed. Reopen it before deleting.')

    def import_sqlite(self, path):
        """Copy legacy records without changing IDs/owners/revisions or replacing shared records."""
        path = Path(path).resolve()
        with closing(sqlite3.connect('file:' + path.as_posix() + '?mode=ro', uri=True)) as source:
            source.row_factory = sqlite3.Row
            rows = [dict(row) for row in source.execute('SELECT * FROM dashboards')]
        owners = sorted({row['owner'] for row in rows})
        imported = 0
        for owner in owners:
            records = [row for row in rows if row['owner'] == owner]
            with self.connect_owner(owner, write=True) as cursor:
                cursor.execute(f'SELECT id FROM {self.table} WHERE owner=%s', (owner,))
                existing = {row['id'] for row in cursor.fetchall()}
                if len(existing | {row['id'] for row in records}) > 100:
                    raise ValueError('Import exceeds the saved dashboard limit for an owner; source was retained.')
                for row in records:
                    doc = DashboardDocument.model_validate_json(row['document'])
                    if (doc.id, doc.revision, doc.title) != (row['id'], row['revision'], row['title']):
                        raise ValueError('Legacy dashboard metadata does not match its document; source was retained.')
                    cursor.execute(f'INSERT INTO {self.table} (id,owner,revision,title,updated,document,html) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING',
                        (row['id'], owner, row['revision'], row['title'], row['updated'], row['document'], row['html']))
                    imported += cursor.rowcount
        return {'imported': imported, 'existing': len(rows) - imported}
