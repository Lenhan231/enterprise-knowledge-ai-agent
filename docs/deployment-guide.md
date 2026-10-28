# Deployment guide

This is a prototype deployment guide. Production identity management, durable
background ingestion, TLS termination and load testing still need deployment-
specific validation.

## Configuration

1. Install Python 3.11 and `uv`; run `uv sync --locked --extra docling` from the repository.
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
uv sync --locked --extra docling
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

The deployment contains four backend services, each built from its own Dockerfile:
`backend-api`, `document-processing`, `embeddings`, and `reranker`.
Supabase remains external; no local database or frontend is started.

1. Configure `.env` as above and generate `INTERNAL_SERVICE_TOKEN` with
   `python -c "import secrets; print(secrets.token_hex(32))"`. Set the generated
   value in `.env`; never commit it or send it to the frontend. Existing `.env`
   files need this new variable added. Internal services receive only this
   token and their model configuration, not Supabase or LLM secrets.
2. Run `docker compose config --quiet`, then `docker compose build` and
   `docker compose up -d --wait --wait-timeout 1800`.
3. Check `docker compose ps`, `docker compose logs --tail=50`, and
   `curl http://127.0.0.1:8000/health`. Model downloads can make first startup
   slow; subsequent starts reuse named cache volumes. No inference weights
   are baked into images. Parser models may download on the first upload.
4. Run `docker stats --no-stream` at idle, during a chat and during an OCR
   upload to size the host. Splitting containers does not guarantee a smaller
   total RAM requirement. Use one inference process per container initially.

The API listens on loopback port 8000. Internal services publish no host ports
and require the shared service token. Dependency health checks wait for model
loading before starting the API. The API retains tokenizer support but does
not install PyTorch or Docling, and its image excludes static frontend files.
Public API paths, authentication, roles and storage ownership remain with the
API. Internal HTTP calls have finite timeouts; parsing can take up to 600 seconds.

For optional local Nginx ingress run
`docker compose --profile proxy up -d --wait --wait-timeout 1800` and use
`http://127.0.0.1:8080`. It forwards backend requests to `backend-api`,
allows 51 MiB request bodies and uses 660-second upstream timeouts for uploads.
Configure HTTPS termination at the deployment edge before public use and set
`AUTH_COOKIE_SECURE=true`. Loopback ports require a host proxy/tunnel; do not
point a public Vercel deployment directly at localhost.

## Vercel connection

The existing Vercel configuration in `src/app/static/vercel.ts` uses
`NGROK_URL` to rewrite `/api/*` and `/ws/*` to the backend. Set that existing
Vercel environment variable to the backend's reachable HTTPS URL and redeploy
the frontend. Keep the configured `TRUSTED_FRONTEND_ORIGINS` limited to the
actual frontend domains. Verify login, role restrictions, chat, reports,
dashboard, upload, parser handoff, Upload Test and previews through that
frontend before cutting over. Current chat uses `/api/agents/chat`; this main branch does not register
a `/ws/ask` endpoint. Keep Supabase secrets
server-only. No frontend files need to be rebuilt as backend containers.

## Safe replacement and rollback

The former monolithic Dockerfile and module-check Dockerfiles are replaced by
runtime images. Old module-check and local-db Compose profiles no longer exist.
After the replacement passes integration checks, remove only the inspected
obsolete project containers (`web`, `app`, `db`); retain the previous app image
until cutover is verified. Do not globally prune Docker, delete source files,
or use `down -v`: old database volumes and uploaded documents must survive.
`docker compose down` stops the replacement without deleting caches. Restore
the prior Compose/Dockerfile revision and app image for rollback if needed.

## Operations boundary

An admin agent-monitoring console is available in the app, backed by
privacy-minimized event rows; it is not centralized production observability.
The chat UI retains its REST fallback when WebSocket upgrades are unavailable.
There is no production load-tested profile. The in-process smoke benchmark in
`technical/agents-and-evaluation.md` measures only the local prototype and is
not a production capacity claim. `/health` confirms the process responds; it is
not a full dependency health check.
