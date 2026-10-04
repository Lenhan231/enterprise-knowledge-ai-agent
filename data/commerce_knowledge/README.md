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

Regenerate the PDFs and re-index them with:

```bash
PYTHONPATH=src .venv/bin/python scripts/ingestion/generate_commerce_demo_policies.py
PYTHONPATH=src .venv/bin/python scripts/ingestion/ingest_commerce_knowledge.py --ids CD-POL-INV-001 CD-POL-PROMO-001 CD-POL-LOG-001
```

The PDF generator refreshes each policy's `content_sha256` in the manifest; always re-index after regeneration so the database and source checksum stay aligned.

The current upload-processor smoke run is
[`commerce-scan-document-processor-current-20261004.json`](../../artifacts/evaluation/ocr/pipeline/commerce-scan-document-processor-current-20261004.json).
It uses visually transcribed references and records 0 micro-CER/WER, 3/3 exact
table rows and 9/9 exact numeric cells on the two-page synthetic fixture. It is
not a representative OCR benchmark. Older nine-page policy CER artifacts refer
to prior PDF bytes and are historical; the current active PDFs are now scored in
the separate [`policy scan evaluation`](../../artifacts/evaluation/ocr/pipeline/commerce-active-policy-scan-ocr-20261005.json).

To regenerate authored-text references for the **current** policy PDFs without
rewriting those PDFs, run:

```bash
uv run python scripts/ingestion/generate_commerce_demo_policies.py --ground-truth-only
uv run python scripts/processing/evaluate_scan_document_processing.py \
  --dataset data/evaluation/ocr/commerce_policy_scan_ground_truth.json \
  --output artifacts/evaluation/ocr/pipeline/commerce-active-policy-scan-ocr-20261005.json
```

The reference generator checks each PDF checksum against the active manifest and
extracts visible authored text without the page CSS. The current nine-page run
uses Tesseract 5.5.3 and reports micro-CER 0.005229 / WER 0.019515. It is still a
digitally rendered, non-human-reviewed fixture; these figures do not establish
accuracy on physical scans. The policy documents were then re-indexed through
the normal Commerce ingestion command, and persisted chunks now carry OCR-derived
section titles.
