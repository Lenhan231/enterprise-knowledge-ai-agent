# Shared dashboard persistence

The backend stores completed dashboards in Supabase PostgreSQL using `DATABASE_URL` when configured.
`DASHBOARD_STORAGE_BACKEND=postgres` explicitly selects this backend; unavailable storage returns HTTP 503
and never silently starts an empty SQLite store. `sqlite` remains available for offline development.

Apply `supabase/migrations/20261116120100_persistent_user_dashboards.sql` before deploying the backend.
The application already uses server-verified session subjects, not Supabase Auth UUIDs. Ownership keeps
the existing SHA-256 subject identifier, so signing out, restarting or changing backend does not change it.
No browser Supabase key or Supabase Auth migration is needed.

The table is in `dashboard_private`, with no public/anon/authenticated access. Each operation opens a bounded
database connection, switches to the non-login `dashboard_store` role, and sets the verified owner for that
transaction. Forced RLS applies to reads and both sides of writes. The configured backend role must be
allowed to `SET ROLE dashboard_store`; the migration grants this to the existing `postgres` connection role.
All reads/writes also filter owner explicitly. The analytics read-only role receives no dashboard privileges.

Document and HTML save atomically. Optimistic revisions prevent stale edits/deletes. A transaction-scoped
owner lock preserves the 100-dashboard limit across backend processes; the 2 MB limit remains enforced
by both the application and database. Network operations run outside the API event loop.

## Existing dashboards

Copy each backend's SQLite database before replacing its container. Import it with:

```powershell
.venv/Scripts/python.exe scripts/agents/migrate_dashboard_storage.py artifacts/local/dashboards/dashboards.sqlite3
```

`scripts/deploy/deploy.sh` performs an online SQLite backup before restarting each backend, retains the
private backup under `artifacts/local/dashboard-backups`, and imports it after the new image starts.

Import retains IDs, owners, revisions, timestamps, documents and HTML. It never replaces records already
in Supabase, never deletes the source, and can be repeated. Existing records with divergent local edits
must be reviewed rather than silently overwriting a shared revision. Previously deleted container files
cannot be recovered by this migration.

## Verification

```powershell
$env:PYTHONPATH = 'src'
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_dashboard*.py'
```

Live tests are opt-in: set `DASHBOARD_POSTGRES_TEST_URL` to a migrated integration database and run
`test_dashboard_postgres_live.py`. They use randomly named users and remove only their own records.
They verify cross-connection persistence, owner isolation, RLS without an owner predicate, anonymous
denial, concurrent edits, concurrent quota enforcement and repeatable SQLite import.
