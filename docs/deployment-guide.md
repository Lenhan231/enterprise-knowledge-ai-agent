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
scoped Q&A, upload, admin metric review and analytics against the target
database. A healthy process response does not prove that database, embeddings,
LLM, storage or RBAC are healthy; exercise those flows as well.

## Database migrations

The canonical history is `supabase/migrations/`. For a new project, apply the
files in timestamp order with `npx supabase db push --db-url "$DATABASE_URL"`.
Set `DATABASE_URL` in the shell from the local environment; never commit or
print it. Before deploying, inspect `npx supabase migration list` and compare
it with the target database. The read-only catalog check
`.venv/bin/python scripts/check_vector_repository_integration.py` validates the
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
`uv run python scripts/check_vector_repository_integration.py` after migration
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
Uvicorn path has been exercised through a cited knowledge answer. The Nginx
container itself still needs runtime verification.

The web service uses the configured external database and Supabase services.
The optional `local-db` profile starts plain PostgreSQL with pgvector:
`docker compose --profile local-db up --build`. It is not a clean local
deployment of this app: the migration history also creates a private bucket in
Supabase's `storage.buckets`, and uploads require the Supabase Storage API. This
profile cannot apply the full schema or verify uploads end to end. Use the
linked Supabase project for app integration; treat local PostgreSQL as a
lower-level vector experiment only. The development host has no Docker CLI, so
local Compose/image/Nginx runtime validation is unavailable here. Hosted
[CI run 36400367545](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/36400367545)
passed the test suite, Compose validation, application image build, `nginx -t`,
and an authenticated HTTP/WebSocket smoke through the running Docker Nginx proxy
on `main` at `109efd14`. The proxy container path is runtime-verified in CI;
this is not a Render/Vercel deployment.

## Hosted prototype on Render

Render is the lowest-setup option for a public prototype from this private GitHub
branch: connect the repository in the Render Dashboard, select a Web Service
with the Docker runtime and `docker/Dockerfile`, and set `/health` as its health
check. The container listens on `PORT` (defaults to 8000 for Compose). Render's
web service handles public TLS and accepts WebSocket upgrades on the same port;
deploying the separate Compose Nginx service is unnecessary for this topology.
The Nginx Compose profile remains useful for local/CI reverse-proxy validation.
Render supports private GitHub repositories, Docker builds, and inbound
WebSockets ([web service docs](https://render.com/docs/web-services),
[Docker docs](https://render.com/docs/docker),
[WebSocket docs](https://render.com/docs/websocket)).

The dashboard flow uses GitHub OAuth and does not need a Render API token. If
automating account operations through the API/CLI, create a scoped token in
Render and keep it out of chat, source files and `.env.example`. Enter runtime
secrets in the service's Environment settings: `DATABASE_URL`, `SUPABASE_URL`,
`SUPABASE_SECRET_KEY`, `GROQ_API_KEY`, `HUGGINGFACE_API_KEY`, and unique demo
passwords. The repository's [`render.yaml`](../render.yaml) Blueprint uses a
Free Singapore service, generates the auth secret, and uses hosted Hugging Face
inference to avoid loading embedding weights into the small web instance. It
marks provider credentials and demo passwords for entry in the Render
Dashboard. Set `AUTH_COOKIE_SECURE=true`; retain the configured
external Supabase database and private Storage bucket. Never add these values to
the image or repository.

Render's free service is suitable for a short smoke/demo only: it spins down
after 15 minutes idle and can take about a minute to wake; its filesystem is
ephemeral. Document uploads already go to Supabase Storage, so the service disk
is not the source of truth. Choose a paid compute plan only after checking the
current price and measuring memory under the embedding/OCR workload. Render's
free-plan behavior is described in its
[free service limits](https://render.com/docs/free).

## Operations boundary

An admin agent-monitoring console is available in the app, backed by
privacy-minimized event rows; it is not centralized production observability.
[`vercel.json`](../vercel.json) publishes the existing static UI from
`src/app/static`, aliases `/static/*` to that output, and proxies API and health
paths to the Render service. The chat UI retains its REST fallback if a hosting
proxy does not pass WebSocket upgrades. Configure the Vercel project with the
repository root and create the Render Blueprint from the same private GitHub
repository. Provider-side account linking, secret entry, first deployment, and
browser smoke testing remain required. There is no production load-tested
profile. The in-process smoke benchmark in
`technical/agents-and-evaluation.md` does not validate a deployed server. Before
public exposure, configure TLS termination at the edge, restrict network access
to PostgreSQL and Supabase secrets, and validate backups, retention, resource
limits and recovery against the chosen hosting environment. Do not treat
`/health` as a full dependency health check.
