"""Private, atomic document + HTML persistence, separate from analytics data."""
import hashlib
import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager

from core.dashboards.models import DashboardDocument, now
from core.dashboards.render import render_dashboard
from core.dashboards.presentation import reconcile


class Conflict(ValueError):
    pass


class DashboardStore:
    def __init__(self, directory=None):
        self.directory = Path(directory or os.getenv('DASHBOARD_STORAGE_DIR', 'artifacts/local/dashboards'))
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'dashboards.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS dashboards (id TEXT PRIMARY KEY, owner TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL, updated TEXT NOT NULL, document TEXT NOT NULL, html TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def owner(subject):
        return hashlib.sha256(subject.encode()).hexdigest()

    def list(self, subject):
        with self.connect() as db:
            return [dict(id=row[0], title=row[1], revision=row[2], updated_at=row[3]) for row in db.execute('SELECT id,title,revision,updated FROM dashboards WHERE owner=? ORDER BY updated DESC', (self.owner(subject),))]

    def get(self, subject, identifier):
        with self.connect() as db:
            row = db.execute('SELECT document FROM dashboards WHERE owner=? AND id=?', (self.owner(subject), identifier)).fetchone()
        return reconcile(DashboardDocument.model_validate_json(row[0])) if row else None

    def html(self, subject, identifier):
        with self.connect() as db:
            row = db.execute('SELECT html FROM dashboards WHERE owner=? AND id=?', (self.owner(subject), identifier)).fetchone()
        return row[0] if row else None

    def create(self, subject, document):
        return self.save(subject, document, expected_revision=None)

    def save(self, subject, document, expected_revision):
        doc = document.model_copy(deep=True)
        reconcile(doc)
        doc.revision = 1 if expected_revision is None else expected_revision + 1
        doc.updated_at = now()
        encoded, html = doc.model_dump_json(), render_dashboard(doc)
        if len(encoded.encode()) + len(html.encode()) > 2_000_000:
            raise ValueError('Dashboard exceeds the 2 MB saved artifact limit. Request fewer observations.')
        owner = self.owner(subject)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if expected_revision is None:
                count = db.execute('SELECT count(*) FROM dashboards WHERE owner=?', (owner,)).fetchone()[0]
                if count >= 100:
                    raise ValueError('Saved dashboard limit reached (100). Delete an old dashboard first.')
                db.execute('INSERT INTO dashboards VALUES (?,?,?,?,?,?,?)', (doc.id, owner, doc.revision, doc.title, doc.updated_at.isoformat(), encoded, html))
            else:
                changed = db.execute('UPDATE dashboards SET revision=?,title=?,updated=?,document=?,html=? WHERE owner=? AND id=? AND revision=?', (doc.revision, doc.title, doc.updated_at.isoformat(), encoded, html, owner, doc.id, expected_revision)).rowcount
                if not changed:
                    raise Conflict('Dashboard changed. Reopen it before saving.')
        return doc

    def delete(self, subject, identifier, revision):
        with self.connect() as db:
            changed = db.execute('DELETE FROM dashboards WHERE owner=? AND id=? AND revision=?', (self.owner(subject), identifier, revision)).rowcount
            if not changed:
                raise Conflict('Dashboard changed. Reopen it before deleting.')
