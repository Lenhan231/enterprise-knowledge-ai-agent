# Commerce knowledge sources

## Synthetic Commerce Demo policies

These three image-only PDFs are fictional internal-policy examples for the mock
Commerce Demo dataset. They are intended to test OCR, RAG citations, and
conditional decision support. They are **not** policies issued by a real
retailer and must not be presented as verified business rules.

| Domain | PDF | Manifest ID | Scope |
| --- | --- | --- | --- |
| Inventory allocation | [`inventory-allocation.pdf`](synthetic_policies/inventory-allocation.pdf) | `CD-POL-INV-001` | Signals for reviewing inventory; evidence required before transfers or order changes. |
| Promotion planning | [`promotion-planning.pdf`](synthetic_policies/promotion-planning.pdf) | `CD-POL-PROMO-001` | Separates observed campaign outcomes from incrementality and profitability. |
| Nationwide logistics | [`nationwide-logistics.pdf`](synthetic_policies/nationwide-logistics.pdf) | `CD-POL-LOG-001` | Regional monitoring; evidence required before network redesign. |

All three are listed as active/indexed in [`manifest.json`](manifest.json).
In the app, sign in as Admin, open **Knowledge management / File management**,
and search for `CD-POL` or `Synthetic demo policy` to find them. Use **Open
original PDF** on each policy row to view the scanned source. The records are
labeled **Synthetic demo policy · fictional Commerce Demo only**. These scans
have OCR errors and demonstrate the parser/upload path; they are not reliable
evidence of business rules beyond their visible, fictional text.

At the current manifest snapshot, 16 sources are active: 9 PDFs and 7 HTML
references. Six active public PDFs are born-digital; some include raster pages
or embedded UI screenshots, but none is a physical scan. The three synthetic
policies are full-document image-only PDFs (three pages each), so they exercise
OCR through the upload path without proving accuracy on real scans. Three
official Tiki Seller Academy pages add Vietnamese, platform-scoped operations
guidance for inventory aging/reports, Category Deal controls, and FBT stock
transfer. They are HTML pages, not scanned documents; their Tiki-specific rules
must not be applied to the fictional Commerce Demo. The Sam's Club screenshot-
table fixture is a separate, incomplete real-source OCR check and must not be
described as a successful full-table scan.

The inventory and promotion entries also have English `notes_en` catalog
summaries for the deterministic provider fallback. Ingestion stores them as
metadata; the answer labels them as summaries rather than verified OCR text
and still cites the original PDF page. They do not replace the indexed PDF
content.

Regenerate the PDFs and re-index them with:

```bash
PYTHONPATH=src .venv/bin/python tools/ingestion/generate_commerce_demo_policies.py
PYTHONPATH=src .venv/bin/python tools/ingestion/ingest_commerce_knowledge.py --ids CD-POL-INV-001 CD-POL-PROMO-001 CD-POL-LOG-001
```

The PDF generator refreshes each policy's `content_sha256` in the manifest; always re-index after regeneration so the database and source checksum stay aligned.

The current upload-processor smoke run is
[`commerce-scan-document-processor-current-20261004.json`](../../artifacts/evaluation/ocr/pipeline/commerce-scan-document-processor-current-20261004.json).
It uses visually transcribed references and records 0 micro-CER/WER, 3/3 exact
table rows and 9/9 exact numeric cells on the two-page synthetic fixture. It is
not a representative OCR benchmark. Older nine-page policy CER artifacts refer
to prior PDF bytes and are historical; the current active PDFs are now scored in
the separate [current policy scan evaluation](../../artifacts/evaluation/ocr/pipeline/commerce-active-policy-scan-ocr-20261008.json); the 6 October report is retained as historical evidence.

To regenerate authored-text references for the **current** policy PDFs without
rewriting those PDFs, run:

```bash
uv run python tools/ingestion/generate_commerce_demo_policies.py --ground-truth-only
uv run python tools/processing/evaluate_scan_document_processing.py \
  --dataset data/evaluation/ocr/commerce_policy_scan_ground_truth.json \
  --output /tmp/commerce-active-policy-scan-ocr.json
```

The reference generator checks each PDF checksum against the active manifest and
extracts visible authored text without the page CSS or the page-counter footer,
which the upload parser intentionally removes. The refreshed 8 October nine-page
run uses Tesseract 5.5.3 and reports micro-CER 0.003297 / WER 0.014558 across
9/9 OCR pages, with a mean parser latency of 5.527 seconds per page ([artifact](../../artifacts/evaluation/ocr/pipeline/commerce-active-policy-scan-ocr-20261008.json)). All three active PDFs have zero native text and one full-page raster image per page; the saved parser records contain Tesseract chunks across pages 1–3. The policy
generator's body text was increased to 12 pt; the OCR engine and render settings
were unchanged. The result is still a digitally rendered, non-human-reviewed
fixture; these figures do not establish accuracy on physical scans. The policy
documents were re-indexed through the normal Commerce ingestion command, and
persisted chunks carry OCR-derived section titles. A regression test also checks
per-page OCR counts for Vietnamese decision qualifiers (`không`, `chỉ`, `nếu`,
`phải`, `cần`) and the restrictive phrases `không được` and `không tự động`, so
a low aggregate CER cannot conceal a dropped action limit.

## Active source table indexing

The active IAB incrementality guideline is parsed for native text tables during Commerce ingestion. Its three tables (13 rows) are stored in `extracted_tables` / `extracted_records`; row-aware chunks repeat the table headers for document retrieval. Re-index one approved source with `PYTHONPATH=src .venv/bin/python tools/ingestion/ingest_commerce_knowledge.py --ids IAB-COMMERCE-INCREMENTALITY-GUIDELINES-2025`. Other active PDFs are not automatically claimed to have structured tables unless the parser actually detects them.
