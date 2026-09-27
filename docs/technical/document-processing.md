# Document processing

## Flow

Seed documents and uploads enter different orchestration points, then use
format parsers, embeddings, and the same retrieval chunk/table persistence
layer. Upload originals live in private Supabase Storage; PostgreSQL stores
parser output separately from retrieval chunks, vectors, tables, and state.

Seed ingestion marks a document `processing` before parsing; it becomes
`ready` only after chunk replacement and extracted-table persistence both
succeed, and `failed` on an exception. Retrieval filters out non-ready rows, so
a partial multi-table write is not searchable. Rerunning that manifest ID
replaces its chunks and tables. The chunks, structured tables, and document
status use separate database transactions, so this status gate is the recovery
boundary rather than one cross-table transaction.

## Module boundaries

- `processors/document_processor.py` is the upload parser dispatcher. It
  validates Office ZIP resource limits, dispatches PDF to `PDFProcessor`,
  parses DOCX/PPTX/XLSX with the standard library, and handles plain text and
  image OCR. It returns chunks and structured tables; it does not persist them.
- `processors/pdf_processor.py` owns native PDF text, table extraction,
  optional layout analysis, and sparse-page OCR.
- `ingest_documents.py` adapts seed PDFs and HTML into token-bounded chunks.
  Seed PDFs reuse `PDFProcessor`; public HTML uses the local HTML text
  extractor.
- Upload orchestration in `app/main.py` stores originals, calls the dispatcher,
  persists parsed chunks/tables before tokenization and embedding, then writes
  vectors and metric candidates. The admin processing tab exposes saved parser
  output and metadata through a paginated, manifest-company-scoped endpoint.

Only these active paths are retained. The unused alternative Excel/image
processors and a second PDF-to-Markdown converter were removed so they cannot
be mistaken for supported production routes.

## Supported formats and extraction

`DocumentProcessor.SUPPORTED` currently lists PDF, DOCX, PPTX, XLSX, TXT, MD,
PNG, JPEG, and TIFF. DOCX/PPTX/XLSX are parsed from Open XML using the Python
standard library. Legacy binary XLS is not supported. The seed-corpus command
currently handles PDF and HTML; the Vinamilk reports are PDFs.

Office ZIP packages are checked before XML parsing: at most 10,000 entries,
100 MiB per member, 200 MiB expanded total, and a 200:1 member compression
ratio. Invalid Office ZIP/XML packages and these resource-limit violations
return a client error on upload rather than being reported as database outages.

PPTX parsing extracts slide text and slide tables into the common structured
table shape, with the slide number retained as page/table metadata. XLSX parsing
preserves explicit cell formulas, formula type/range attributes, and cached
values in the corresponding table metadata. Formula expressions are also
included in retrievable sheet text; cached values remain structured row values
because the parser does not recalculate workbooks. This does not recognize
mathematical notation embedded in PDF/images or establish formula calculation
correctness.

PDF handling uses PyMuPDF text and table extraction. Selective Tesseract OCR
uses `vie+eng`: OCR runs below 50 native-text characters, or below 500 when
raster images cover at least 25% of the page. Mixed-page OCR is appended to
native text. Chunk metadata records the extraction method. An optional Paddle
path exists, but production seed/upload configuration disables it; figure,
caption, formula and diagram understanding are not complete.

Tables are stored separately in `extracted_tables` and `extracted_records`.
They are raw parser results, not validated financial facts. Dashboard KPIs come
from admin-verified `extracted_financial_metrics` only.

Parsed upload chunks are stored in `processed_document_chunks` with extraction
metadata and an embedding-stage status. This preserves OCR/layout output if
tokenizer/model initialization or vector persistence fails. Admins can inspect
the saved chunks in the Document processing tab; maintainers can rebuild
retrieval vectors without rerunning OCR/layout using
`uv run python scripts/retry_document_embeddings.py UPLOAD-<document-id>`.
The script re-applies the configured tokenizer length limit, replaces the
document's retrieval vectors atomically, and only then restores `ready` status.
Migration `20260926213836_processed_document_chunks.sql` enables RLS and denies
direct `anon`/`authenticated` access; the server-side database role owns writes.

## Current boundaries

- Seed parsing: `src/core/document_processing/ingest_documents.py`.
- Upload parsing: `src/core/document_processing/processors/document_processor.py`.
- PDF/OCR/layout: `src/core/document_processing/processors/pdf_processor.py`.
- Table persistence: `src/core/database/structured_store.py`.
- OCR smoke benchmark runner: `scripts/evaluate_ocr.py`; common page list:
  `data/evaluation/ocr_pages.json`; rendered inputs and engine reports live
  under `artifacts/evaluation/` (ignored/local artifacts).
- Human-reviewed OCR pilot: run
  `uv run python scripts/evaluate_ocr.py --dataset data/evaluation/vinamilk_ocr_ground_truth.json --engines tesseract --dpi 180 --output artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract.json`.
  Two manually transcribed real-report crops are scored: a Vietnamese 2024
  financial infographic and an English 2024 sustainability passage. Tesseract
  micro CER/WER were 0.0665/0.2553; the Vietnamese crop was substantially
  harder (CER/WER 0.2637/0.6327) than the English crop (0.0047/0.0543). This is
  a small, born-digital, Tesseract-only pilot; PaddleOCR, EasyOCR and Surya have
  not been compared on these same labels, so it is not a model-selection result.
- Expanded manual-label OCR pilot: run
  `uv run python scripts/evaluate_ocr.py --dataset data/evaluation/vinamilk_ocr_ground_truth_v2.json --engines tesseract --dpi 180 --output artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract-v2.json`.
  This adds a Vietnamese raster-embedded product poster to the two v1 crops.
  Tesseract 5.5.3 scored micro CER/WER 0.1627/0.3815 and macro CER/WER
  0.3124/0.5415. The poster scored 0.6688/0.9375; it is raster-embedded
  artwork, not a physical scan. The report records dataset, source-PDF and
  rendered-image SHA-256, DPI, language and PSM. Three crops and one engine
  remain ineligible for model selection; PaddleOCR, EasyOCR and Surya have no
  comparable scores here.
- Sampled real-document extraction evaluation: run
  `uv run python scripts/evaluate_document_extraction.py --output artifacts/evaluation/vinamilk-document-extraction-scan-table-v9.json`. The latest report is
  `artifacts/evaluation/vinamilk-document-extraction-scan-table-v9.json`; its manually
  transcribed, visually checked fixture is
  `data/evaluation/vinamilk_document_extraction_cases.json`; the current
  report preserves the full-source and selected single-page hashes. Native
  pages are copied without rasterizing, so the evaluator runs in about 20
  seconds on the measured host while exercising the same page parser.
  It compares born-digital PDF parsing, a synthetic raster PDF through the PDF
  parser, and the same rendered page through the actual PNG upload parser. On
  a 2020 financial infographic, all three paths retained both sampled
  revenue/profit anchors exactly (2/2). On a 2024 balance-sheet page, native
  PDF text retained 3/3 exact anchors; PDF-raster OCR retained 0/3 exact, while
  the image-upload OCR path retained 2/3 exact. Both OCR paths reached 3/3
  after normalization (accents, whitespace and numeric grouping punctuation
  ignored while label/value order is preserved). The synthetic raster-PDF path
  now also emits 2/2 structured table regions and matches all 3 table anchors
  after normalization. The image-upload path emits 2/2 regions, matches 2/3
  table anchors after normalization, and retains 3/3 normalized text anchors.
  The evaluator maps image table metadata to page 1 although image chunks lack
  a PDF page number. OCR numeric punctuation and grouping remain error-prone. A
  new borderless-table fallback
  yielded 2/2 expected regions and 3/3 exact structured anchors on the 2024
  balance sheet. It uses PyMuPDF's text grid only when default detection finds
  no tables, groups repeated numeric columns, then restores labels from source
  word coordinates. The runner compares PyMuPDF's default, text/text, text/lines,
  and lines/text table strategies against those same manually labeled fields.
  The initial sweep found that the default missed the regions and raw text/text
  emitted one fragmented 75x15 grid; its settings and results are preserved in
  `artifacts/evaluation/vinamilk-document-extraction-table-strategy-v4.json`.
  Both source documents are born-digital public PDFs; raster copies are not real
  scans. Two pages/five fields remain diagnostic evidence, not representative
  document accuracy.
- PaddleOCR is an optional benchmark extra (`uv sync --extra ocr-paddle`), so
  the standard app environment does not need its large runtime. The runner
  adapts PaddleOCR 2.x/3.x output, accepts `--max-pages` for small smoke runs,
  and limits Paddle CPU threads. A prior optional benchmark environment used
  PaddleOCR 2.10.0 and PaddlePaddle 3.3.1 CPU; neither package is installed in
  the current standard `.venv`. In that prior run, disabling PIR still ended
  in OS kill 137 on one 72-DPI page, so no Paddle quality score is valid. The
  current host has about 3.9 GiB available memory, nearly exhausted swap, and
  no CUDA device; rerun on a higher-memory host or supported GPU.
- The OCR evaluator records each engine's installed package version, model
  initialization duration/error, and CUDA availability in its report. Failed
  model initialization remains an explicit unscored engine and does not produce
  empty-text CER/WER values. On a higher-memory/GPU host, run all proposal
  engines against the same manually reviewed crops with:
  `uv run python scripts/evaluate_ocr.py --dataset data/evaluation/vinamilk_ocr_ground_truth_v2.json --engines paddleocr easyocr surya tesseract --dpi 180 --output artifacts/evaluation/vinamilk-ocr-proposal-comparison.json`.
  Add physical scanned pages and manually labeled table/layout regions before
  using this comparison to select a production OCR engine.
- On the measured host (about 3.6 GiB `MemAvailable`, swap nearly exhausted,
  no CUDA), installing and loading additional OCR engines is not a safe way to
  obtain valid measurements. Run the paired engines on a high-memory/GPU host;
  record versions, model initialization, peak memory, and failures per engine.
- Parser outputs and database status are different evidence; verify both after
  corpus ingestion or upload.
- `tests/test_upload_processing_flow.py` exercises a borderless PDF table, a
  formula-bearing XLSX and a table-bearing PPTX through the upload route and
  checks their structured data reaches the persistence layer. The PDF fixture
  verifies the text-grid fallback; the source-backed v7 report separately
  validates its labels against the Vinamilk statement. Storage and database
  services are mocked; this is the repeatable credential-free regression test.
  A live integration smoke on 2026-09-27 logged in as the configured uploader,
  POSTed a formula-bearing XLSX through `/api/documents/upload`, observed
  `ready` and one indexed chunk, read back its formula metadata and structured
  row from PostgreSQL, and verified the uploaded bytes in private Storage.
  Cleanup removed the uniquely identified document, parser/chunk/table rows
  and object; follow-up queries confirmed both document and Storage object were
  absent. This one-off smoke does not replace CI coverage for upload, Storage,
  retry, RBAC retrieval or other file formats.
- A live retry/RBAC smoke on 2026-09-27 uploaded a newline-terminated TXT while
  injecting an embedding initialization failure. The API returned failure but
  retained one parsed chunk and the original for retry. The actual
  `retry_document_embeddings.py` command rebuilt its vector and restored the
  document to `ready`; the parsed chunk also reached `embedded`. Role-filtered
  BM25 then returned the unique test marker to `finance_analyst` and no result
  to `employee`. This caught two defects: sentence chunking dropped text when a
  file ended in a newline, and the retry repository kept its implicit SELECT
  transaction open so later status writes rolled back on close. Both are fixed
  and covered by regressions. The fixture, parsed/vector/table rows and Storage
  object were removed, and absence was verified. This is one controlled
  integration check, not broad upload-format or load coverage.
- Current upload processing is synchronous. Embedding retry is available for
  saved parsed output, but durable/background jobs, OCR alternatives,
  layout-quality checks, and broad real-file validation remain.

The current Tesseract diagnostic uses ten born-digital report pages and the
native PDF text layer as an unreviewed reference. The 2026-09-26 report is
`artifacts/evaluation/vinamilk-ocr-tesseract-diagnostic-v3.json`: macro page
CER/WER are 0.2281/0.2923; reference-length-weighted CER/WER are
0.1509/0.2140. Visual review corrected the page-language labels for the 2020
and 2021 annual reports: those selected pages are English despite the `VI`
document IDs. The resulting diagnostic aggregates are English micro CER/WER
0.1264/0.1711 (8 pages) and Vietnamese 0.5781/0.7371 (2 pages). The overall
scores did not change; references remain unreviewed, so the dataset marks
`primary_metric_selection_eligible` false. Do not interpret these small,
imbalanced page groups as model-selection evidence. The runner records macro
and micro scores, per-page edit counts, language, and separate language
aggregates.

The separate manually transcribed pilot is defined in
`data/evaluation/vinamilk_ocr_ground_truth.json`; each engine receives the same
PDF-point crop rendered at the configured DPI. Its report records whether each
reference came from manual transcription or the unreviewed PDF text layer so
the two protocols cannot be confused.

PaddleOCR 2.10.0 inference was OS-killed (exit 137) on one 72-DPI page even
after disabling PIR before import; EasyOCR was killed during model loading.
Surya has not been run. This does not satisfy the proposal's three-model
comparison or scanned-document evaluation. See
`technical/agents-and-evaluation.md` for current limits.

See [chunking](chunking.md) for per-path size settings and [proposal coverage](../README.md)
for remaining extraction requirements.
