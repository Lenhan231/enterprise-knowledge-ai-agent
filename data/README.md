# Dataset workflows

## Vinamilk enterprise corpus

`data/vietnam_enterprises/manifest.json` is a source-backed corpus for one
enterprise: Vinamilk. All 25 manifest sources are now downloaded, parsed and
indexed: annual reports for 2020–2024, sustainability reports for 2020–2025,
corporate-governance reports for 2020–2025, current governance/policy documents,
three operating policies and a product page. The read-only metadata audit
checked 4,750 chunks with no manifest propagation mismatches. Two image-based
2026 governance PDFs completed the production Tesseract OCR path. These are
public materials; synthetic RBAC assignments are demo controls and do not
represent Vinamilk's real internal permissions or private records. Existing
retrieval/embedding benchmark artifacts were collected before the ten
governance sources were ingested; rerun them against the expanded corpus before
comparing with those baseline scores.

Download the source documents locally (raw files are not committed):

```bash
.venv/bin/python scripts/download_vietnam_enterprise_corpus.py
```

Download a controlled subset by manifest IDs when source validation or
incremental ingestion is needed:

```bash
.venv/bin/python scripts/download_vietnam_enterprise_corpus.py \
  --ids VNM-AR-2020-VI VNM-AR-2021-VI VNM-AR-2022-VI VNM-AR-2023-EN
```

The downloader validates PDFs and HTML and writes files under
`data/raw/vietnam_enterprises/vnm/`. Re-ingest after changing the manifest or
source files:

```bash
.venv/bin/python scripts/ingest_vietnam_enterprise_corpus.py
```

The ingestion command converts selected sources to page-aware chunks, creates
embeddings, upserts metadata/RBAC roles, and atomically replaces each
document's chunks. Each manifest document is marked `processing` before parse
and persistence, `ready` only after both chunks and extracted tables finish, or
`failed` on error. Retrieval only returns `ready` documents, so partial writes
stay hidden; rerun the same manifest ID to replace them. PDF bulk ingestion
and uploads use the page-aware PyMuPDF parser with Vietnamese/English Tesseract
OCR for pages under 50 native-text
characters, and mixed pages under 500 characters when raster images cover at
least 25% of the page. OCR text is appended to native text on mixed pages and the
extraction method is recorded in chunk metadata. Seed PDF table rows are stored
in `public.extracted_tables` and `public.extracted_records`; uploads use the
same structured store. Retrieval filters allowed roles before ranking and
prioritizes an explicitly requested single fiscal year. It requires
the project's `DATABASE_URL`, the `documents.allowed_roles` column from
migration 004, and the configured embedding model.

The native-text heading heuristic populated `section_title` on 3,773/3,780
chunks (99.8%) across the 11 indexed annual and sustainability reports after
re-ingestion. Seven chunks had no detected heading; this is coverage, not a
precision/recall assessment. Token-aware splitting now keeps every stored
report chunk within the configured 512-token model limit. OCR-only headings and
parent sections remain unsupported.

All manifest URLs point to Vinamilk's own report, sustainability, policy, or
product pages. Check the original source link shown in the UI when using an
answer.

The app reads its single-company scope from the manifest's top-level `company`
and applies that filter to document listings, analytics/review data, routed QA,
and new uploads. The shared Supabase database still contains 19 ready FPT
documents from an earlier corpus; they are preserved in storage but excluded
from this Vinamilk demo. The Docker image includes only this manifest, not the
downloaded corpus files.

The dashboard reads verified financial metrics from
`public.extracted_financial_metrics`, not from `analytics.json`. Migration 005
defines the table. Extracted candidates retain source quote/page provenance
and remain `needs_review` until checked. `analytics.json` is not a dashboard
source.

User-uploaded originals go to the private `enterprise-documents` Supabase
Storage bucket. PostgreSQL stores document metadata, RBAC assignments, Storage
path, uploader, and processing status. Uploads begin as `uploaded` and are not
searchable after page-aware text extraction and embeddings are persisted to
`document_chunks`. The upload processor supports PDF, DOCX, PPTX, XLSX, TXT,
Markdown, PNG, JPEG and TIFF; it uses Tesseract for image-only scans and stores
PDF/Office tables separately from chunks. The upload API requires the
server-only `SUPABASE_SECRET_KEY`
and an uploader demo identity. KPI candidates remain pending review until an
admin confirms the value and unit. Rebuild report evidence without database
writes with `uv run python scripts/process_vinamilk_financial_reports.py
--dry-run`. The 2026-09-26 smoke summary is in
[`artifacts/evaluation/vinamilk-metric-candidate-smoke.json`](../artifacts/evaluation/vinamilk-metric-candidate-smoke.json);
it measures candidate coverage, not extraction accuracy. Existing database
review rows may include older per-page duplicates; dry-run does not remove or
rewrite them.

The report processor also accepts `--ids <document_id...>` for a controlled
refresh. Large-font PDF number spans are matched to nearby labels for infographic
KPI cards that native reading order otherwise loses; table and text extraction
remain the paths for statements and narrative. These are suggestions only. A
controlled save looks like:

```bash
.venv/bin/python scripts/process_vinamilk_financial_reports.py \
  --ids VNM-AR-2024-VI --save-candidates
```

This stores current candidates as `needs_review`; it does not publish KPIs. A
2026-09-27 rerun for `VNM-AR-2024-VI` stored six current source-linked candidates;
two headline values came from page 2 (61.824 and 9.453, in the report's
displayed `tỷ đồng` unit). Value/unit normalization still requires admin review.
Migration 009 preserves unmatched older pending evidence as `superseded`, not
`rejected`, when that document is reprocessed.

## Apple corpus

The `documents` table in Supabase is the source of truth for the Apple corpus
manifest. Raw downloads and generated Markdown are local artifacts and are not
committed.

## Prerequisites

- Set `DATABASE_URL` in `.env`.
- Apply the SQL migrations in `src/database/migrations/`.
- Configure the embedding model required by the ingestion pipeline.

## Review 1 corpus

`scripts/download_apple_corpus.py` downloads these default document IDs:

- `APL-CMP-003`
- `APL-CMP-004`
- `APL-PRC-002`
- `APL-PRC-015`
- `APL-ENV-002`

Download the frozen subset into a dedicated directory:

```bash
python scripts/download_apple_corpus.py \
  --output data/raw/apple_review1
```

The downloader reads metadata from Supabase, validates the PDF signature, and
skips existing files. Use `--force` to replace existing downloads.

Download specific document IDs when needed:

```bash
python scripts/download_apple_corpus.py \
  --ids APL-CMP-003 APL-PRC-002 \
  --output data/raw/apple_review1
```

## Ingestion

Parse, chunk, embed, and persist the Review 1 subset:

```bash
python scripts/ingest_apple_corpus.py \
  --input data/raw/apple_review1 \
  --output data/processed/apple_review1
```

For a small metadata check, ingest one file:

```bash
python scripts/ingest_apple_corpus.py \
  --file data/raw/apple_review1/compliance/apl-cmp-003_anti_corruption_policy.pdf \
  --output data/processed/apple_review1
```

Re-ingestion is idempotent by `document_name`: existing chunks for that file
are deleted and replaced in one transaction, and each document starts at
`chunk_index = 0`.

## Evidence checks

Summarize chunk coverage:

```sql
select
    metadata->>'document_id' as document_id,
    count(*) as chunk_count,
    min(chunk_index) as first_index,
    max(chunk_index) as last_index,
    min((metadata->>'page_number')::int) as first_page,
    max((metadata->>'page_number')::int) as last_page
from document_chunks
group by metadata->>'document_id'
order by document_id;
```

Inspect representative provenance:

```sql
select
    chunk_index,
    metadata->>'document_id' as document_id,
    metadata->>'source_document' as source_document,
    metadata->>'page_number' as page_number,
    metadata->>'token_count' as token_count,
    metadata->>'section_title' as section_title,
    metadata->>'parent_id' as parent_id
from document_chunks
where metadata->>'document_id' = 'APL-CMP-003'
order by chunk_index
limit 5;
```

## Known limitations

- The verified ingestion path currently supports PDF files only.
- Existing Review 1 Apple chunks predate native-text heading extraction and
  need re-ingestion if populated `section_title` is required there.
- Hierarchical parent sections are not persisted, so `parent_id` is `null`.
- OCR, layout-aware parsing, and table extraction are not part of the Review 1
  baseline.

## Retrieval checkpoint

Use `RetrievalService.retrieve(RetrievalRequest(query=question, top_k=5))`
with these cross-document questions:

```text
What standards must third parties working with Apple follow?
What obligations does a supplier have regarding subcontractors?
What requirements apply to supplier personnel?
How does Apple's anti-corruption policy relate to third parties?
```

Inspect `source`, `location.chunk_index`, `score`, and full `text` in each item of
`RetrievalResponse.results` before expanding to the rest of the manifest.
The repeatable checkpoint command is:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/check_apple_retrieval.py
```

Inspect `document_name`, `chunk_index`, `similarity_score`, metadata, and chunk
content before expanding beyond the Review 1 subset.
