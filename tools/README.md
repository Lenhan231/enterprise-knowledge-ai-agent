# CLI tools

Runnable command-line tools are separate from application code in `src/`. Benchmark commands are grouped with the workstream they evaluate, alongside ingestion and operational commands.
Run commands from the repository root with `uv run python`:

| Folder | Purpose |
| --- | --- |
| `ingestion/` | Import synthetic Commerce data and download/index manifest-listed operating references; `source_downloaders/` holds format adapters. |
| `processing/` | OCR, PDF/table extraction, and upload-pipeline evaluation. |
| `chunking/` | Chunking evaluation. |
| `retrieval/` | Retrieval, embedding, reranking, and vector maintenance checks. |
| `agents/` | Commerce decision support and agent evaluation. |
| `operations/` | API load and runtime checks. |

The active application uses the Commerce SQL schema for dashboard facts and
the manifest-backed corpus for retrieved operating guidance. Commerce
transaction data is synthetic; public documents are attributed operating
references, not evidence about the synthetic business. Benchmark inputs live
under `data/evaluation/`; current run evidence lives under
`artifacts/evaluation/`.

To load Kaggle's Datathon 2026 Round 1 source files, first download the
competition files with `kagglehub.competition_download('datathon-2026-round-1')`,
then run `uv run python tools/ingestion/import_kaggle_datathon.py <download-path>`.
The migration creates the private `commerce` schema, separate from the
knowledge-base tables in `public`. Import is one-time and refuses a non-empty
schema; it copies the 13 source CSVs directly and skips `sample_submission.csv`.

The Commerce operating-method references and platform procedures are registered in
[`data/commerce_knowledge/manifest.json`](../data/commerce_knowledge/manifest.json).
Download and index them through the same parser/chunk/embed repositories with:

```bash
PYTHONPATH=src .venv/bin/python tools/ingestion/ingest_commerce_knowledge.py --download-only
PYTHONPATH=src .venv/bin/python tools/ingestion/ingest_commerce_knowledge.py
```

The three explicitly synthetic Commerce Demo policy PDFs are reproducible and
can be indexed without downloading/reprocessing the public corpus:

```bash
PYTHONPATH=src .venv/bin/python tools/ingestion/generate_commerce_demo_policies.py
PYTHONPATH=src .venv/bin/python tools/ingestion/ingest_commerce_knowledge.py --ids CD-POL-INV-001 CD-POL-PROMO-001 CD-POL-LOG-001
```

These fictional scenario rules are for testing policy-grounded decision support
only. Every PDF and indexed document is labeled synthetic; do not attribute the
rules to a real retailer.

The downloader only accepts HTTPS URLs from its explicit host allowlist in
`ingest_commerce_knowledge.py` (TikTok Shop, Shopee, Walmart, Shopify, Amazon,
and DoorDash hosts); downloaded HTML/PDF and parsed text stay local and are
git-ignored. Synthetic policy PDFs are read directly from their canonical
`data/commerce_knowledge/synthetic_policies/` paths without a duplicate cache.
Chunks retain publisher, update date, original URL, evidence class, decision
domain, applicability, and content SHA-256. Seller/platform requirements apply
only to that issuer's marketplace; they are not policies of the synthetic
Commerce dataset. The command writes indexed references to
`public.documents`, `processed_document_chunks`, and `document_chunks`.

The SQL case set and document-level source labels live in
[`data/evaluation/commerce_decision_benchmark.json`](../data/evaluation/commerce_decision_benchmark.json)
and [`data/evaluation/commerce_retrieval_cases.json`](../data/evaluation/commerce_retrieval_cases.json).
To replay the nine source-grounded decision cases against the authenticated local API, configure an Admin demo account and provider key in `.env`, then run:

```bash
PYTHONPATH=src uv run python tools/agents/evaluate_commerce_decision_support.py
```

Use `--case-id INV-01` for a single case. The report checks API/citation/source structure; inspect each response against benchmark gold observations and expected behavior before treating it as a semantic score.

To export only manifest-listed public chunks for embedding experiments, run
`uv run python tools/retrieval/export_public_embedding_corpus.py`; then pass
the resulting JSONL with `--corpus` to `tools/retrieval/evaluate_embeddings.py`.
The scan upload path can be smoke-tested with
`uv run python tools/processing/evaluate_scan_document_processing.py`.

To create a private Kaggle bundle for any one labeled OCR dataset, pass its
JSON path and a new dataset slug. The bundle includes only that dataset, its
source PDF(s), and the evaluator; source hashes are checked from page-level
provenance before copying:

```bash
uv run python tools/processing/package_ocr_benchmark.py /tmp/shopee-ocr-kaggle \
  --dataset data/evaluation/ocr/commerce_shopee_inventory_page_transcriptions.json \
  --dataset-id your-kaggle-user/commerce-shopee-ocr-exploratory
```

For example, `uv run python tools/processing/evaluate_ocr.py --help` shows
the OCR benchmark options. Read a command's help before running a script that
downloads, ingests, re-embeds, or writes evaluation results.
