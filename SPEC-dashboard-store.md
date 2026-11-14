# Spec: dashboard-store

Objective: persist private, editable dashboard snapshots and rendered HTML outside the analytics database.

Use a standard-library SQLite artifact store under configurable `DASHBOARD_STORAGE_DIR` (default ignored `artifacts/local/dashboards`). Store document JSON and rendered HTML atomically, indexed by owner and UUID, with optimistic revision checks. Limit one saved bundle to 2 MB and 100 dashboards per owner. List/load/update/delete never cross owner boundaries. Retain data timestamps; opening does not query providers or refresh data.

Interface: create/load/list/save/delete with verified owner subject; save requires the expected revision. Immutable query results cannot be supplied through presentation-edit requests. Query refresh and changed filters go through dashboard-build and the SQL agent again. Local SQLite is artifact persistence, not a Supabase/analytics schema change. Production needs a durable configured volume and a storage decision for multiple app instances.

Implementation: `src/core/dashboards/store.py`, authenticated `src/app/dashboards.py`. Reuse app session authentication, analytics permission and origin checks. Parameterize every storage query.

Verify: `.venv/Scripts/python.exe -m unittest discover -s tests -p test_dashboard*.py`. Test reopen, revision conflicts, owner isolation, unauthorized access, stored HTML and malformed edit bodies. No credentials or dashboard data in public static files.
