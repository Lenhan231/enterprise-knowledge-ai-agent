# Dataset workflows

## Vinamilk enterprise corpus

`data/vietnam_enterprises/manifest.json` is a source-backed corpus for one
enterprise: Vinamilk. The 26 manifest sources include annual reports for
2020–2024, sustainability reports for 2020–2025,
corporate-governance reports for 2020–2025, current governance/policy documents,
three operating policies, a customer-service returns policy and a product page.
The read-only metadata audit checked a 25-document snapshot (4,750 chunks) with
no manifest propagation mismatches; the returns policy was subsequently
ingested as three chunks. Two image-based
2026 governance PDFs completed the production Tesseract OCR path. These are
public materials; synthetic RBAC assignments are demo controls and do not
represent Vinamilk's real internal permissions or private records. Historical
retrieval/embedding artifacts use different corpus snapshots and are not
directly comparable. The refreshed corpus runs and limitations are
listed in [`docs/README.md`](../docs/README.md) and the evaluation matrix.

The separate [`2011 Vietnamese scan diagnostic v2`](evaluation/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v2.json)
adds two visually transcribed balance-sheet pages to the signed income
statement case. The production-parser run removes embedded OCR text by
rasterizing each labeled page before processing, then scores selected row,
period and numeric-cell associations. It matches 17/17 rows, 34/34 numeric
cells, 6/6 period headers and 20/20 visually checked value-cell boxes on this
three-page, third-party packet. CER/WER is
reported only for the fully transcribed income-statement page; the other two
pages have targeted financial anchors rather than full-page text references.
The coordinate boxes derive from the source text layer and were visually
checked, not independently click-annotated.
This is supplemental single-source evidence, not a model-selection dataset.

The separate [`2011 scan diagnostic v4`](evaluation/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v4.json)
adds raster-derived boxes for 14 value cells across seven income-statement
rows. Those boxes were mapped from the exact 180-DPI clipped render and visually
checked without PDF text-layer assistance. The existing 20 balance-sheet boxes
remain text-layer-derived. The full three-page upload-parser check scored 33/34 cell locations, 17/17
rows and 34/34 values; its single miss is the 2011 dash with no useful parser
box. This remains single-reviewer evidence from one source packet.

The internal employee-access case is explicitly assigned the `employee` demo role; its expected answer preserves the official English Code of Conduct wording, including the source phrase “appropriate for the execution of their employees” rather than silently correcting that translation. The full routed-case runner records the selected role and switches demo accounts accordingly.

OCR benchmark labels are versioned separately under `data/evaluation/`.
[`vinamilk_ocr_ground_truth_v9.json`](evaluation/vinamilk_ocr_ground_truth_v9.json)
combines the eleven v8 regions with three full-page regions from a 2011
Vietnamese financial-statement scan packet. The four-engine v9 comparison
reuses v2/v8 predictions only after checking engine versions, settings, runtime
devices, and exact source/render hashes. Its references mix direct visual
transcription with text-layer-assisted, visually checked labels; it remains a
diagnostic and is not eligible for engine selection. Table cell counts measure
text presence, while exact-row recall measures a stricter linearized sequence;
neither establishes spatial cell reconstruction. See the reproducible merge
and score commands in
[`document-processing.md`](../docs/technical/document-processing.md#current-boundaries).

[`vinamilk_ocr_charter_scan_en_v1.json`](evaluation/vinamilk_ocr_charter_scan_en_v1.json)
isolates page 8 of the issuer-hosted, image-only 2026 Company Charter for a
four-engine paired diagnostic. Its English full-page transcription is from one
visual annotator and has not been independently reviewed; do not use it to
select an OCR engine. Its separate private Kaggle asset dataset is
`ltrngnhn/vinamilk-charter-scan-page8-assets` version 2. The paired raw reports
and comparison are linked in the technical processing notes.

[`vinamilk_ocr_ground_truth_v5.json`](evaluation/vinamilk_ocr_ground_truth_v5.json)
retains the five v4 reviewed regions and adds a visually checked 16-row,
two-period Vietnamese balance-sheet table from annual-report PDF page 91.
The new page is born-digital, not a physical scan. Its row labels and values
support exact row-recall scoring; they do not yet establish general table or
layout accuracy. Version 6, [`vinamilk_ocr_ground_truth_v6.json`](evaluation/vinamilk_ocr_ground_truth_v6.json),
corrects horizontal crops on both English image-only governance scans: v5 had
clipped printed text while retaining full-line transcriptions. The v6
Tesseract baseline gives Charter CER/WER 0.008830/0.042254 and governance-TOC
CER/WER 0.642038/0.322222. V5 scan-page scores and six-page CER/WER aggregates
are superseded; table-only scores remain valid because that crop is unchanged.
The new dataset uses a unique hash in rendered filenames so reruns do not
overwrite earlier paired inputs. All four engines have v6 reports paired on
the same six dataset/PDF/render hashes. Tesseract/EasyOCR/Surya/PaddleOCR
CER is 0.325961/0.176672/0.071090/0.088994 and WER is
0.259207/0.361190/0.143059/0.209632. Surya has the lowest errors in this
sample, but the engines ran on CPU across different hosts; latency and memory
are not controlled and no production winner is selected. The hash-checked
comparison and raw reports are linked from
[`docs/technical/document-processing.md`](../docs/technical/document-processing.md#current-boundaries).
See the paired-engine matrix and limitations in
[`docs/technical/document-processing.md`](../docs/technical/document-processing.md).

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
OCR for pages under 50 native-text characters, and mixed pages under 500
characters when raster images cover at least 25% of the page. Text OCR uses
PSM 11; scanned-table TSV word boxes use PSM 3. Mixed-page OCR is appended to
native text, and extraction method is recorded in chunk metadata. Seed PDF table rows are stored
in `public.extracted_tables` and `public.extracted_records`; uploads use the
same structured store. Retrieval filters allowed roles before ranking and
prioritizes an explicitly requested single fiscal year. It requires
the project's `DATABASE_URL`, the schema applied from the canonical
`supabase/migrations/` history, and the configured embedding model. See the
[database setup guide](../docs/deployment-guide.md#database-migrations).

The native-text heading heuristic populated `section_title` on 3,773/3,780
chunks (99.8%) across the 11 indexed annual and sustainability reports after
re-ingestion; that figure is limited to those report chunks. After exact-match
metadata backfills on eight governance reports, the 25-document report corpus
snapshot has 4,666/4,750 chunks with a title (84 null); this does not include
the later customer-service HTML policy. Token-aware splitting keeps all
stored report chunks within the configured 512-token model limit. Numbered
OCR headings are supported; unnumbered OCR-only headings and persisted parent
sections remain unsupported. The per-document counts are in the [read-only
coverage audit](../artifacts/evaluation/section-title-corpus-coverage-post-backfill-20260928.json);
coverage does not measure heading correctness.

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
`public.extracted_financial_metrics`, not from `analytics.json`. The table is
created by
`supabase/migrations/20260925143350_create_vinamilk_metrics_rbac_and_storage.sql`.
Extracted candidates retain source quote/page provenance
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
two headline values came from page 2 (the report prints `61.824` and `9.453`
with `tỷ đồng` units, using Vietnamese thousands punctuation). Preserve these
as text while reviewing; the admin must normalize them to `61824` and `9453`
before publication. See the [review input rules](../docs/user-guide.md#analytics-review).
`supabase/migrations/20260926190105_metric_candidate_superseding.sql` preserves
unmatched older pending evidence as `superseded`, not
`rejected`, when that document is reprocessed.

## Archived Review 1 corpus (legacy Apple dataset)

This is a retained, separate Review 1 experiment and is not part of the active
Vinamilk demo manifest or its 25-document dashboard/QA scope. Its download and
ingestion scripts remain for reproducing that earlier experiment; raw downloads
and generated Markdown are local artifacts and are not committed. Do not use
this legacy corpus as evidence for current Vinamilk evaluation.

## Prerequisites

- Set `DATABASE_URL` in `.env`.
- Apply the canonical timestamped SQL migrations in `supabase/migrations/`
  following the [database setup guide](../docs/deployment-guide.md#database-migrations).
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
