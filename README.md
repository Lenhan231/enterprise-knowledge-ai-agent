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

Open `http://localhost:8000` for the Commerce decision-support dashboard.
The UI reads the indexed corpus and live, role-scoped aggregates from Supabase.
Commerce competition data is synthetic; public operating references are external
examples, not policy for the synthetic business.

Project layout

- src/app: FastAPI routes and dashboard UI; isolated Upload Test API lives in `upload_test.py`
- src/document_processing: Docling parser with Tesseract OCR and shared normalization
- tools/ingestion: seed ingestion orchestration and source-specific CLI workflows
- src/core/chunking: shared text and table chunk creation
- src/core/database: PostgreSQL repositories and table persistence
- Supabase `document_preprocessing_test` schema: isolated Upload Test runs and parser outputs
- src/core/retrieval and src/core/rag: role-scoped hybrid search and grounded answers
- src/core/agents: runtime router for grounded QA, analytics, hybrid reports and dashboard data
- [CLI tools](tools/README.md): reproducible CLI entry points grouped by workstream; see the [repository map](docs/technical/repository-ownership.md) for ownership and shared contracts
- docker-compose.yml: backend API, document processing, chunking worker, embeddings and reranker; optional Nginx ingress. Frontend hosting remains on Vercel and data remains in Supabase.

Backend Docker quick start (configure `.env` first, including a random
`INTERNAL_SERVICE_TOKEN` shared only by the backend containers):

Apply `supabase/migrations/20261028090548_add_chunking_document_statuses.sql`
and `supabase/migrations/20261028091543_align_processing_outputs_with_parser.sql`
through the normal database migration workflow before starting the chunking
worker. It consumes `parsed` documents and leaves them `chunked`, without
embedding or retrieval activation. See the [worker guide](src/core/chunking/README.md#chunking-worker-service).

```bash
docker compose config --quiet
docker compose build
docker compose up -d --wait
curl http://127.0.0.1:8000/health
```

Each backend service has its own `docker/Dockerfile.<service>` and runtime.
Only the API publishes a host port. Model services use persistent caches and
load one model copy each; first startup downloads the configured weights.
The API calls those services instead of loading inference/OCR models itself.
Document processing remains synchronous; an unavailable service fails the
request rather than silently changing retrieval or parser behavior.
See [deployment instructions](docs/deployment-guide.md#docker) for Vercel,
HTTPS ingress, checks and safe retirement of old containers.

Chat responses include request-local stage timings under `metadata.latency`;
the backend also writes `agent_latency` JSON records to Docker logs. Values are
milliseconds, and `null` means the stage was skipped. Retrieval totals include
their child stages; parallel agent timings overlap and must not be summed to
estimate request time. Existing database telemetry still stores total handler
time only. After restarting the backend containers, run
`python scripts/operations/measure_pipeline_latency.py` to save two sequential
passes of ten questions and sampled container resources. The second pass also
benefits from the existing translation cache; it is not a load or quality test.

## Dataset and knowledge sources

The current business demo is centered on the Kaggle Datathon 2026 Round 1
Commerce schema. Its transactional and operational data is synthetic and is
kept in the private PostgreSQL `commerce` schema; it must not be described as
observed data from a real retailer. The importer copies source CSV fields
without recomputing competition metrics. `sample_submission.csv` is not loaded.
See [`tools/README.md`](tools/README.md).

Decision support uses public management cookbooks and attributed retailer or
platform operating examples, registered in
[`data/commerce_knowledge/manifest.json`](data/commerce_knowledge/manifest.json).
Management cookbooks are external decision methods, not policy for the
synthetic dataset; company practice references are attributed examples, and
platform rules apply only when that platform is in scope. Source scope and
reuse terms are recorded in the manifest.
Three additional generated PDFs define demo-only decision rules for inventory,
promotions, and logistics. Each page labels them synthetic; they exist to test
the policy-grounded agent flow and must never be presented as policy from a real
retailer. The rules intentionally use no fabricated numeric targets.
No government document is used as company policy. A synthetic scanned PDF may
demonstrate OCR/upload behavior only; it must be labeled synthetic and excluded
from business evidence.

## Local demo access

The app includes demo RBAC roles. Set `AUTH_SECRET_KEY` to a random value at
least 32 characters long, then set each
`DEMO_{VIEWER,ANALYST,SUSTAINABILITY_ANALYST,ADMIN}_USERNAME`
and matching password in `.env`. Set `AUTH_COOKIE_SECURE=true` behind HTTPS.
Passwords are kept in environment configuration and are never exposed to the
browser. The demo has no user-registration or password-reset flow.

- Viewer: corpus overview and document questions.
- Analyst and Sustainability Analyst: viewer access plus the source-backed analytics dashboard.
- Document Uploader: upload and classify documents; no document Q&A or analytics access.
- Tester: isolated Upload Test only; parser chunks and tables stay outside the corpus.
- Admin: analyst access plus upload, source review, access control, and knowledge-file management.

Configure `DEMO_TESTER_USERNAME` / `DEMO_TESTER_PASSWORD` to enable the Tester
login. Tester can run Upload Tests and inspect saved runs, but cannot browse
documents or use production upload. Upload Test runs Docling with configurable
Tesseract OCR, table structure, and device settings. It saves normalized parser
elements and tables without tokenization, embedding, or vector creation.

Corpus coverage and passage quality are computed from the indexed Supabase
data. Do not treat the demo credentials as a production identity-management
system. See the [user guide](docs/user-guide.md) for Q&A, decision-support,
upload, OCR review, role access, and troubleshooting steps.

## Document storage and access model

Original user-uploaded PDF, Office, text and image documents are stored in a
private Supabase Storage bucket;
PostgreSQL stores document metadata, processing state, and role assignments.
Normalized document-processing output (`metadata`, ordered `elements`, and
structured `tables`) is retained in `document_processing_outputs`; chunked
parser output is retained separately in `document_parser_chunks` before
embeddings. Embedded passages in `document_chunks` support retrieval.
`/api/documents/parser-handoff`
uses the same parser and writes the same public parser chunks and structured tables,
then leaves the document in `parsed` state for downstream tokenization and indexing.
The regular `/api/documents/upload` continues through embedding and retrieval indexing.
Uploads do not create
dashboard metrics: Commerce dashboard observations come from the private SQL
dataset, while uploaded and seeded documents provide policy and operating
context through RAG. The manifest is the source registry for public seed data,
not a dashboard data source. Regular uploads go through `/api/documents/upload`;
parser handoff stops after saving parser output for downstream processing.
Commerce references retain their publisher, applicability scope, and
decision-domain tags. Admins can inspect each source chunk in Processing.
The Admin **Knowledge Management** tab can change reader roles for each indexed
file, or remove and restore that file from AI retrieval. Role edits update
`documents.allowed_roles` and apply on the next retrieval without reprocessing
or re-embedding. Removing a file toggles `documents.knowledge_base_active`
without deleting the source file or parser chunks; OCR processing status remains
independent.
The commerce manifest controls the initial state
for public references, while later Admin changes persist across re-indexing.
Every upload is searchable through document Q&A. In the Admin upload form,
Commerce decision support is an optional additional classification. Commerce
references require a source type, publisher, applicability scope, and one or more decision areas; internal
document-kind/category tags are derived automatically, while fiscal year and
source URL are optional.
The Commerce dashboard loads only the selected domain's aggregates when an
analyst opens Analytics or switches domain; dashboard data is not queried as a
login prerequisite. Commerce decision support combines descriptive aggregates
from the private `commerce` schema with retrieved management methods and
attributed operating references. The dashboard excludes fields that failed the
current quality review and explicitly labels promotion comparisons as
non-causal. The Commerce source corpus and OCR demo progress are tracked in
[`docs/commerce-decision-support.md`](docs/commerce-decision-support.md).

The upload route requires `SUPABASE_SECRET_KEY` on the server (legacy
`SUPABASE_SERVICE_ROLE_KEY` is also accepted), an
`enterprise-documents` bucket provisioned by `supabase/migrations/`, and
`DEMO_UPLOADER_USERNAME` / `DEMO_UPLOADER_PASSWORD` (or an admin login). Never
expose the secret key to frontend code. Text-based PDFs are extracted page by
page, embedded and saved to `document_chunks` with their selected roles before
the upload completes. PDF/DOCX/PPTX/XLSX/CSV/TXT/Markdown/PNG/JPEG/TIFF are
supported. Tesseract handles scanned-page and image text OCR; extracted PDF and
Office tables are stored separately. Table OCR uses PSM 3 for PDFs and PSM 6
for direct image uploads based on a small labeled pilot; OCR-derived table
metadata keeps the engine and settings used. See
[`src/document_processing/docs/document-processing.md`](src/document_processing/docs/document-processing.md)
for the evaluation and limitations. Upload processing indexes source content;
it does not extract or publish dashboard KPIs. Successful uploads report page,
parser-passage, indexed-passage, OCR-passage and structured-table counts. Admins are taken to
the saved parser output for that document; each passage and table links to its
original PDF page for review. The isolated Upload Test additionally compares page
previews with parser chunks and tables without adding test files to the corpus.
See [`docs/README.md`](docs/README.md) for
current Commerce scope, verification status, limitations and the technical guide
to processing, chunking, embeddings, retrieval, agents and evaluation.
