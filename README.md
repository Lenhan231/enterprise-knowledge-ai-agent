Enterprise Knowledge AI Agent

Prototype for source-grounded enterprise document Q&A and business analytics,
using a role-filtered PostgreSQL/pgvector corpus and a FastAPI dashboard.

Quick start

1. Create a Python virtualenv and install dependencies:

```bash
uv sync
```

2. Copy `.env.example` to `.env` and fill in the Supabase URL/secret, database
   URL, provider key, and demo credentials described in
   [`docs/deployment-guide.md`](docs/deployment-guide.md#configuration). The
   local command below explicitly loads `.env`; Uvicorn does not load it
   automatically.

3. Run the FastAPI app:

```bash
PYTHONPATH=src uvicorn app.main:app --reload --env-file .env --port 8000
```

Open `http://localhost:8000` for the Enterprise Intelligence dashboard.
The UI reads the indexed corpus and role-scoped, verified analytics from Supabase.

Project layout

- src/app: FastAPI routes and dashboard UI
- src/core/document_processing: seed ingestion orchestration and format processors
- src/core/chunking: shared chunk splitting and section metadata
- src/core/database: PostgreSQL repositories and table persistence
- src/core/retrieval and src/core/rag: role-scoped hybrid search and grounded answers
- src/core/agents: runtime router for grounded QA, analytics, hybrid reports and dashboard data
- [scripts](scripts/README.md): reproducible CLI entry points grouped by workstream; see the [repository map](docs/technical/repository-ownership.md) for ownership and shared contracts
- docker-compose.yml: FastAPI service; optional pgvector-only database profile (not the full Supabase stack)

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
- Tester: isolated OCR Lab only; test PDFs and parser output are not added to the corpus.
- Admin: analyst access plus the role permission matrix.

Configure `DEMO_TESTER_USERNAME` / `DEMO_TESTER_PASSWORD` to enable the Tester
login. Tester can run OCR tests and inspect saved test runs, but cannot browse
documents or use production upload. The OCR Lab tab compares rendered source
pages with parser chunks and extracted tables.

Run `PYTHONPATH=src uv run uvicorn app.main:app --reload --env-file .env --port 8000` and open
`http://localhost:8000`. Corpus coverage and passage quality are computed
from the indexed Supabase data. Do not treat the demo credentials as a
production identity-management system.

## Document storage and access model

Original user-uploaded PDF, Office, text and image documents are stored in a
private Supabase Storage bucket;
PostgreSQL stores document metadata, processing state, and role assignments.
Parser output is retained in `processed_document_chunks` before embeddings;
embedded passages in `document_chunks` support retrieval and source-linked
metric evidence. Financial and business candidates live in
`extracted_financial_metrics` and `business_metric_evidence`; only verified
rows feed analytics and the SQL decision-support agent. Verified financial and
business evidence keeps its source page, quote/scope, indexed `source_chunk_id`,
chunk index, and a hash of the exact source chunk. The manifest is
the source registry for public seed data, not a dashboard data source. User
uploads go through `/api/documents/upload`; PDF parser output is chunked and
indexed, then the business-metric extractor proposes only decision-domain
primary KPIs for admin review. Admins can inspect each source chunk before
verification.
Vinamilk's source-backed business metric extraction, provenance and decision-question coverage are documented in [`docs/technical/vinamilk-milk-supply-metrics.md`](docs/technical/vinamilk-milk-supply-metrics.md).

The upload route requires `SUPABASE_SECRET_KEY` on the server (legacy
`SUPABASE_SERVICE_ROLE_KEY` is also accepted), an
`enterprise-documents` bucket provisioned by `supabase/migrations/`, and
`DEMO_UPLOADER_USERNAME` / `DEMO_UPLOADER_PASSWORD` (or an admin login). Never
expose the secret key to frontend code. Text-based PDFs are extracted page by
page, embedded and saved to `document_chunks` with their selected roles before
the upload completes. PDF/DOCX/PPTX/XLSX/TXT/Markdown/PNG/JPEG/TIFF are
supported. Tesseract handles scanned-page and image text OCR; extracted PDF and
Office tables are stored separately. Table OCR uses PSM 3 for PDFs and PSM 6
for direct image uploads based on a small labeled pilot; OCR-derived table
metadata keeps the engine and settings used. See
[`docs/technical/document-processing.md`](docs/technical/document-processing.md)
for the evaluation and limitations. KPI candidates stay pending until an admin
verifies their value and unit. See [`docs/README.md`](docs/README.md) for
proposal coverage and the technical guide to processing, chunking, embeddings,
retrieval, agents and evaluation.
