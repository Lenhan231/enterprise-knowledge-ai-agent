Enterprise Knowledge AI Agent

Prototype for source-grounded enterprise document Q&A and business analytics,
using a role-filtered PostgreSQL/pgvector corpus and a FastAPI dashboard.

Quick start

1. Create a Python virtualenv and install dependencies:

```bash
uv sync
```

2. Run the FastAPI app:

```bash
PYTHONPATH=src uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000` for the Enterprise Intelligence dashboard.
The UI reads the indexed corpus and role-scoped, verified analytics from Supabase.

Project layout

- src/app: FastAPI routes and dashboard UI
- src/core/document_processing: seed ingestion orchestration and format processors
- src/core/database: PostgreSQL repositories and table persistence
- src/core/retrieval and src/core/rag: role-scoped hybrid search and grounded answers
- src/core/agents: runtime router for grounded QA, analytics, hybrid reports and dashboard data
- docker-compose.yml: FastAPI service; optional local pgvector database profile

## Dataset

The current demo uses a reproducible, public Vinamilk corpus documented in
[`data/README.md`](data/README.md). Raw source documents and generated Markdown
stay local and are not committed.

## Local demo access

The app includes demo RBAC roles. Set `AUTH_SECRET_KEY` to a random value at
least 32 characters long, then set each
`DEMO_{VIEWER,ANALYST,SUSTAINABILITY_ANALYST,ADMIN}_USERNAME`
and matching password in `.env`. Set `AUTH_COOKIE_SECURE=true` behind HTTPS.
Passwords are kept in environment configuration and are never exposed to the
browser. The demo has no user-registration or password-reset flow.

- Viewer: corpus overview and document questions.
- Analyst: viewer access plus the source-backed analytics dashboard.
- Admin: analyst access plus the role permission matrix.

Run `PYTHONPATH=src uv run uvicorn app.main:app --reload --port 8000` and open
`http://localhost:8000`. Corpus coverage and passage quality are computed
from the indexed Supabase data. Do not treat the demo credentials as a
production identity-management system.

## Document storage and access model

Original user-uploaded PDF, Office, text and image documents are stored in a
private Supabase Storage bucket;
PostgreSQL stores document metadata, processing state, and role assignments.
Processing outputs go to `document_chunks` and reviewable financial metrics go
to `extracted_financial_metrics`; only metrics marked `verified` appear in the
analytics endpoint. The manifest is the source registry for public seed data,
not a dashboard data source. User uploads go through `/api/documents/upload`.

The upload route requires `SUPABASE_SECRET_KEY` on the server (legacy
`SUPABASE_SERVICE_ROLE_KEY` is also accepted), an
`enterprise-documents` bucket provisioned by migration 005, and
`DEMO_UPLOADER_USERNAME` / `DEMO_UPLOADER_PASSWORD` (or an admin login). Never
expose the secret key to frontend code. Text-based PDFs are extracted page by
page, embedded and saved to `document_chunks` with their selected roles before
the upload completes. PDF/DOCX/PPTX/XLSX/TXT/Markdown/PNG/JPEG/TIFF are
supported. Tesseract handles scanned-page and image text OCR; extracted PDF and
Office tables are stored separately. KPI candidates stay pending until an admin
verifies their value and unit. See [`docs/README.md`](docs/README.md) for
proposal coverage and the technical guide to processing, chunking, embeddings,
retrieval, agents and evaluation.
