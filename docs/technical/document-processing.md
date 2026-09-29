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

- `processors/document_processor.py` is the upload dispatcher. It selects a
  format processor and attaches common source metadata; it does not parse file
  contents or persist results.
- `processors/office_processor.py` parses DOCX/PPTX/XLSX Open XML and enforces
  archive expansion limits. These formats share ZIP/XML handling, so one module
  owns their common boundary.
- `processors/text_processor.py` decodes UTF-8 TXT/Markdown and provides the
  shared chunking implementation.
- `processors/image_processor.py` handles standalone-image OCR, OCR-derived
  tables, and optional vision captions.
- `processors/pdf_processor.py` orchestrates native text extraction, OCR,
  chunking and optional image captions. Its focused helpers are
  `processors/pdf_layout_processor.py` for Paddle layout analysis and
  `processors/pdf_table_extractor.py` for native/OCR table reconstruction.
  Compatibility methods remain on `PDFProcessor` for existing callers.
- `ingest_documents.py` adapts seed PDFs and HTML into token-bounded chunks.
  Seed PDFs reuse `PDFProcessor`; public HTML uses the local HTML text
  extractor.
- Upload orchestration in `app/main.py` stores originals, calls the dispatcher,
  persists parsed chunks/tables before tokenization and embedding, then writes
  vectors and metric candidates. For fiscal-year PDFs, it additionally ranks
  finance pages from statement terms, KPI labels, parser tables, and summary
  page signals, then requests candidate JSON from the LLM only for those pages
  (at most 10). Validation requires page-verbatim evidence, the metric label
  and value in the quote, a reported unit on the page, and the year on that
  page. Parser fallback candidates are generated only from these shortlisted
  pages, prioritizing structured rows and KPI cards; narrative numeric guesses
  are limited to summary pages. Unit hints come from table headers/page spans
  and remain suggestions. Values stay unverified until an admin checks source,
  fiscal year, and unit.
  During candidate merging, LLM output replaces only the parser candidate with
  the same document, metric, year, and page; parser candidates for other
  metrics remain visible for review.
  Candidates record extraction method, model, prompt version, and page
  selection evidence; all stay pending until admin verification. The admin
  processing tab exposes saved parser output and metadata through a paginated,
  manifest-company-scoped endpoint. Review links open an uploaded original
  through an admin-only application route that checks the ready document and
  company before downloading bytes from private Storage; the browser never gets
  the Storage secret or a public URL. Financial candidate and verified-KPI
  links to PDFs open at their cited page; links to non-PDF sources remain
  unchanged.

The batch runner supports `--page-selection-only` for zero-cost selection
inspection, `--llm --dry-run` to inspect model extraction without persistence,
and `--llm --save-candidates` for review-only candidate persistence. Selected
page diagnostics and current evaluation limits are documented in the
[project progress](../README.md#financial-dashboard-extraction-progress).

The proposed next dashboard iteration is recorded after OCR acceptance work in
the [project progress note](../README.md#next-dashboard-iteration-after-ocr-acceptance-work).
It retains the current candidate/review table and treats page-count savings as
an experiment: evaluate statement-page recall and field/value/unit correctness
before changing the shortlist or claiming request-cost reduction.

Only these active paths are retained. The unused alternative Excel/image
processors and a second PDF-to-Markdown converter were removed so they cannot
be mistaken for supported production routes.

## Supported formats and extraction

`DocumentProcessor.SUPPORTED` currently lists PDF, DOCX, PPTX, XLSX, TXT, MD,
PNG, JPEG, and TIFF. DOCX/PPTX/XLSX are parsed from Open XML using the Python
standard library. Legacy binary XLS is not supported. The seed-corpus command
currently handles PDF and HTML; the Vinamilk reports are PDFs.
Standalone image uploads can also create a separate, model-generated caption
chunk. Set `DOCUMENT_VISION_CAPTIONS=true` to enable this path; it sends the
image to Groq's vision endpoint using `GROQ_VISION_MODEL` (default
`qwen/qwen3.8-27b`). This is disabled by default. Caption chunks preserve the
model ID and generated-content provenance. If the provider is unavailable or
rejects the image, the parser keeps the OCR result and logs only the error type.
The model accepts visual input through Groq's documented [vision API](https://console.groq.com/docs/vision).
Caption text is labeled as unverified in retrieval context, and the KPI candidate
extractor excludes model-generated chunks as source evidence. PDFs use the same
opt-in setting to caption up to three prominent embedded raster figures per
document; each caption keeps its source page and PDF-point bounding box. PPTX
figures and vector-only PDF charts are not covered. Caption quality has not been
manually evaluated. Treat captions as retrieval hints, not verified evidence.
DOCX chunks inherit the most recent Word `Heading 1`–`Heading 9` paragraph as
`section_title`; PPTX chunks use the slide title placeholder; XLSX chunks use
the worksheet name. Native PDF headings use short, visually prominent lines;
OCR text conservatively adds explicitly numbered Chapter, Article and
subsection headings. Unnumbered OCR-only headings can still be missed.
Documents/pages without a recognized heading keep `section_title` null.
DOCX body tables are processed in document order: row values become retrieval
text with their column labels, while the same rows remain in structured table
storage for admin inspection. This preserves row/column relationships in RAG
context instead of embedding each table-cell paragraph as an unlabeled chunk.
DOCX Office Math runs (`m:oMath`) are now included alongside paragraph text;
the chunk metadata marks `contains_formula` and stores the extracted math text.
This preserves the source's textual math tokens for retrieval, but does not
reconstruct two-dimensional notation, recognize formulas in figures/scanned
pages, or evaluate an equation.
The parser change alone does not update existing rows. For a seed PDF,
`uv run python scripts/backfill_section_titles.py --ids <DOCUMENT_ID>` creates
a dry-run report. Add `--apply` only after checking that stored chunk count,
indices, and every content string match the parser; it then updates only
`metadata.section_title` and writes a backup. If chunks do not match exactly,
the tool skips the document and re-ingestion is required.

Office ZIP packages are checked before XML parsing: at most 10,000 entries,
100 MiB per member, 200 MiB expanded total, and a 200:1 member compression
ratio. Invalid Office ZIP/XML packages and these resource-limit violations
return a client error on upload rather than being reported as database outages.

PPTX parsing extracts slide text and slide tables into the common structured
table shape, with the slide number retained as page/table metadata. XLSX parsing
preserves explicit cell formulas, formula type/range attributes, and cached
values in the corresponding table metadata. Formula expressions are also
included in retrievable sheet text; cached values remain structured row values
because the parser does not recalculate workbooks. Workbook parsing does not
recognize mathematical notation embedded in PDF/images or establish formula
calculation correctness. DOCX Office Math coverage is limited to extracting its
XML text runs; it is not full formula recognition. PDF formula recognition is available
only through the optional PaddleOCR PP-StructureV3 path. Set
`DOCUMENT_PADDLE_FORMULA_RECOGNITION=true` to enable it; this also enables
`DOCUMENT_PADDLE_LAYOUT` implicitly and downloads/loads Paddle's formula model.
Recognized formula blocks are stored in the ordinary retrieval chunks with
their page, rendered-page bounding box, `element_type=layout_type=formula`,
`contains_formula=true`, and `formula_representation=latex`. The integration is
covered by an adapter mock only; real PDF formula accuracy, OCR/layout
interaction and resource usage have not been measured. Keep it disabled unless
formula-bearing PDFs need processing. See PaddleOCR's [formula recognition
pipeline](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/formula_recognition.html)
and [PP-StructureV3 configuration](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PP-StructureV3.en.md).

PDF handling uses PyMuPDF text and table extraction. Selective Tesseract OCR
uses `vie+eng` with PSM 11 for reading sparse text: OCR runs below 50
native-text characters, or below 500 when raster images cover at least 25% of
the page. Mixed-page OCR is appended to native text. Direct image uploads use
the same text mode and record the extraction method. If OCR finds at least
three numeric rows, a separate TSV pass supplies word boxes to reconstruct
borderless table rows by repeated left or right numeric column alignment. The
scanner filters infrequent numeric alignments and account/note columns that
do not have a clear per-column label/value gap. It uses local label evidence so
parallel financial tables stay separate; OCR'd four-digit years and eight-digit dates can supply
period column names and are omitted from table body rows. General page text
renders at 108 DPI; likely numeric-table pages receive a second 180 DPI render
for table-word recognition. This extra render is gated on repeated numeric
rows and configurable with `ocr_table_render_scale`; ordinary pages keep the
existing render cost. This remains a heuristic, not general table-structure
recognition.
PDF upload path uses PSM 3 for its table-word pass; direct image uploads use
PSM 6, selected from the paired financial-page evaluation below. The text OCR
mode remains independent of this table setting. The separate six-region,
108-DPI v6 sweep found PSM 3 vs 11 micro-CER
0.226172 vs 0.107952 and micro-WER 0.400850 vs 0.293201; PSM 3 retained more
table cell text (27/48 vs 21/48), supporting it for PDF word-box extraction.
The pilot is small and mixes scans, artwork and a born-digital table; it is not
a universal optimal setting. Reproduce via `scripts/evaluate_ocr.py` with
`--tesseract-psm 3` or `11`; see the [PSM 3 baseline](../../artifacts/evaluation/vinamilk-tesseract-psm3-v6-108dpi.json), [PSM 6 comparison](../../artifacts/evaluation/vinamilk-tesseract-psm6-v6-108dpi.json), and [PSM 11 result](../../artifacts/evaluation/vinamilk-tesseract-psm11-v6-108dpi.json).
OCR-derived structured tables carry their Tesseract engine, language, table
PSM and render scale in the persisted `metadata.ocr` object so the review UI
and later audits can identify the extraction configuration.

The v8 end-to-end replay of the upload `DocumentProcessor` on 11 labeled
regions scored micro-CER/WER 0.055009/0.175768 at 108 DPI with local Tesseract
5.5.3. This is a parser-path diagnostic, not a comparison with the Kaggle
engines (which used 180 DPI and different package/runtime environments). It
exposed a 2024 born-digital balance-sheet page where text OCR had CER/WER
0.188875/0.364583 and no table, despite selectable source text. Native
PyMuPDF text-table detection reconstructs its 16 rows and both date columns;
the parser now tries that detector when the standard table and aligned-text
checks find nothing, even if OCR did not run. A real source-crop regression
checks the audited `Tổng tài sản` values for 2024 and 2023. The 2020 product
poster remains difficult at CER/WER 0.662500/0.906250 on this fixture; it is
complex artwork and does not justify changing global OCR defaults. Reproduce
the parser replay with `uv run python scripts/evaluate_scan_document_processing.py
--dataset data/evaluation/vinamilk_ocr_ground_truth_v8.json --output
artifacts/evaluation/vinamilk-upload-processor-v8-20260929.json`.

The five-year financial extraction evaluator now also runs the same
rule-based KPI candidate extractor on both synthetic raster paths (PDF upload
and direct image upload), not only on the born-digital source. Against the 11
reviewed fields, the source-text path found 11/11; Tesseract found 3/11 on the
raster-PDF path and 2/11 on the image path, with no incorrect matched
candidates in this small set. These are synthetic scans rendered from
born-digital reports, not true scanned originals. The result shows that good
native-text extraction and a detected OCR table do not establish that KPI
evidence reaches the admin review queue. Keep OCR-derived metrics pending and
require source verification; do not treat the score as financial accuracy.
Reproduce with
`uv run python scripts/evaluate_document_extraction.py --compact --output
artifacts/evaluation/vinamilk-document-extraction-ocr-to-kpi-20260929.json`.

An optional one-request LLM mode exercises the same PDF-upload shortlist and
verbatim-evidence validator without persisting candidates. On the reviewed
2023 income-statement page, Tesseract OCR selected the page; the configured
`openai/gpt-oss-20b` returned four metrics, two passed page-quote validation,
and one matched a labeled target (profit after tax; 1/2 field recall). Revenue
was not recovered because its OCR label was corrupted. This confirms the
review gate rejects unsupported suggestions, but does not close OCR accuracy
or model-quality evaluation. Reproduce with
`uv run python scripts/evaluate_document_extraction.py --compact --case-id
ar2023-consolidated-income-p115 --llm --output
artifacts/evaluation/vinamilk-document-extraction-ocr-to-kpi-llm-20260929.json`;
the command reads `GROQ_API_KEY` from the environment or local `.env` and makes
one LLM request for the selected case.

The no-write LLM path was exercised on the original scanned PDF page from the
separate third-party 2011 financial-statement packet. A prior run returned four
suggestions; strict validation accepted two, including the reviewed FY2011
profit-after-tax value with its `VNĐ` unit. Revenue remained unmatched. A
follow-up run after adding OCR-only near-match validation hit the provider rate
limit before returning candidates, so the updated behavior is currently covered
by deterministic tests rather than a fresh live-provider result. Label recovery
requires an exact page quote, exact value and unit evidence, and the requested
fiscal year; it is enabled only for OCR pages and records the near-match in
selection evidence. Candidates remain `needs_review`; the admin review panel
shows an OCR-label warning and asks reviewers to verify the printed label, value,
and year in the source. The source page's OCR table contains the reviewed
revenue amount, but its Vietnamese label has
recognition errors. This is one source page, not representative OCR/model
evidence. The latest [run artifact](../../artifacts/evaluation/vinamilk-ocr-2011-real-scan-kpi-llm-20260929.json)
records the provider error and must not be interpreted as a successful rerun.
During the earlier trace, a handoff defect was also fixed: accepted LLM units
were validated but omitted from the pending candidate before database save. The
unit now travels through that handoff; extractor and upload boundary tests
assert it. No database write was made. Reproduce against the original source scan with
`uv run python scripts/evaluate_document_extraction.py --cases
data/evaluation/vinamilk_2011_real_scan_kpi_cases.json --case-id
real-scan-2011-income-statement-vi --compact --llm --output
artifacts/evaluation/vinamilk-ocr-2011-real-scan-kpi-llm-20260929.json`.

The actual PDF upload parser was also measured on the manually labeled
Vietnamese product poster. At its nominal 108 DPI, PSM 11 scored CER/WER
0.543750/0.843750, compared with 0.650000/0.906250 for PSM 3 and
0.675000/0.937500 for PSM 6. PSM 11 is the best of these tested settings, but
the absolute error remains high for complex artwork. These are single-region
results, not a Vietnamese scan benchmark. The PSM runs share the same
deterministic cropped-PDF SHA-256 (`74b3b66d250bbfa60c44d8934e120e8d2f4a10457a376622b1e860362c960ffd`). Reproduce with
`scripts/evaluate_scan_document_processing.py --dataset data/evaluation/vinamilk_ocr_ground_truth_v6.json --case-id annual-2020-product-poster-vi --tesseract-psm 11`; the [PSM 11](../../artifacts/evaluation/vinamilk-upload-ocr-vietnamese-poster-psm11-v6-20260928.json), [PSM 3](../../artifacts/evaluation/vinamilk-upload-ocr-vietnamese-poster-psm3-v6-20260928.json), and [PSM 6](../../artifacts/evaluation/vinamilk-upload-ocr-vietnamese-poster-psm6-v6-20260928.json) artifacts preserve upload-path outputs and input hashes.
Raising the actual parser render scale from 1.5 (108 DPI) to 2.5 (180 DPI)
made this same poster worse: PSM 11 CER/WER rose to 0.631250/1.218750 and
latency to 1.721 seconds, so the default remains 1.5. Set the
`DocumentProcessor` config key `ocr_render_scale` to change the scale; it is
recorded per evaluation. See the
[180-DPI run](../../artifacts/evaluation/vinamilk-upload-ocr-vietnamese-poster-psm11-180dpi-v6-20260928.json).
A generated TIFF smoke verified both OCR and transactional
readback through `extracted_tables`; this validates the path, not image/table
accuracy on representative source documents. The optional Paddle path enables
PP-Structure chart recognition and retains textual chart/figure blocks as
retrieval chunks with layout labels and page coordinates. Paddle labels such as
`figure_caption` and `table_caption` are also retained. Production seed/upload
configuration disables this path, and chart recognition has only adapter-mock
coverage; real-chart quality, PPTX figure captions, image interpretation
and diagram understanding remain unverified. Standalone image uploads have an
independent, opt-in Groq vision caption path; no caption-quality review has been
completed.

Tables are stored separately in `extracted_tables` and `extracted_records`.
They are raw parser results, not validated financial facts. Dashboard KPIs come
from admin-verified `extracted_financial_metrics` only.

Parsed upload chunks are stored in `processed_document_chunks` with extraction
metadata and an embedding-stage status. This preserves OCR/layout output if
tokenizer/model initialization or vector persistence fails. Admins can inspect
saved chunks and paginated extracted table rows in the Document processing tab;
the table API applies active-company scope and bounded page sizes. Maintainers can rebuild
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
  `data/evaluation/ocr_pages.json`; rendered inputs and run reports live under
  `artifacts/evaluation/`; selected hash-verified comparison artifacts are tracked.
- Human-reviewed OCR pilot: run
  `uv run python scripts/evaluate_ocr.py --dataset data/evaluation/vinamilk_ocr_ground_truth.json --engines tesseract --dpi 180 --output artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract.json`.
  Two manually transcribed real-report crops are scored: a Vietnamese 2024
  financial infographic and an English 2024 sustainability passage. Tesseract
  micro CER/WER were 0.0665/0.2553; the Vietnamese crop was substantially
  harder (CER/WER 0.2637/0.6327) than the English crop (0.0047/0.0543). This is
  a small, born-digital, Tesseract-only v1 baseline; the paired v2 comparison
  across four engines is recorded below and is still not a model-selection result.
- Expanded manual-label OCR pilot: run
  `uv run python scripts/evaluate_ocr.py --dataset data/evaluation/vinamilk_ocr_ground_truth_v2.json --engines tesseract --dpi 180 --output artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract-v2.json`.
  This adds a Vietnamese raster-embedded product poster to the two v1 crops.
  Tesseract 5.5.3 scored micro CER/WER 0.1627/0.3815 and macro CER/WER
  0.3124/0.5415. The poster scored 0.6688/0.9375; it is raster-embedded
  artwork, not a physical scan. The report records dataset, source-PDF and
  rendered-image SHA-256, DPI, language and PSM. This three-crop set remains
  ineligible for model selection. The three proposal engines and Tesseract
  were subsequently evaluated on the identical crop/PDF hashes at 180 DPI.
  EasyOCR 1.7.2 (T4 GPU) scored micro CER/WER 0.078842/0.283237 and 1.195 s
  mean inference/crop; PaddleOCR 3.7.0 (CPU on a T4-assigned runtime) scored
  0.079840/0.300578 and 18.587 s/crop; Surya 0.17.1 (T4 GPU) scored
  0.083832/0.156069 and 5.845 s/crop; Tesseract 5.5.3 (local CPU) scored
  0.163673/0.381503 and 0.855 s/crop. Initialization was 12.111 s for
  EasyOCR, 57.036 s for PaddleOCR, and 61.3 s for Surya. EasyOCR has the lowest
  micro-CER while Surya has the lowest micro-WER; three selected crops do not
  justify selecting a production engine. All reports share dataset SHA-256
  `3a7c747104689ceea630d41891e11cd2ba5ebf34e96688b6fcfe86d0a8f83846`.
  See the linked raw [EasyOCR](../../artifacts/evaluation/ocr-kaggle-easy/vinamilk-ocr-easyocr.json),
  [PaddleOCR](../../artifacts/evaluation/ocr-kaggle-paddle/vinamilk-ocr-paddleocr.json),
  [Surya](../../artifacts/evaluation/ocr-kaggle-surya/vinamilk-ocr-surya.json)
  and [Tesseract](../../artifacts/evaluation/ocr-tesseract-v2-current-labels.json)
  reports. A hash-checking comparator verifies the dataset, PDF/page and
  rendered-image hashes before pairing them; its result is
  `artifacts/evaluation/vinamilk-ocr-three-engine-v2-comparison.json`. Rebuild
  it with `uv run python scripts/compare_ocr_reports.py <report> <report> ...
  --output <comparison.json>`. These are text-transcription scores only, not
  table/layout accuracy.
- **Historical OCR v3-v5 results (superseded for scan accuracy):** the v3/v4
  manual labels added two image-only scan regions from official 2026
  governance PDFs; PyMuPDF confirms both source pages have no text layer and
  contain scanned page images. On the Charter introduction (71 words),
  Tesseract 5.5.3 at 180 DPI scored CER 0.037528/WER 0.084507 (~1.06 s).
  On the governance table-of-contents crop (270 words; dotted leaders and page
  numbers), it scored CER 0.654140/WER 0.300000 (~4.11 s). The sharp difference
  illustrates the layout difficulty. Dataset v4 is
  `data/evaluation/vinamilk_ocr_ground_truth_v4.json`; its result is
  `artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract-v4.json`.
  Dataset v3 preserves the earlier single-scan baseline. EasyOCR 1.7.2 now has
  hash-verified scores on all five v4 regions, including both scans; paired
  v4 comparison is in `vinamilk-ocr-governance-scans-v4-comparison.json`.
  PaddleOCR 3.7.0 has now completed on those exact v4 hashes. It scored
  micro-CER/WER 0.078017/0.173152 at 2.818 pages/minute, 37.852 s model
  initialization and 3,937.254 MiB process peak RSS. The Kaggle T4 runtime had
  CUDA, but this run used Paddle's CPU wheel/device; do not compare throughput
  directly with EasyOCR's T4 run. Hash-paired EasyOCR/PaddleOCR/Tesseract scores
  are in [the v4 comparison](../../artifacts/evaluation/vinamilk-ocr-paddle-easy-tesseract-v4-comparison.json).
  These v3-v5 scan scores and any all-page aggregates containing those scans
  are superseded by v6 below; the unchanged v5 balance-sheet table diagnostics
  remain historical table-only results. The earlier note that Surya v4 was
  queued is stale: v6 four-engine reports are complete. **Dataset correction
  (v6, 2026-09-28):** visual review found that the two
  governance scan crops in v3–v5 cut off printed text while their references
  retained complete lines. Therefore all v3–v5 scan-page CER/WER and any
  all-page aggregate containing those scans are historical and must not be
  compared or cited as valid paired text-accuracy results. The financial-table
  crop did not change, so its table-only cell-presence and exact-row diagnostics
  remain valid. V6 widens both scan crops and pins dataset/PDF hashes in rendered
  filenames. The corrected local Tesseract baseline is Charter CER/WER
  0.008830/0.042254 and governance-TOC 0.642038/0.322222; corrected paired
  All four v6 engines now have hash-matched reports on the same six pages.
  Tesseract/EasyOCR/Surya/PaddleOCR micro-CER is 0.325961/0.176672/0.071090/
  0.088994 and micro-WER is 0.259207/0.361190/0.143059/0.209632. On the one
  unchanged financial table, cell-text presence is 40/48, 47/48, 47/48 and
  32/48; exact contiguous row recall is 8/16, 2/16, 14/16 and 0/16. Surya
  has the lowest character/word error in this run, but CPU inference averaged
  119.647 s/page and peaked at 5,995.988 MiB RSS. EasyOCR averaged 15.606
  s/page (3,129.754 MiB), PaddleOCR 31.952 s/page (3,504.520 MiB), and local
  Tesseract 1.183 s/page (562.336 MiB). EasyOCR, Surya and PaddleOCR used
  Kaggle CPU; Tesseract used local CPU. Quality metrics are paired to the same
  images and references, but runtime/memory comparisons are not controlled
  across hosts. Do not select a production engine from these six pages. Raw
  reports: [Tesseract v6](../../artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract-v6.json),
  [EasyOCR v6 CPU](../../artifacts/evaluation/ocr-kaggle-easy/vinamilk-ocr-easyocr-v6-cpu.json),
  [Surya v6 CPU](../../artifacts/evaluation/ocr-kaggle-surya/vinamilk-ocr-surya-v6-cpu.json),
  [PaddleOCR v6 CPU](../../artifacts/evaluation/ocr-kaggle-paddle/vinamilk-ocr-paddleocr-v6-cpu.json).
  Reproducible hash-checked comparison: [four-engine v6](../../artifacts/evaluation/vinamilk-ocr-four-engine-v6-cpu-comparison.json).
  Recompute it with the matching v6 baseline; the older
  `ocr-tesseract-v2-current-labels.json` has a different dataset hash:

  ```bash
  uv run python scripts/compare_ocr_reports.py \
    artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract-v6.json \
    artifacts/evaluation/ocr-kaggle-easy/vinamilk-ocr-easyocr-v6-cpu.json \
    artifacts/evaluation/ocr-kaggle-surya/vinamilk-ocr-surya-v6-cpu.json \
    artifacts/evaluation/ocr-kaggle-paddle/vinamilk-ocr-paddleocr-v6-cpu.json \
    --dataset data/evaluation/vinamilk_ocr_ground_truth_v6.json \
    --output /tmp/vinamilk-ocr-four-engine-v6-cpu-comparison.json
  ```
  **Expanded cross-engine run (v7):** five settings now share the same ten
  reviewed regions, 180-DPI renders and dataset/PDF/image hashes. Six regions
  are physical scans with English references; v7 added four of these regions.
  The Vietnamese financial table is born-digital and its cell strings were
  reviewed.
  Tesseract PSM 3/11, EasyOCR 1.7.2, PaddleOCR 3.7.0 and Surya 0.17.1 score
  micro-CER 0.272556/0.127318/0.110025/0.043609/0.043233 and micro-WER
  0.263561/0.197497/0.248261/0.108484/0.090403. Surya on a Tesla T4 has the
  lowest text error, 14/16 exact table rows and 47/48 present cell strings.
  Paddle ran on CPU (2.229 pages/minute), so its throughput is not comparable
  with the EasyOCR/Surya GPU runs. Tesseract is also CPU-only. This is a
  ten-region diagnostic, not model selection: six regions are English physical
  scans, the only labeled financial table is born-digital, and Vietnamese
  physical scans/cell-coordinate labels remain absent. See the [five-setting report](../../artifacts/evaluation/vinamilk-ocr-v7-five-configuration-comparison-20260928.json),
  raw [EasyOCR](../../artifacts/evaluation/vinamilk-ocr-v7/easyocr.json),
  [PaddleOCR](../../artifacts/evaluation/vinamilk-ocr-v7/paddleocr.json),
  [Surya](../../artifacts/evaluation/vinamilk-ocr-v7/surya.json), the
  Tesseract [PSM 3](../../artifacts/evaluation/vinamilk-ocr-tesseract-scan-expansion-v7-180dpi-psm3-20260928.json)/[PSM 11](../../artifacts/evaluation/vinamilk-ocr-tesseract-scan-expansion-v7-180dpi-20260928.json)
  reports, and the [reviewed references](../../data/evaluation/vinamilk_ocr_ground_truth_v7.json).
  Tesseract reports in the `vinamilk-ocr-v7/` folder are copies with distinct
  `tesseract_psm3`/`tesseract_psm11` keys so the general comparator can accept
  both configurations in one paired run.
  Recompute the paired result with the same reports:

  ```bash
  uv run python scripts/compare_ocr_reports.py \
    artifacts/evaluation/vinamilk-ocr-v7/tesseract-psm3.json \
    artifacts/evaluation/vinamilk-ocr-v7/tesseract-psm11.json \
    artifacts/evaluation/vinamilk-ocr-v7/easyocr.json \
    artifacts/evaluation/vinamilk-ocr-v7/paddleocr.json \
    artifacts/evaluation/vinamilk-ocr-v7/surya.json \
    --dataset data/evaluation/vinamilk_ocr_ground_truth_v7.json \
    --output /tmp/vinamilk-ocr-v7-five-configuration-comparison.json
  ```
  The comparison artifact labels the Tesseract settings separately as PSM 3
  and PSM 11 while preserving their source reports' hashes.
  A source audit on 2026-09-28 found no physically scanned Vietnamese page in
  the current corpus: low-text pages 22–24 of the 2020 report and page 28 of
  the 2021 report are promotional artwork when visually inspected. The
  physically scanned Vinamilk Charter and Governance Rules pages in v6 are
  English. Vinamilk's [official annual-report archive](https://www.vinamilk.com.vn/investor/reports/annual)
  currently serves the Vietnamese [2011 annual report PDF](https://d8um25gjecm9v.cloudfront.net/cms/1398182145_88985e5feb5620a4ffe6eb89a4752696210bb183d1784ef5ee438a8acc14deb4_1891381fb3.pdf).
  Its 2011 financial statements are born-digital, so they do not fill the
  physical-scan gap. A separate signed Vietnamese 2011 statement packet was
  found in a third-party preview. Three financial-statement pages were visually
  reviewed; the income-statement figures match the official report. The packet
  remains separate from v7 because it is third-party-hosted and represents one
  source. It cannot represent broad Vietnamese scan quality or close the
  cell-coordinate gap.

  **Latest cross-engine run (v8):** the v7 regions plus one full-page scan from
  Vinamilk's official 2026 Internal Corporate Governance Regulations were run
  at 180 DPI through Tesseract 4.1.1 PSM 3, PaddleOCR 3.7.0, EasyOCR 1.7.2 and
  Surya 0.17.1. All four have 11 valid regions with exact-matched source/render
  hashes. Micro-CER is 0.217257/0.034654/0.089266/0.034654 and micro-WER is
  0.230375/0.089875/0.211035/0.075085. Paddle and Surya tie on CER; Surya has
  the lowest WER. On the single financial table, exact row counts are 15/16,
  0/16, 2/16 and 14/16, and cell-string presence is 47/48, 32/48, 47/48 and
  47/48. Paddle ran on CPU; EasyOCR and Surya on a Tesla T4; timing and memory
  are not controlled. This is an English-heavy diagnostic, not model-selection
  evidence. The original engine runs used label SHA-256
  `824c2a06fd6a4a170b0b2387182d346fe153863c56f1dd1dc304f93124b15bb0`; the
  final labels add page source/render hashes and correct the source-PDF count,
  so cached predictions were rescored against the final label SHA-256
  `6c2be146e88b54a3c8f674157d6d86b01d57f6be0b91da0b2f190d164337ffd2` after
  verifying those page hashes. Rebuilding the comparison from all four checked-in
  raw reports reproduces the paired page hashes and every aggregate exactly:

  ```bash
  uv run python scripts/compare_ocr_reports.py \
    --dataset data/evaluation/vinamilk_ocr_ground_truth_v8.json \
    --rescore-references \
    artifacts/evaluation/ocr-kaggle-v8/tesseract.json \
    artifacts/evaluation/ocr-kaggle-v8/paddleocr.json \
    artifacts/evaluation/ocr-kaggle-v8/easyocr.json \
    artifacts/evaluation/ocr-kaggle-v8/surya.json \
    --output /tmp/vinamilk-ocr-v8-reproduction.json
  ```

  The [v8 labels](../../data/evaluation/vinamilk_ocr_ground_truth_v8.json),
  [paired comparison](../../artifacts/evaluation/vinamilk-ocr-v8-four-engine-comparison-20260929.json),
  and [raw reports](../../artifacts/evaluation/ocr-kaggle-v8/) preserve both
  hashes and run provenance.

  **Cross-layout v9 rescore:** the v8 labels are paired with all three pages
  from the separate 2011 Vietnamese financial-scan diagnostic, giving 14
  regions across six PDFs. The v2 and v8 raw reports use identical engine
  versions, settings, runtime devices and 180-DPI rendering; every page's PDF
  and image hashes were checked before pooling. No OCR model was rerun. Across
  the combined references, Tesseract/PaddleOCR/EasyOCR/Surya micro-CER is
  0.361902/0.073542/0.198714/0.074786 and micro-WER is
  0.491573/0.181882/0.337079/0.116222. On 33 labeled financial rows, exact
  contiguous row recall is 15/33, 0/33, 11/33 and 16/33; cell-string presence
  is 97/99, 66/99, 97/99 and 98/99. The row score does not measure spatial
  reconstruction. The per-language split is:

  | Language | Pages | Tesseract CER/WER | PaddleOCR CER/WER | EasyOCR CER/WER | Surya CER/WER |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | English | 8 | 0.221998/0.226936 | 0.019134/0.030976 | 0.050017/0.141414 | 0.021819/0.058586 |
  | Vietnamese | 6 | 0.587959/0.779897 | 0.161454/0.346295 | 0.438980/0.550257 | 0.160369/0.179017 |

  The Vietnamese slice is still only six pages from three sources, with two
  text-layer-assisted references; it is diagnostic, not representative or
  model-selection evidence. Cell-string recall remains text-presence only.
  The [v9 labels](../../data/evaluation/vinamilk_ocr_ground_truth_v9.json),
  [merged engine reports](../../artifacts/evaluation/ocr-kaggle-v9/), and
  [four-engine comparison](../../artifacts/evaluation/vinamilk-ocr-v9-four-engine-comparison-20260929.json)
  record source reports and hashes. Rebuild the merged reports, then rescore:

  ```bash
  uv run python scripts/merge_ocr_reports.py \
    --dataset data/evaluation/vinamilk_ocr_ground_truth_v9.json \
    --output-dir /tmp/ocr-kaggle-v9 \
    artifacts/evaluation/ocr-kaggle-v8/tesseract.json \
    artifacts/evaluation/ocr-kaggle-v2/tesseract-psm3.json \
    artifacts/evaluation/ocr-kaggle-v8/paddleocr.json \
    artifacts/evaluation/ocr-kaggle-v2/paddleocr.json \
    artifacts/evaluation/ocr-kaggle-v8/easyocr.json \
    artifacts/evaluation/ocr-kaggle-v2/easyocr.json \
    artifacts/evaluation/ocr-kaggle-v8/surya.json \
    artifacts/evaluation/ocr-kaggle-v2/surya.json
  uv run python scripts/compare_ocr_reports.py \
    --dataset data/evaluation/vinamilk_ocr_ground_truth_v9.json \
    --rescore-references \
    /tmp/ocr-kaggle-v9/tesseract_psm3.json \
    /tmp/ocr-kaggle-v9/paddleocr.json \
    /tmp/ocr-kaggle-v9/easyocr.json \
    /tmp/ocr-kaggle-v9/surya.json \
    --output /tmp/vinamilk-ocr-v9-four-engine-comparison.json
  ```

  **Paired CPU v9 rerun:** four private Kaggle kernels reran Tesseract 4.1.1,
  PaddleOCR 3.7.0, EasyOCR 1.7.2 and Surya 0.17.1 on the same 14 regions,
  using 180-DPI renders, the v9 dataset SHA, and GPU-disabled CPU kernels.
  All four reports contain 14/14 pages with zero errors and identical
  source/render hashes. Tesseract/Paddle/Easy/Surya micro-CER is
  0.361902/0.073542/0.198645/0.074924; micro-WER is
  0.491573/0.181882/0.337430/0.116573. Exact table-row matches are
  15/33/10/16; text-presence cell matches are 97/99, 66/99, 96/99 and 98/99.
  Paddle has the lowest CER, while Surya has the lowest WER and highest row
  recall. In Vietnamese, Paddle/Surya CER is 0.161454/0.160730 and WER is
  0.346295/0.179751. The Kaggle CPU runtime reports four logical CPUs but does
  not expose the CPU model; throughput (2.468/47.641/20.155/106.282 s/page)
  and process peak RSS (342/4,106/4,033/6,306 MiB) are therefore descriptive,
  not a hardware-controlled ranking. The samples and mixed manual/text-layer
  references remain too small for selecting an OCR engine, and the row/cell
  scores do not test spatial reconstruction. Reproduce from
  [`kaggle_ocr_v9_cpu_paired.ipynb`](../../notebooks/kaggle_ocr_v9_cpu_paired.ipynb)
  attached to the private Kaggle dataset
  [`vinamilk-ocr-v9-benchmark-assets`](https://www.kaggle.com/datasets/ltrngnhn/vinamilk-ocr-v9-benchmark-assets);
  the per-engine kernels are [Tesseract](https://www.kaggle.com/code/ltrngnhn/vinamilk-ocr-v9-cpu-tesseract),
  [PaddleOCR](https://www.kaggle.com/code/ltrngnhn/vinamilk-ocr-v9-cpu-paddleocr),
  [EasyOCR](https://www.kaggle.com/code/ltrngnhn/vinamilk-ocr-v9-cpu-easyocr) and
  [Surya](https://www.kaggle.com/code/ltrngnhn/vinamilk-ocr-v9-cpu-surya). The
  [paired comparison](../../artifacts/evaluation/vinamilk-ocr-v9-cpu-four-engine-comparison-20260929.json)
  and [raw reports](../../artifacts/evaluation/ocr-kaggle-v9-cpu/) preserve
  scores, run versions and per-page hashes.

  **Supplemental Vietnamese scan diagnostic (v1; separate from v7):** one signed
  2011 consolidated income-statement page from the third-party preview was
  transcribed and visually checked; its financial values were cross-checked
  against Vinamilk's official annual report. The scan PDF is pinned by SHA-256
  in the [diagnostic labels](../../data/evaluation/vinamilk_ocr_ground_truth_2011_scan_diagnostic.json);
  the package builder downloads a missing copy only after HTTPS, PDF-magic and
  checksum checks. At 180 DPI, Tesseract PSM 3/6/11, EasyOCR 1.7.2, PaddleOCR
  3.7.0 and Surya 0.17.1 scored micro-CER 0.858586/0.359751/0.369852/
  0.468531/0.373737/0.316239 and micro-WER 1.055016/0.462783/0.482201/
  0.533981/0.592233/0.349515. Strict row recall was 0/7, 3/7, 2/7, 6/7,
  0/7 and 2/7; cell-text presence was 18/21, 17/21, 17/21, 20/21, 14/21
  and 21/21. EasyOCR and Surya ran on Tesla T4; PaddleOCR and Tesseract ran
  on CPU, so runtime/resource figures are not comparable. This single
  third-party-hosted page is diagnostic only: do not pool it into v7 or use it
  for model selection. Cell-text presence and linearized row recall do not
  evaluate cell coordinates or table structure. See the [paired report](../../artifacts/evaluation/vinamilk-ocr-2011-scan-diagnostic/paired-comparison.json),
  [raw engine reports](../../artifacts/evaluation/vinamilk-ocr-2011-scan-diagnostic/),
  and the reusable [Kaggle diagnostic notebook](../../notebooks/kaggle_ocr_scan_diagnostic.ipynb).

  **Production-parser follow-up (v2; three pages):** the existing
  `DocumentProcessor` was run on all three visually reviewed pages with text
  pages at 108 DPI and table OCR at 180 DPI. The evaluator first rasterizes
  each selected page at 216 DPI to remove embedded, unreviewed OCR text layers;
  this ensures the upload parser actually exercises image OCR. Tesseract PSM 11
  recovered 17/17 selected rows, 34/34 selected numeric cells, all 6/6
  period headers and 20/20 visually checked value-cell bounding boxes on the
  two balance-sheet pages. The parser now retains OCR word boxes per table row
  in the existing JSONB table metadata, so review and evaluation can inspect
  source positions. In the original v2 parser run, only the fully transcribed income-statement page
  was scored for CER/WER (0.443667/0.582524); the balance-sheet pages used
  targeted row/value anchors. A v3 reference refresh below adds full-page text
  scores for those balance-sheet pages.
  This is one engine on three pages from one third-party packet, not a paired
  OCR comparison or representative quality estimate. The coordinate labels
  were located from the PDF text layer and visually checked, not independently
  click-annotated; wider and independently annotated coverage remains needed.
  A separate paired OCR-engine diagnostic now uses the exact same three
  180-DPI page renders and hashes. Tesseract PSM 3, PaddleOCR 3.7.0 (CPU), and
  EasyOCR 1.7.2 (CUDA) scored micro-CER/WER 0.840715/1.126214,
  0.373737/0.592233, and 0.468531/0.533981. They matched 0/17, 0/17, and
  0/17, 9/17, and 2/17 selected complete table rows for Tesseract, EasyOCR
  and Surya; selected cell-string presence was 50/51, 34/51, 50/51, and 51/51
  respectively. Surya scored micro-CER/WER
  0.316239/0.349515 at 9.775 s/page on CUDA; PaddleOCR averaged 67.722 s/page
  on CPU and EasyOCR 3.920 s/page on CUDA. Hardware and engine runtimes differ,
  so timing is not a controlled comparison. A reference refresh adds visually
  reviewed full-page text for both balance-sheet pages, giving all three pages
  full-text coverage. The two new transcriptions used the PDF text layer as an
  aid, so they are not independent double-keyed labels. Cached engine output
  was rescored without rerunning OCR: Tesseract/Paddle/Easy/Surya now score
  CER 0.693200/0.162611/0.449397/0.166705 and WER
  0.912844/0.330275/0.540367/0.182569. Paddle has the lowest CER, Surya the
  lowest WER, and EasyOCR matches the most complete rows (9/17). Cell-string
  presence still ignores row/column assignment. These
  scores are diagnostic for this third-party sample, not engine selection. The
  original paired artifact is
  [`vinamilk-ocr-2011-v2-four-engine-comparison-20260929.json`](../../artifacts/evaluation/vinamilk-ocr-2011-v2-four-engine-comparison-20260929.json);
  its reference-updated rescore is
  [`vinamilk-ocr-2011-v3-four-engine-comparison-20260929.json`](../../artifacts/evaluation/vinamilk-ocr-2011-v3-four-engine-comparison-20260929.json),
  using [v3 labels](../../data/evaluation/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v3.json).
  Reports
  are in [`ocr-kaggle-v2`](../../artifacts/evaluation/ocr-kaggle-v2/); rebuild
  the refreshed scores with `scripts/compare_ocr_reports.py --rescore-references`
  and the v3 labels. The tool verifies exact page identity and source/render
  hashes before rescoring cached predictions.
  **Live upload-path verification (2026-09-29):** three selected source pages
  were rasterized at 216 DPI into an image-only PDF, uploaded through the
  authenticated app endpoint, processed to `ready`, and read back through the
  admin chunks, tables and private-source endpoints. The database contained
  9 OCR-marked chunks and 3 tables with 58 rows; the downloaded source hash
  matched the uploaded bytes. A finance analyst saw the finance-only document
  in the dashboard while an employee did not. The temporary rows and Storage
  object were deleted and read-back confirmed zero remaining records. This is
  a single real-document integration smoke, not broad upload-quality evidence;
  its record is
  [`vinamilk-scan-upload-live-e2e-20260929.json`](../../artifacts/evaluation/vinamilk-scan-upload-live-e2e-20260929.json).
  Reproduce with
  `uv run python scripts/evaluate_scan_document_processing.py --dataset data/evaluation/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v2.json --tesseract-psm 11 --tesseract-table-psm 3 --render-scale 1.5 --table-render-scale 2.5 --output artifacts/evaluation/vinamilk-scan-document-processor-2011-three-pages-v2-20260929.json`.
  See the [labels](../../data/evaluation/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v2.json)
  and [run artifact](../../artifacts/evaluation/vinamilk-scan-document-processor-2011-three-pages-v2-20260929.json).

  **Historical table-only run (v5):** a manually checked Vietnamese 2024
  balance-sheet table has 16
  rows with the 2024 and 2023 values, rendered from born-digital PDF page 91
  (printed pages 180–181). The Tesseract 5.5.3 baseline at 180 DPI scored
  CER/WER 0.080207/0.140625 and exact row recall 8/16 (0.5); a row counts only
  when the normalized `label + 2024 value + 2023 value` sequence appears
  contiguously in recognized text. This measures row-preserving linearized
  output, not spatial cell association.
  The per-page report retains the raw recognized text and exact row indices so
  misses can be audited. This one-table result is diagnostic, not a general
  table-accuracy estimate.
  Reproduce it with `uv run python scripts/evaluate_ocr.py --dataset
  data/evaluation/vinamilk_ocr_ground_truth_v5.json --engines tesseract --dpi
  180 --output artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract-v5.json`.
  [Dataset](../../data/evaluation/vinamilk_ocr_ground_truth_v5.json) and
  [Tesseract report](../../artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract-v5.json).
  EasyOCR 1.7.2/T4 has completed on the identical v5 hashes: micro-CER/WER
  0.175882/0.348442 and exact table row recall 2/16. Its recognition output
  groups labels and numeric columns separately, which explains why it can
  recognize the cell text but fails this row-preserving score. Paired with
  local-CPU Tesseract, hash verification passed; see the
  [v5 comparison](../../artifacts/evaluation/vinamilk-ocr-easy-tesseract-v5-comparison.json)
  and [EasyOCR report](../../artifacts/evaluation/ocr-kaggle-easy/vinamilk-ocr-easyocr-v5.json).
  Surya 0.17.1/T4 has completed on the same v5 hashes: micro-CER/WER
  0.075829/0.151558 and exact table row recall 14/16 (0.875). Initialization
  took 156.223 s; mean inference was 3.962 s/page (15.144 pages/minute), peak
  process RSS 4,395.629 MiB, and PyTorch CUDA peak allocated/reserved memory
  2,354.048/2,670 MiB. PaddleOCR 3.7.0/CPU has completed on the same hashes:
  micro-CER/WER 0.087941/0.211048, exact row recall 0/16, cell-text presence
  recall 32/48 (0.667), 30.537 s/page after 45.849 s initialization and
  3,437.094 MiB process peak RSS. Across the 16-row table's 48 expected label
  and value cells, cell-text presence recall is 40/48 (0.833) for Tesseract,
  47/48 (0.979) for EasyOCR, 47/48 (0.979) for Surya, and 32/48 (0.667) for
  PaddleOCR. This complementary score checks text presence only and ignores
  row/column association; the stricter row score checks each label and both
  year values contiguously. The difference shows why neither score alone
  measures table reconstruction. Use the hash-checked
  [four-engine comparison](../../artifacts/evaluation/vinamilk-ocr-paddle-easy-surya-tesseract-v5-comparison.json)
  to inspect per-page hypotheses. These are small-pilot diagnostic results,
  not a production model selection. This v5 all-page accuracy run is
  superseded by corrected v6 labels; table-only metrics remain valid. The
  older Surya v4 kernel is complete in v6, not queued.
  A Vietnamese physical scan and broader cell/layout annotations remain open.
  Rebuild the comparison and both table scores from the saved raw hypotheses
  with:

  ```bash
  uv run python scripts/compare_ocr_reports.py --dataset data/evaluation/vinamilk_ocr_ground_truth_v5.json \
    artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract-v5.json \
    artifacts/evaluation/ocr-kaggle-easy/vinamilk-ocr-easyocr-v5.json \
    artifacts/evaluation/ocr-kaggle-surya/vinamilk-ocr-surya-v5.json \
    artifacts/evaluation/ocr-kaggle-paddle/vinamilk-ocr-paddleocr-v5.json \
    --output artifacts/evaluation/vinamilk-ocr-paddle-easy-surya-tesseract-v5-comparison.json
  ```
- **Production upload-parser protocol (v6; not paired with the earlier v4 run):**
  the current upload parser used PSM 11 on the two physical scans. It measured
  micro-CER/WER 0.038557/0.155425; per-page CER/WER were 0.008830/0.042254 and
  0.047134/0.185185. The [v6 PSM 11 artifact](../../artifacts/evaluation/vinamilk-scan-document-processor-psm11-v6-20260928.json)
  was paired against PSM 3 on the exact same v6 dataset, source-PDF and
  cropped-PDF hashes. PSM 3 scored micro-CER/WER 0.065744/0.167155; on the
  Charter introduction both modes scored 0.008830/0.042254, while on the
  governance contents page PSM 11 scored 0.047134/0.185185 vs PSM 3
  0.082166/0.200000. The [paired PSM 3 artifact](../../artifacts/evaluation/vinamilk-scan-document-processor-psm3-v6-20260928.json)
  supports retaining PSM 11 for this two-page English scan sample. One-run
  mean latency was 1.174 s for PSM 11 and 2.004 s for PSM 3, but this is not a
  controlled speed comparison. This small scan set does not establish a
  Vietnamese financial-scan winner. Earlier v4 repeats used a different
  dataset hash and remain historical diagnostics only.
- The scanned Vietnamese 2011 statement was then run through the actual
  `DocumentProcessor` PDF path. OCR produced 1 structured table with 17 rows
  and date-labeled amount columns (`31/12/2011`, `31/12/2010`) after excluding
  recurring account/note numbers and recognizing the OCR'd period header. The
  result is not accurate enough for automatic financial use: OCR CER/WER are
  0.430458/0.566343 and several amount strings contain recognition errors.
  Regression tests cover account codes, note references, period headers and
  side-by-side financial tables. A paired render-scale run on the official
  Vinamilk 2024 balance-sheet page (synthetic raster of printed pages 180–181)
  returns both table blocks and all three normalized value anchors at 108 and
  180 DPI; exact table anchors improve from 0/3 to 2/3 at 180 DPI. On the
  scanned 2011 statement, the split-resolution path reaches 14/14 reviewed
  numeric cells. A separate value-cell score checks ordered amounts in the
  same row without requiring a clean label: at 180 DPI the 2021 raster PDF
  reaches 2/2 pairs (image upload 1/2), the 2022 PDF 0/2 (image 1/2), and the
  2023 PDF/image 0/2; label-plus-value anchors still fail on these 2021–23
  cases. The 2024 scan-like input is generated from a born-digital report, not
  a physical scan. See the
  paired [108 DPI table render](../../artifacts/evaluation/vinamilk-document-extraction-table-render-sweep-108dpi-20260929.json)
  and [180 DPI table render](../../artifacts/evaluation/vinamilk-document-extraction-table-render-sweep-180dpi-20260929.json).
  The evaluation report includes extracted rows for review. A separate live
  database roundtrip persisted and independently read back the exact 17 rows,
  then verified temporary-row cleanup; it did not exercise HTTP upload or
  Storage. Holding text OCR at PSM 11 and scoring seven reviewed financial
  rows, table-word PSM 3/4/6/11/12 at 108 DPI matched 10/14, 13/14, 9/14,
  0/14 and 0/14 numeric cells. At 180 DPI, PSM 3 and 4 each recovered 14/14
  numeric cells and both headers; a separate 108 DPI page-text pass retained
  the baseline CER/WER 0.430458/0.566343. Cropping the gross-profit amount
  confirmed Tesseract recognizes the correct leading digit in isolation; its
  full-page table pass is the source of the 108 DPI error. The table comparison
  ignores punctuation but preserves sign and digits; row labels use
  accent-folded similarity. This one-page result does not establish accuracy
  across layouts or safe automatic financial publication. Reproduce the
  split-resolution production path with `uv run python
  scripts/evaluate_scan_document_processing.py --dataset
  data/evaluation/vinamilk_ocr_ground_truth_2011_scan_diagnostic.json
  --tesseract-psm 11 --tesseract-table-psm 3 --render-scale 1.5
  --table-render-scale 2.5`; PSM 4 gives the same reviewed score. See the [PSM 3 report](../../artifacts/evaluation/vinamilk-scan-document-processor-2011-table-psm3-20260929.json),
  [PSM 4 report](../../artifacts/evaluation/vinamilk-scan-document-processor-2011-table-psm4-20260929.json),
  [PSM 6 report](../../artifacts/evaluation/vinamilk-scan-document-processor-2011-table-psm6-20260929.json),
  [PSM 11 report](../../artifacts/evaluation/vinamilk-scan-document-processor-2011-table-psm11-20260929.json),
  [PSM 12 report](../../artifacts/evaluation/vinamilk-scan-document-processor-2011-table-psm12-20260929.json),
  [split-resolution PSM 3 report](../../artifacts/evaluation/vinamilk-scan-document-processor-2011-separated-scales-psm3-20260929.json),
  [split-resolution PSM 4 report](../../artifacts/evaluation/vinamilk-scan-document-processor-2011-separated-scales-psm4-20260929.json),
  and [live database readback](../../artifacts/evaluation/vinamilk-scan-table-live-database-readback-20260929.json).
- A completed Kaggle EasyOCR 1.7.2/Tesla T4 run on v3 adds a paired-engine
  result for the Charter scan introduction: CER/WER 0.039735/0.112676 at
  180 DPI. Across all four v3 regions its micro-CER/WER is 0.066667/0.233607;
  the three non-scan regions retain the same image/reference hashes as the
  shared v2 comparison. This version predates the second governance scan and
  used the older evaluator without memory/throughput telemetry, so it is not
  comparable to the current five-region protocol for resources. Its dataset
  hash is `31944ac8864b4ba9b59c78500ce0656a24989846b9ff4c80e3552df2b9ac824e`;
  report: `artifacts/evaluation/ocr-kaggle-easy/vinamilk-ocr-easyocr-v3.json`.
  A hash-verified v3 comparison against Tesseract on the same four rendered
  pages scored micro-CER/WER 0.066667/0.233607 vs 0.124399/0.295082;
  artifact: `artifacts/evaluation/vinamilk-ocr-charter-scan-v3-comparison.json`.
- EasyOCR 1.7.2 completed on Kaggle Tesla T4 against the full v4 set: the same
  five manually reviewed 180-DPI regions, including both image-only governance
  scans, as the Tesseract v4 report. Hash-verified micro-CER/WER is
  0.097521/0.260700 vs 0.399339/0.297665. EasyOCR scored 0.039735/0.112676 on
  the Charter introduction and 0.126115/0.285185 on governance contents;
  Tesseract scored 0.037528/0.084507 and 0.654140/0.300000. EasyOCR runtime
  was 1.213 s/page after 9.746 s initialization (49.472 pages/minute), with
  1,543.852 MiB process peak RSS and 1,800.277 MiB allocated / 2,570 MiB
  reserved PyTorch CUDA memory. This is a small text-only pilot with no
  table/layout labels and does not establish a model winner. PaddleOCR and
  Surya have not been run against these v4 pages. Report:
  `artifacts/evaluation/ocr-kaggle-easy/vinamilk-ocr-easyocr-v4.json`; paired
  hashes and metrics:
  `artifacts/evaluation/vinamilk-ocr-governance-scans-v4-comparison.json`.
- A separate protocol now evaluates the actual PDF upload parser on those same
  two preserved source-page regions. The `DocumentProcessor` path (PyMuPDF
  plus Tesseract fallback, nominal 108 DPI) scored aggregate micro-CER 0.070687
  and micro-WER 0.173021; mean latency was 5.718 s/page (17.746 pages/minute),
  process peak RSS 72.395 MiB, and child-process peak RSS 110.453 MiB. By
  region, the Charter introduction scored CER/WER 0.037528/0.098592 and the
  governance contents page 0.080255/0.192593. These differ from the direct
  180-DPI crop run above because rendering and OCR invocation follow the
  production PDF path; do not compare the protocols as if they were identical
  engine settings. This remains a two-page, English-only Tesseract pilot with
  no table-cell/layout labels or paired engines. Reproduce it with
  `uv run python scripts/evaluate_scan_document_processing.py`; artifact:
  `artifacts/evaluation/vinamilk-scan-document-processor-v1.json`.
- Sampled real-document extraction evaluation uses the manually transcribed,
  visually checked fixture `data/evaluation/vinamilk_document_extraction_cases.json`.
  Re-run compactly with
  `uv run python scripts/evaluate_document_extraction.py --compact --output artifacts/evaluation/vinamilk-document-extraction-compact-20260928.json`.
  The compact report preserves source/render hashes, scores, Tesseract version
  and traineddata hashes while omitting raw parser dumps. Native 2020
  financial-infographic parsing and rule-based KPI extraction each match 2/2
  anchors. The current production text OCR setting is PSM 11 and matches 0/2; an
  explicit PSM 3 rerun matches 2/2 on both raster-PDF and image-upload paths,
  reproducing the older v9 result. On the 2024 balance-sheet page, native
  parsing and KPI candidates match 3/3. PSM 11 matches 1/3 exact OCR text
  anchors on each raster path; PSM 3 matches 0/3 exact on raster-PDF and 2/3
  on image upload. Both PSM 3 paths retain all 3/3 values after normalization,
  while PSM 11 retains all values only on the raster-PDF path. Both table
  modes detect 2/2 regions. A separate table-only PSM 6 run, with text PSM 3,
  improves normalized table-anchor recall from 2/3 to 3/3 on the image-upload
  path and retains 3/3 on raster-PDF; exact table anchors remain error-prone
  (0/3 on image upload, 1/3 on raster-PDF). This supports PSM 6 for image
  table word boxes, not a claim of accurate financial OCR generally. The v9 /
  current difference is explained by the active PSM changing from 3 to 11,
  which the older report did not record. Current reports record Tesseract
  5.5.3, `vie`/`eng` traineddata hashes and explicit PSM/render scale. PSM 11
  remains the text OCR default because the separate mixed-layout poster
  CER/WER comparison favored it; these two financial pages are not enough to
  change that global text setting. PDF table OCR remains PSM 3; image table
  OCR now defaults to PSM 6. Reproduce the latter comparison with
  `uv run python scripts/evaluate_document_extraction.py --compact --tesseract-psm 3 --tesseract-table-psm 6 --output artifacts/evaluation/vinamilk-document-extraction-compact-table-psm6-20260928.json`.
  The [table PSM 6 report](../../artifacts/evaluation/vinamilk-document-extraction-compact-table-psm6-20260928.json), [PSM 11 compact report](../../artifacts/evaluation/vinamilk-document-extraction-compact-20260928.json)
  and [paired PSM 3 report](../../artifacts/evaluation/vinamilk-document-extraction-compact-psm3-20260928.json)
  preserve comparable hashes and scores. The table strategy sweep records the
  per-strategy shapes and anchor scores. The evaluation fixture contains two
  born-digital source pages and five fields; raster copies are synthetic, not
  real scans. Results remain diagnostic rather than representative accuracy.
- A separate 14-region replay sends the v9 source-page crops through the
  existing upload `DocumentProcessor` path, rasterizing each crop at 216 DPI
  first so native PDF text cannot bypass OCR. The processor then renders text
  at 108 DPI and tables at 180 DPI, using local Tesseract 5.5.3, text PSM 11
  and table PSM 3. All 14 regions are text-scored (micro-CER 0.120957,
  micro-WER 0.245435; mean 1.835 s/page).
  Table structure is a separate score: 17/33 reviewed rows and 34/66 numeric
  cells matched. The three 2011 physical-scan pages alone match 17/17 rows
  and 34/34 cells. The two balance-sheet pages also match 20/20 reviewed
  value-cell locations; their reference boxes were derived from the PDF text
  layer and visually checked, not independently click-annotated. The
  rasterized 2024 balance-sheet region detects no table and is scored
  explicitly as 0/16 rows and 0/32 cells. That is an OCR-only failure
  on a born-digital source page; it does not evaluate the normal native-PDF
  extraction path, which is covered by the separate document-extraction
  fixture above. Reproduce with
  `uv run python scripts/evaluate_scan_document_processing.py --dataset data/evaluation/vinamilk_ocr_ground_truth_v9.json --all-pages --output artifacts/evaluation/vinamilk-upload-document-processor-v9-14regions-20260929.json`.
  See the [14-region parser report](../../artifacts/evaluation/vinamilk-upload-document-processor-v9-14regions-20260929.json).
- A paired CPU-only v9 OCR benchmark reran Tesseract 4.1.1, PaddleOCR 3.7.0,
  EasyOCR 1.7.2 and Surya 0.17.1 against the same 14 reviewed English/Vietnamese
  regions at 180 DPI. All four reports have the same dataset SHA-256
  (`1847715f…300e1b`), identical PDF/render hashes and 14/14 successful pages.
  Micro-CER is 0.361902/0.073542/0.198645/0.074924 and micro-WER is
  0.491573/0.181882/0.337430/0.116573 (Tesseract/Paddle/Easy/Surya). Paddle
  has lowest CER; Surya has lowest WER, 16/33 exact table rows and 98/99 table
  cell strings. This is a paired CPU-profile comparison, but the Kaggle report
  could not identify the CPU model; latency/RSS are descriptive, not hardware
  generalizations. Six pages are Vietnamese; references combine manual review
  with visually checked PDF text-layer assistance, and cell-string presence
  does not measure spatial reconstruction. The result is diagnostic, not a
  production-engine selection. See the [comparison](../../artifacts/evaluation/vinamilk-ocr-v9-cpu-four-engine-comparison-20260929.json),
  [raw reports](../../artifacts/evaluation/ocr-kaggle-v9-cpu/) and
  [CPU notebook](../../notebooks/kaggle_ocr_v9_cpu_paired.ipynb).
- **Corrected 2011 Vietnamese scan crop (v2):** the CafeF-hosted PDF is a
  second scanner capture of the same signed 2011 filing as the earlier
  third-party diagnostic. The reference covers a visually checked crop of the
  income statement and corrects v1's scope and prior-period transcription
  mismatches. All four Kaggle reports share dataset SHA-256
  `e714090fd4389fc53715d018dae2238718742aa46cf01e94a29140e0d0fe7d35`, source
  PDF SHA-256 `d4bd33e16bed1d176f215830135456059366318c1b9a7071976554450a08ddf6`,
  and rendered crop SHA-256
  `19af16ae6548b42824584107ba3bea3f1435010c00bfe5d751e2c1c032498ea3`. At
  180 DPI, Tesseract 4.1.1 / PaddleOCR 3.7.0 / EasyOCR 1.7.2 / Surya 0.17.1
  scored CER 0.171683 / 0.279070 / 0.511628 / 0.493160 and WER 0.288462 /
  0.475275 / 0.659341 / 0.678571. Ordered label/value row matches were 1/7,
  0/7, 4/7, and 0/7; selected cell-string presence was 14/21, 14/21, 19/21,
  and 17/21. Tesseract/Paddle ran on CPU; Easy/Surya on Tesla T4, so runtimes
  are descriptive only. The reference was adapted from a visually checked
  duplicate capture and checked against this page, not independently
  double-entered. This one-page, third-party diagnostic is not model-selection
  evidence. The corrected row metric requires label/value strings in order
  while allowing intervening table-column text; it does not establish spatial
  row/column association. Historical artifacts retain the former contiguous
  string rule. See the [comparison](../../artifacts/evaluation/vinamilk-ocr-2011-cafef-scan-v2-four-engine-comparison-20260929.json),
  [labels](../../data/evaluation/vinamilk_ocr_2011_cafef_scan_v2.json),
  [raw reports](../../artifacts/evaluation/ocr-kaggle-vinamilk-2011-cafef-scan-v2/)
  and [notebook](../../notebooks/kaggle_vinamilk_2011_cafef_scan/kaggle-vinamilk-2011-cafef-scan.ipynb).
- The issuer-hosted 2026 Company Charter is image-only across all 46 pages.
  A single-annotator visual transcription of page 8 adds a paired English
  legal-document scan diagnostic. At 180 DPI, Tesseract 4.1.1, PaddleOCR 3.7.0,
  EasyOCR 1.7.2 and Surya 0.17.1 scored CER 0.011122/0.002944/0.004253/0.017991
  and WER 0.030888/0.007722/0.019305/0.052124. PaddleOCR has the lowest errors
  against this draft reference; the single page is not independently reviewed
  and cannot select an engine. Tesseract/Paddle ran on CPU; EasyOCR/Surya on
  Tesla T4, so runtime and memory are descriptive only. All four reports match
  the dataset, source-PDF and rendered-page hashes. Reproduce one engine per
  kernel using [`kaggle-charter-scan-page8.ipynb`](../../notebooks/kaggle_charter_scan_page8/kaggle-charter-scan-page8.ipynb)
  and private dataset `ltrngnhn/vinamilk-charter-scan-page8-assets` (version 2).
  See the [paired comparison](../../artifacts/evaluation/vinamilk-ocr-charter-scan-page8-four-engine-comparison-20260929.json),
  [labels](../../data/evaluation/vinamilk_ocr_charter_scan_en_v1.json), and
  [raw reports](../../artifacts/evaluation/ocr-kaggle-charter-scan-page8/).
  This does not improve Vietnamese physical-scan coverage.
- A separate v4 label set adds raster-derived boxes for 14 value cells across
  seven manually transcribed rows on the 2011 Vietnamese income-statement scan.
  The boxes were mapped from the exact 180-DPI clipped-page image to PDF points,
  visually checked by one reviewer and located without PDF text-layer spans.
  Running the upload parser on that page matched 7/7 rows and 14/14 values;
  13/14 boxes met IoU >= 0.3. The unmatched box is the 2011 dash in the
  minority-interest row: its value is correct but the parser does not emit a
  usable box for that small dash. This is a single-page, single-source diagnostic,
  not independent multi-reviewer gold or paired engine evidence. Run
  `uv run python scripts/evaluate_scan_document_processing.py --dataset data/evaluation/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v4.json --case-id income-statement-scan-2011-vi --output artifacts/evaluation/vinamilk-scan-document-processor-2011-raster-cell-labels-20260929.json`.
  The evaluator now maps short year keys to extracted full-date columns, which
  fixes the prior false-zero coordinate score when expected box keys were
  `2011`/`2010` and parser columns were `31/12/2011`/`31/12/2010`.
- PaddleOCR is an optional benchmark extra (`uv sync --extra ocr-paddle`), so
  the standard app environment does not need its large runtime. The runner
  accepts `--max-pages` for smoke runs and limits Paddle CPU threads. Earlier
  local Paddle runs were OS-killed, but the Kaggle CPU-wheel run completed on
  the identical three-crop labels. The standard `.venv` does not include the
  optional OCR dependencies.
- The OCR evaluator records each engine's installed package version, model
  initialization duration/error, actual runtime device where available, and CUDA availability in its report. Failed
  model initialization remains an explicit unscored engine and does not produce
  empty-text CER/WER values. On a higher-memory/GPU host, run all proposal
  engines against the same manually reviewed crops with:
  `uv run python scripts/evaluate_ocr.py --dataset data/evaluation/vinamilk_ocr_ground_truth_v2.json --engines paddleocr easyocr surya tesseract --dpi 180 --output artifacts/evaluation/vinamilk-ocr-proposal-comparison.json`.
  Add physical scanned pages and manually labeled table/layout regions before
  using this comparison to select a production OCR engine.
- The evaluator renders the selected PDF crops once, then initializes, runs,
  and releases one engine before loading the next. Run a single engine with
  `--engines paddleocr` (or `easyocr` / `surya`) to isolate setup and failures;
  use the same dataset, DPI, and crop hashes for paired results. This lowers
  peak memory versus holding all engines at once, but it cannot make a model
  fit if one engine alone exceeds available memory.
- For a no-cost accelerator, Kaggle Notebooks documents a weekly GPU quota of
  30 hours or sometimes more depending on demand ([GPU usage guide](https://www.kaggle.com/docs/efficient-gpu-usage)); this is the best fit for a repeatable multi-engine batch. Colab offers free GPU access but says availability and limits fluctuate ([FAQ](https://research.google.com/colaboratory/faq.html)). Hugging Face ZeroGPU is convenient for a quick demo, but a free account currently gets five GPU minutes per day and its Spaces integration is Gradio/PyTorch-oriented ([ZeroGPU docs](https://huggingface.co/docs/hub/spaces-zerogpu)), so it is not the recommended host for the full Paddle/EasyOCR/Surya benchmark.
- The local host has no CUDA device; at the latest check only about 1.7 GiB
  was `MemAvailable` and swap was nearly exhausted. Do not load OCR models
  here while the app is running. The benchmark corpus is public Vinamilk
  material; never upload private enterprise files to a third-party free
  notebook. Record the runtime, package/model versions, peak RAM/VRAM and
  failures with each result.
- Reproducible cloud entry point: `notebooks/kaggle_ocr_benchmark.ipynb`.
  Select one engine per session, enable Internet + GPU for EasyOCR/Surya
  (the PaddleOCR fallback and Tesseract can run on CPU), and add a Kaggle
  private dataset [vinamilk-ocr-v7-benchmark-assets](https://www.kaggle.com/datasets/ltrngnhn/vinamilk-ocr-v7-benchmark-assets).
  The notebook discovers the attached dataset by its project files, including
  the five bundled source PDFs used by its ten reviewed regions. Rebuild the
  bundle with `uv run python scripts/package_ocr_benchmark.py
  build/kaggle-ocr-v7-dataset` and keep the Kaggle dataset private. The notebook
  writes its JSON into `/kaggle/working`. Versions are pinned in the notebook. PaddleOCR 3.7 uses
  the official PaddlePaddle 3.3.0 CPU wheel because the 1.9 GB CUDA wheel
  failed pip validation on Kaggle; the report records the engine's actual
  runtime device. EasyOCR 1.7.2 uses the notebook's
  PyTorch CUDA runtime. Surya is pinned to 0.17.1 with Transformers 4.57.3;
  later Surya releases change the API/runtime and are outside this comparison.
  Its T4 detection/recognition batches are capped to fit the assigned GPU.
  The ten-region v7 reports are complete: Surya scored micro-CER/WER
  0.043233/0.090403 (T4), PaddleOCR 0.043609/0.108484 (CPU), EasyOCR
  0.110025/0.248261 (T4), Tesseract PSM 11 0.127318/0.197497 (CPU), and
  Tesseract PSM 3 0.272556/0.263561 (CPU). Reproduce the comparison with
  `scripts/compare_ocr_reports.py` using the linked raw reports. The Kaggle
  runs are [EasyOCR](https://www.kaggle.com/code/ltrngnhn/vinamilk-ocr-v7-easyocr),
  [PaddleOCR](https://www.kaggle.com/code/ltrngnhn/vinamilk-ocr-v7-paddleocr),
  and [Surya](https://www.kaggle.com/code/ltrngnhn/vinamilk-ocr-v7-surya).
  Surya requires `transformers==4.57.3` with `surya-ocr==0.17.1`; the newer
  default Transformers version failed during inference. The OCR evaluator
  selects Paddle's CUDA device through Paddle directly and reports the physical
  GPU via `nvidia-smi` when PyTorch CUDA telemetry is unavailable. The result
  remains a small diagnostic, not evidence for production model selection.
- The evaluator records the assigned PyTorch-visible GPU and each engine's
  actual execution device. This
  reports assigned runtime hardware, not measured peak VRAM/RAM.
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
- A live DOCX-table integration smoke on 2026-09-28 uploaded one generated
  table through the uploader UI/API path, observed `ready`, read back the
  labeled table chunk and structured row through admin endpoints, and reopened
  the exact source bytes from private Storage. Role-filtered BM25 returned its
  unique row marker to `finance_analyst` and not to `employee`. The temporary
  database rows were deleted and the document's absence verified; the Storage
  remove request completed, but object absence was not independently
  read-verified. The run is recorded in
  [the live DOCX integration artifact](../../artifacts/evaluation/vinamilk-docx-table-live-e2e-20260928.json);
  it verifies integration behavior for one generated English fixture, not
  general table extraction accuracy or LLM answer quality.
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

The manually reviewed financial extraction fixture now covers five Vinamilk
annual-report pages from 2020–2024, with eleven labels/values transcribed from
rendered pages and checked against period and unit. Run it with:

```sh
uv run python scripts/evaluate_document_extraction.py \\
  --cases data/evaluation/vinamilk_document_extraction_cases.json --compact \\
  --output artifacts/evaluation/vinamilk-document-extraction-multiyear-v3-20260928.json
```

The 2020 highlight and 2024 balance-sheet figures are in VND billion and VND
million respectively; audited 2021–2023 income-statement values are in VND.
The rule-based candidate extractor matched all 11 expected fields with 1.00
anchor precision on these born-digital pages. The synthetic Tesseract raster
conditions matched 1/11 exact text anchors and 3/11 normalized text anchors;
normalized table-anchor recall was also 3/11 (exact table-anchor recall 0/11).
These OCR pages are rasterizations of born-digital reports, not scanned source
documents, and the sample is too small for accuracy or model-selection claims.
Real-report regression coverage also found line-wrapped statement labels and
the Vietnamese “lợi nhuận sau thuế TNDN” wording; metric matching now spans
whitespace and recognizes that label. This verifies candidate creation and
period-column selection, not OCR quality.

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

Earlier local PaddleOCR 2.10.0 inference was OS-killed (exit 137) on one
72-DPI page, and EasyOCR was killed during model loading. These failures were
resolved for the paired cloud pilot described above; they are historical
diagnostics, not the current benchmark status. The three-crop comparison still
does not satisfy scanned-document or layout/table evaluation. See
`technical/agents-and-evaluation.md` for current limits.

See [chunking](chunking.md) for per-path size settings and [proposal coverage](../README.md)
for remaining extraction requirements.
