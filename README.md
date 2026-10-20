# Enterprise Knowledge AI Agent

FastAPI serves the Knowledge and SQL agents. One LangGraph-backed router handles
automatic routing and the selected Knowledge, SQL, or Agentic mode. Streamlit
provides a small demo client for choosing a mode and viewing answers, rows, and
sources.

## Setup

```powershell
uv sync
```

Configure `.env` with the model key, document database, and least-privilege
commerce reader:

```text
GROQ_API_KEY=...
GROQ_MODEL=qwen/qwen3.8-27b  # optional; this is also the default
DATABASE_URL=postgresql://...            # existing VietStyle knowledge index
ANALYTICS_DATABASE_URL=postgresql://...  # read-only commerce role
```

`ANALYTICS_DATABASE_URL` must use a non-privileged role with `USAGE` on
`commerce` and `SELECT` on the approved commerce tables. The application checks
this role at startup. Keep credentials on the backend; the Streamlit client
only calls FastAPI.

For local testing, opt in to the development analytics identity in `.env`:

```text
APP_ENV=development
ALLOW_DEV_ANALYTICS=true
DEV_ANALYTICS_IDENTITY=local-analyst
```

This local identity is disabled outside `APP_ENV=development`. Production
requests need a server-authenticated `VerifiedIdentity` with `analytics:read`.

## Run the demo

Start the API in one terminal:

```powershell
uv run python -m uvicorn app.main:app --app-dir src --reload --port 8000
```

Start Streamlit in another:

```powershell
uv run streamlit run src/app/streamlit_ui.py
```

Open the Streamlit URL it prints (usually `http://localhost:8501`). Set
`API_BASE_URL` if FastAPI runs elsewhere; it defaults to
`http://127.0.0.1:8000`.

## API

`POST /api/chat` accepts a question and optional mode:

```json
{
  "question": "Show monthly revenue and COGS for 2022.",
  "agent_mode": "sql"
}
```

Modes are `knowledge`, `sql`, and `agentic`. Omit `agent_mode` or set it to
`auto` to keep the existing automatic routing behavior.

SQL mode generates a query from the approved `commerce.*` schema, validates it
before execution and again at the repository boundary, and runs it in a
read-only transaction with a five-second statement timeout. Results include
rows and database source evidence. Agentic mode uses the same LangGraph router
to select Knowledge, SQL, or both; each subagent is called no more than once.

## Knowledge data and evaluation

The existing VietStyle document index in Supabase is the knowledge source of
truth; the application does not maintain a second local corpus. See [data/README.md](data/README.md).
Run the existing VietStyle retrieval benchmark with its configured Supabase
environment:

```powershell
.venv\Scripts\python.exe evaluation/run_vietstyle_benchmark.py
```

To check the live commerce database and verify read-only enforcement:

```powershell
.venv\Scripts\python.exe scripts/smoke_test_supabase_analytics.py
```

The smoke test runs three generated, bounded queries and a write-blocking probe
inside a read-only transaction.
