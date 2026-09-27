# Deployment guide

This is a prototype deployment guide. Production identity management, durable
background ingestion, TLS termination and load testing still need deployment-
specific validation.

## Configuration

1. Install Python 3.11 and `uv`; run `uv sync --locked` from the repository.
2. Copy `.env.example` to `.env` without replacing an existing secret-bearing
   `.env`. Set Supabase URL, server-only secret key, database URL, Groq key/model,
   embedding model, demo passwords and a random `AUTH_SECRET_KEY` of at least
   32 characters. `DOCUMENT_CHUNKING_STRATEGY` defaults to `sentence`; set it
   to `fixed` only when building a controlled fixed-window comparison corpus.
3. Apply the SQL migrations in `src/database/migrations/` in numeric order,
   then apply the supplemental Supabase migrations listed in
   [`src/database/migrations/README.md`](../src/database/migrations/README.md).
   The dated folder contains a few mirrors of numbered migrations; do not apply
   those mirrors a second time. The supplemental migrations add the private
   bucket's full supported-format allowlist and parsed-chunk table/grants.
4. For local HTTP, `AUTH_COOKIE_SECURE=false` is suitable for development only.
   Set it to `true` behind HTTPS. Do not expose `SUPABASE_SECRET_KEY` or
   `DATABASE_URL` to browser code or commit `.env`.

## Run locally

```bash
uv sync --locked
PYTHONPATH=src uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Check `GET /health`, sign in with each configured demo role, and verify role-
scoped Q&A, upload, admin metric review and analytics against the target
database. A healthy process response does not prove that database, embeddings,
LLM, storage or RBAC are healthy; exercise those flows as well.

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
The optional local PostgreSQL service is available with
`docker compose --profile local-db up --build`; configure `DATABASE_URL` for
that database and apply the migrations before using the app. Compose/container
build and startup have not been runtime-verified on this development machine.
The CI workflow now validates the Compose profile, builds the app image, and
runs `nginx -t`. The latest GitHub Actions runs visible to `gh run list` are
older Copilot workflows on other branches; this feature branch has no remote
tracking branch, so this CI workflow has not yet run for the current source.
The development host also has no Docker CLI, so local Compose/image/Nginx
runtime validation is unavailable here.

## Operations boundary

An admin agent-monitoring console is available in the app, backed by
privacy-minimized event rows; it is not centralized production observability.
There is no configured CI/CD deployment target or production load-tested
profile. The in-process smoke benchmark in
`technical/agents-and-evaluation.md` does not validate a deployed server. Before
public exposure, configure TLS termination at the edge, restrict network access
to PostgreSQL and Supabase secrets, and validate backups, retention, resource
limits and recovery against the chosen hosting environment. Do not treat
`/health` as a full dependency health check.
