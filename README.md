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
- src/document_processing: Docling parser with VietOCR recognition, RapidOCR line detection, and shared normalization
- tools/ingestion: seed ingestion orchestration and source-specific CLI workflows
- src/core/document_processing/chunking: shared chunk splitting and section metadata
- src/core/database: PostgreSQL repositories and table persistence
- Supabase `document_preprocessing_test` schema: isolated Upload Test runs and parser outputs
- src/core/retrieval and src/core/rag: role-scoped hybrid search and grounded answers
- src/core/agents: runtime router for grounded QA, analytics, hybrid reports and dashboard data
- [CLI tools](tools/README.md): reproducible CLI entry points grouped by workstream; see the [repository map](docs/technical/repository-ownership.md) for ownership and shared contracts
- docker-compose.yml: FastAPI service; optional pgvector-only database profile (not the full Supabase stack)

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
documents or use production upload. Upload Test compares rendered pages and
tables across Built-in, PP-StructureV3, MinerU, and Docling. Each
parser has separate settings; cleanup, metadata normalization, and parser
chunking are shared. It stops before tokenization, embedding, and vector creation.
Tesseract settings appear only for the Built-in profile; Paddle and
MinerU expose their own settings. The optional DocLayout-YOLO overlay is
diagnostic only; install it with `uv sync --extra layout-yolo`.
MinerU Upload Test runs the local Basic tier through `mineru-kit`. Install MinerU
in an isolated environment, then set `MINERU_LOCAL_CLI` to that environment's
`mineru-kit` executable and `MINERU_LOCAL_HOME` to its model-cache home in `.env`.
Download the Basic ONNX models into that home before running Upload Test. MinerU
models are independent of the application's Python environment; see the
[MinerU local setup guide](https://opendatalab.github.io/MinerU/quick_start/).
MinerU test runs stay isolated from production ingestion.

Corpus coverage and passage quality are computed from the indexed Supabase
data. Do not treat the demo credentials as a production identity-management
system. See the [user guide](docs/user-guide.md) for Q&A, decision-support,
upload, OCR review, role access, and troubleshooting steps.

## Document storage and access model

Original user-uploaded PDF, Office, text and image documents are stored in a
private Supabase Storage bucket;
PostgreSQL stores document metadata, processing state, and role assignments.
Parser output is retained in `document_parser_chunks` before embeddings;
embedded passages in `document_chunks` support retrieval. `/api/documents/parser-handoff`
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
supported. The production document-processing container uses VietOCR recognition
with RapidOCR line detection; Tesseract remains an available OCR override. Extracted
PDF and Office tables are stored separately, and OCR-derived table metadata keeps
the engine and settings used. See
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
