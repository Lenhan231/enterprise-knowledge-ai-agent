# Deployment guide

This is a prototype deployment guide. Production identity management, durable
background ingestion, TLS termination and load testing still need deployment-
specific validation.

## Configuration

1. Install Python 3.11 and `uv`; run `uv sync --locked` from the repository.
2. Copy `.env.example` to `.env` without replacing an existing secret-bearing
   `.env`. Set `SUPABASE_URL`, server-only secret key, database URL, Groq key/model,
   embedding model, demo passwords and a random `AUTH_SECRET_KEY` of at least
   32 characters. `DOCUMENT_CHUNKING_STRATEGY` defaults to `sentence`; set it
   to `fixed` only when building a controlled fixed-window comparison corpus.
3. Apply the timestamped migrations in [`supabase/migrations/`](../supabase/migrations/)
   with the Supabase CLI. That directory is the single schema history; do not
   apply a second numbered SQL sequence. See
   [Database migrations](#database-migrations) below.
4. For local HTTP, `AUTH_COOKIE_SECURE=false` is suitable for development only.
   Set it to `true` behind HTTPS. Do not expose `SUPABASE_SECRET_KEY` or
   `DATABASE_URL` to browser code or commit `.env`.

## Run locally

```bash
uv sync --locked
PYTHONPATH=src uv run uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

Check `GET /health`, sign in with each configured demo role, and verify role-
scoped Q&A, upload, admin source review and Commerce analytics against the target
database. A healthy process response does not prove that database, embeddings,
LLM, storage or RBAC are healthy; exercise those flows as well.

## Database migrations

The canonical history is `supabase/migrations/`. For a new project, apply the
files in timestamp order with `npx supabase db push --db-url "$DATABASE_URL"`.
Set `DATABASE_URL` in the shell from the local environment; never commit or
print it. Before deploying, inspect `npx supabase migration list` and compare
it with the target database. The read-only catalog check
`.venv/bin/python tools/retrieval/check_vector_repository_integration.py` validates the
pgvector tables and repository mapping.

The configured project predates complete migration tracking. Several schema
changes were already present remotely but had no canonical file or history
entry; the history is reconciled from verified catalog state. Use
`supabase migration repair --status applied <version>` only for a version whose
schema is already present; it updates migration tracking and does not run the
SQL. New schema changes must be added as timestamped files and deployed with
`db push`.

The read-only integration check also compares the exact timestamped versions
in the local directory with `supabase_migrations.schema_migrations`. On
2026-09-28 it found 13 local and 13 remote versions with no missing or unknown
entries; the vector schema and repository mapping passed on 5,052 rows. Run
`uv run python tools/retrieval/check_vector_repository_integration.py` after migration
changes to repeat both checks. It never applies SQL or writes test rows.

## Docker

With Docker Compose installed and a configured `.env`, run the backend directly
on loopback:

```bash
docker compose up --build web
```

To include the Nginx reverse proxy profile, use:

```bash
docker compose --profile proxy up --build
```

The proxy is available at `http://127.0.0.1:8080`; direct backend development
access remains on `http://127.0.0.1:8000`. `docker/nginx.conf` allows requests
up to the upload limit, forwards standard client/protocol headers, and sets
basic browser security headers. Configure TLS termination at the deployment
edge and set `AUTH_COOKIE_SECURE=true` before exposing the app beyond localhost.
The proxy forwards WebSocket upgrades for `/ws/ask`; the authenticated local
Uvicorn path has been exercised through a cited knowledge answer. CI also
builds the container, validates Nginx, and runs authenticated HTTP/WebSocket
smoke checks through the Docker proxy.

The web service uses the configured external database and Supabase services.
The optional `local-db` profile starts plain PostgreSQL with pgvector:
`docker compose --profile local-db up --build`. It is not a clean local
deployment of this app: the migration history also creates a private bucket in
Supabase's `storage.buckets`, and uploads require the Supabase Storage API. This
profile cannot apply the full schema or verify uploads end to end. Use the
linked Supabase project for app integration; treat local PostgreSQL as a
lower-level vector experiment only. The development host has no Docker CLI, so
local Compose/image/Nginx runtime validation is unavailable here. The proxy
container path is runtime-verified in CI; this is not a hosted deployment.

## Hosting scope

Hosted deployment is outside this prototype's proposal scope. Provider-specific
Render/Vercel deployment configs have been removed; validate the application
locally and through the Docker/Nginx CI path above.

## Operations boundary

An admin agent-monitoring console is available in the app, backed by
privacy-minimized event rows; it is not centralized production observability.
The chat UI retains its REST fallback when WebSocket upgrades are unavailable.
There is no production load-tested profile. The in-process smoke benchmark in
`technical/agents-and-evaluation.md` measures only the local prototype and is
not a production capacity claim. `/health` confirms the process responds; it is
not a full dependency health check.
