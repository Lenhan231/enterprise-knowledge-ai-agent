# CLI scripts

Runnable tools are grouped by workstream so the top level stays navigable.
Run commands from the repository root with `uv run python`:

LLM instruction templates live in [`src/core/prompts`](../src/core/prompts/README.md).
Scripts and runtime modules import those templates instead of embedding their text.

| Folder | Purpose |
| --- | --- |
| `ingestion/` | Download and ingest the public seed corpus; `source_downloaders/` holds source adapters. |
| `processing/` | OCR, PDF/table extraction, processing evaluation, and financial-report extraction. |
| `chunking/` | Chunking diagnostics and chunking-versus-retrieval evaluation. |
| `retrieval/` | Retrieval, embedding, reranking, and vector maintenance checks. |
| `agents/` | Agent routing, grounded QA, proposal-case, and answer-quality evaluation. |
| `analytics/` | Corpus metadata and verified-metric audits. |
| `operations/` | API load and runtime checks. |

For example, `uv run python scripts/processing/evaluate_ocr.py --help` shows
the OCR benchmark options. Read a command's help before running a script that
downloads, ingests, re-embeds, or writes evaluation results.
