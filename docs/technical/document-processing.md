# Document processing

This guide describes the supported upload and seed-ingestion paths. OCR fixture
definitions and measured results live in [the OCR evaluation guide](../../data/evaluation/ocr/README.md).

## Data flow

```text
seed manifest ─┐
               ├─> format processor ─> parser chunks + structured tables
user upload ───┘                          │
                                          ├─> processed_document_chunks
                                          └─> tokenize/embed ─> document_chunks
                                                               └─> retrieval
```

- Seed ingestion is orchestrated by `src/core/document_processing/ingest_documents.py`.
- Authenticated uploads enter through `/api/documents/upload` in `src/app/main.py`.
- `DocumentProcessor` dispatches by extension. Format processors parse content;
  database repositories persist output and state.
- Original uploads live in private Supabase Storage. Parsed, model-neutral chunks
  are stored before embeddings; `document_chunks` is the active retrieval index.
- Structured table rows are persisted separately from retrieval text so the UI
  can inspect structure while retrieval can use a readable serialization.
- Documents become searchable only when processing succeeds. Failed embedding
  work can be retried from persisted parsed chunks.

The manifest is a seed-source registry, not the source of dashboard values.
Commerce analytics reads the Commerce SQL schema, while uploaded documents
provide RAG context; see the [data flow](../README.md) and
[Commerce status](../commerce-decision-support.md).

## Module ownership

- `processors/document_processor.py`: upload format dispatch and shared metadata.
- `processors/pdf_processor.py`: native PDF text, Tesseract fallback, PDF tables,
  page metadata, and optional layout/formula adapters.
- `processors/pdf_layout_processor.py`: optional PaddleOCR layout processing.
- `processors/pdf_table_extractor.py`: native and OCR word-box table reconstruction.
- `processors/office_processor.py`: DOCX, PPTX, and XLSX Open XML parsing.
- `processors/text_processor.py`: TXT/Markdown decoding and common text chunking.
- `processors/image_processor.py`: standalone image OCR and table extraction.
- `src/core/chunking/`: shared chunk boundaries and token-aware splitting.
- `src/core/database/structured_store.py`: structured table persistence.

Keep processor output model-neutral. Token counts and vectors belong to the
embedding/index stage because tokenization limits vary by model.

## Supported input and behavior

`DocumentProcessor.SUPPORTED` is the authoritative extension list. It currently
includes PDF, DOCX, PPTX, XLSX, TXT, Markdown, PNG, JPEG, and TIFF. Seed ingestion
supports PDF and HTML. Legacy binary XLS is unsupported.

For PDFs, PyMuPDF extracts text when a page has a usable text layer. Pages with
no usable text can fall back to Tesseract (`vie+eng` by default); processor
callers can override the OCR language. The OCR evaluator uses each labeled
source language and records the effective setting per case. This is page-level
fallback; it does not replace readable PDF text with OCR. PDF tables use native
text-alignment extraction when available and OCR word boxes for scanned pages.
On text-rich pages, the parser also examines at most the two largest embedded
image regions (each at least 10% of page area). It appends region OCR and uses
its word boxes only when mean Tesseract confidence is at least 60/100. Text is
appended only when it contributes at least three distinct new word/number
tokens and those tokens make up at least 8% of the OCR token stream; single-digit
tokens do not count toward that text gate. OCR word boxes still go to table
extraction when the text gate rejects a region. These are conservative
heuristics, not accuracy scores; validate them on labeled scans before changing
thresholds or treating extracted tables as business facts. When an embedded
image is rejected for low confidence or too few recognized words, the page's
parser metadata records the reason and score; Admin Processing and OCR Lab show
that diagnostic beside the extracted output.

On scan-only pages where OCR word boxes also produce a structured table, the
prose chunk is rebuilt from words outside that table's body and header boxes.
This keeps corrected row values in the structured table chunk without indexing
conflicting full-page OCR values a second time. The prose chunk records the
effective table PSM, render scale, and `page_words_outside_structured_tables`
scope. Pages with no extracted structured table retain the original OCR text.
The PDF parser drops a short final text line only when it is an explicit
`Page n/m`, `Page n of m`, or `Trang n/m` counter; source pages and separate
`page_number` provenance remain unchanged.
Before OCR, Tesseract OSD checks page orientation; reported 90°, 180°, and
270° rotations with orientation confidence of at least 2.5 are corrected in the
raster only. A projection-profile pass then estimates small skew up to ±6° and
corrects it only when the best angle is at least 0.5° and improves the horizontal
text-line score by 10%. Table recognition runs on that corrected raster; table
and word boxes are transformed back to source PDF page coordinates afterward.
The chosen quarter-turn and deskew angle are recorded in OCR metadata. This is a
bounded heuristic, not arbitrary-angle correction. If OSD and OCR return little
text on a nonblank landscape scan, the parser also tries both sideways
quarter-turns and keeps a candidate only when it yields a recognizable table or
substantially more text. Adjacent-page table segments are linked only when
their column labels match exactly, the first ends in the bottom quarter, the
next starts in the top quarter, and there is a single unambiguous match. The
segments remain page-local records with their own source links; a title found on
either segment is copied to its linked neighbor. This does not combine them
into one structured record. OSD adds one Tesseract call per OCR page; a sparse
landscape scan can require up to two bounded retry calls.
The native-table gate also recognizes repeated aligned text columns, so
qualitative comparison matrices are not skipped just because they contain no
numbers. Commerce corpus ingestion persists detected rows in the structured
table store and indexes row-aware chunks with their column headers for RAG.
OCR/layout output records its engine, settings, extraction method, page, and
bounding boxes in parser metadata. Table title, section, units, and period are
best-effort context and may remain unavailable; they are not inferred from raw
parser diagnostics by the UI. When extraction finds an explicit table title,
each row-aware retrieval chunk repeats that title and stores it in chunk
metadata; structured rows remain separately available for inspection. The OCR
Lab shows Tesseract's mean word confidence for OCR-derived tables as a parser
diagnostic; it is not a probability or a measure of table accuracy.

PDF upload defaults are text PSM 11 at scale 1.5 and table PSM 3 at scale 2.5.
The OCR Lab exposes supported Tesseract PSM/scale options per test run; it uses
isolated `ocr_test_*` tables and does not create a corpus document, Storage
object, or embeddings. The Tester role is separate from document ACL roles.

`DOCUMENT_PADDLE_LAYOUT=true` enables the optional Paddle layout path.
`DOCUMENT_PADDLE_FORMULA_RECOGNITION=true` enables formula recognition and the
layout path. Both are off by default. Chart recognition is separately
controlled by `DOCUMENT_PADDLE_CHART_RECOGNITION` and defaults to off because
PP-Chart2Table adds a large model download and memory cost. Install the
`ocr-paddle` extra for the PP-Structure OCR dependencies; consult the OCR guide
before enabling these optional paths. The CPU adapter disables oneDNN because
PaddlePaddle 3.3.1 has a reported CPU inference failure in that path; this
avoids the runtime error but may reduce inference speed ([upstream issue](https://github.com/PaddlePaddle/Paddle/issues/79749)).

Office formats are parsed from Open XML. ZIP expansion limits are enforced
before XML parsing. DOCX tables retain labeled row text for retrieval and
structured rows for inspection. PPTX slide tables and XLSX worksheet tables use
the same structured representation. XLSX formulas and cached values are
preserved; the parser does not recalculate formulas.

Section titles are format-dependent metadata: Word headings, slide titles,
worksheet names, and recognizable PDF headings. OCR-only unnumbered headings
can be missed, so `section_title` may be null. A table's context is separate
from `structured_data` and parser `metadata` in OCR test persistence.

Optional image captions are generated content, disabled by default, and are not
valid source evidence for metric extraction. They must remain labeled as model
output in retrieval context.

## Dashboard data boundary

User uploads are parsed, chunked, embedded, and indexed as RAG knowledge. They
do not create dashboard observations. The Commerce dashboard reads the Commerce
SQL dataset; decision-support documents provide
retrieved policy or operating context. XLSX uploads are supported for document
Q&A, but uploaded HTML is unsupported; seed-corpus HTML ingestion is separate.

## Reproduce and verify

Run the app-upload parser smoke without external credentials:

```bash
uv run python tools/processing/evaluate_scan_document_processing.py \
  --output /tmp/commerce-scan-parser-smoke.json
```

Run OCR scoring against the labeled synthetic fixtures:

```bash
uv run python tools/processing/evaluate_ocr.py \
  --engines tesseract \
  --output /tmp/commerce-scan-ocr-smoke.json
```

These fixtures verify wiring and known table anchors, not real-world OCR
accuracy. They are synthetic and must not be indexed as Commerce policy or
business evidence. Current measured limitations, source hashes, and commands
for engine comparisons are maintained in [the OCR evaluation guide](../../data/evaluation/ocr/README.md).

On 2026-10-06, the Admin processing API returned HTTP 200 for the active
Shopee Uni Vietnamese inventory guide (`SHOPEE-UNI-INVENTORY-MANAGEMENT-VN`):
17 persisted parser passages across 17 pages, with Tesseract metadata on 11
passages across 11 pages. This confirms OCR passages from an image-heavy public
operating PDF reach persisted processing output. A later human transcription of
two clear regions on page 11 (heading/instruction and replenishment callouts)
scored micro-CER 0.015873 / micro-WER 0.041096 after rasterizing those crops to
force OCR ([dataset](../../data/evaluation/ocr/commerce_shopee_inventory_page_transcriptions.json),
[run](../../artifacts/evaluation/ocr/pipeline/shopee-page11-selected-region-ocr-20261007.json)).
This is a single-reviewer, selected-region check on a mixed vector/image
PowerPoint export, not a full-page transcription or physical-scan benchmark.
The screenshot text still has OCR errors and must be checked against the
original page before relying on it.

On 2026-10-08, Tester uploaded that same official PDF through OCR Lab. The
persisted run contains 17 page previews, 18 parser chunks, and no structured
tables; page 11's preview returned HTTP 200 and its chunk retained the four
reviewed inventory phrases. Before the parser fix, PyMuPDF had emitted 15 empty
or title-fragment table candidates from those screenshot-heavy pages. The PDF
table extractor now accepts a native candidate only when it has at least three
data rows with two populated cells, matching the existing text/OCR table floor.
The false tables no longer block OCR fallback. The screenshot's product grid
remains unstructured OCR text, so this result demonstrates page-level OCR and
persisted OCR Lab review data (outside the production knowledge base), not
reliable extraction of the screenshot table or physical-scan accuracy
([upload/API audit](../../artifacts/evaluation/ocr/pipeline/commerce-shopee-inventory-upload-lab-20261008.json),
[current page-11 anchor run](../../artifacts/evaluation/ocr/pipeline/shopee-inventory-selected-anchor-current-20261008.json)).

A selected-page check on the image-heavy Amazon FBA Restock Guide (pages 6–7;
English, upload defaults) exposed two issues: standalone screenshot text could
replace the real page heading, and embedded-image OCR added low-novelty UI
fragments such as `Flige`. Native visual headings now take precedence, wrapped
headings are joined, and low-novelty OCR text is omitted while table word boxes
remain available. A fresh parser run retained the real section titles; page 6
used native text and matched its three selected anchors, while page 7 used
Tesseract and matched all six. The regression tests also verify a mixed text/table
page still extracts table rows when OCR text is rejected. This two-page smoke
uses an image-heavy PDF with a partial text layer, not a physical scan; its
native layer still includes duplicated screen text and neither page yielded a
structured table. Do not treat it as full-page accuracy evidence. A separate
forced-raster check at the upload defaults matched all 9/9 selected phrase
anchors in 2.811 seconds per page; CER/WER remain unavailable because labels are
partial ([anchor labels](../../data/evaluation/ocr/commerce_amazon_fba_restock_page_anchors.json),
[run](../../artifacts/evaluation/ocr/pipeline/amazon-fba-restock-selected-page-upload-smoke-20261008.json)).
The two-page excerpt was uploaded through the live Tester OCR Lab API both
before and after the text gate. The follow-up run
`f01bac00-29f2-4090-bce8-a632a75847a4` appears in the Tester run list; upload,
detail readback, and both PNG previews returned HTTP 200. It remains in isolated
OCR test tables, outside production retrieval. The audit records the earlier
run and the post-change comparison ([API readback](../../artifacts/evaluation/ocr/pipeline/commerce-amazon-fba-ocr-lab-upload-live-20261008.json)).

For chunk sizing, embedding, and model-specific token limits see
[chunking](chunking.md) and [embedding/tokenization](embeddings-tokenization.md). For the CLI map, see
[`tools/README.md`](../../tools/README.md).
