# CLI scripts

Runnable tools are grouped by workstream so the top level stays navigable.
Run commands from the repository root with `uv run python`:

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

## Two-report retrieval benchmark

Run An's unchanged 24 English cases against only the PVFCCo and Long Hau
reports, comparing dense, BM25 and hybrid on the same read-only snapshot:

```bash
.venv/bin/python scripts/retrieval/evaluate_two_document_benchmark.py --output artifacts/evaluation/retrieval/two-document-scoped-en.json
```

For Vietnamese, add `--cases data/evaluation/long_hau_2008_cases.json` and use
another output filename. Use `--methods dense hybrid` to compare only those
methods. The default hybrid weights are dense 1.0, BM25 2.0. Both document IDs
remain in scope for every question; no per-question gold-document filtering
is used. Scope still intersects ready-status and role checks. This benchmark
explicitly uses the admin role; it does not evaluate role isolation. Search
latency excludes query embedding and model loading. No generation is run.
The case files were copied unchanged from QuocAn commit `3ea4f43`.

### Document-language-aware experiment

```bash
.venv/bin/python scripts/retrieval/evaluate_bilingual_two_document_benchmark.py --language-aware --device cuda --output artifacts/evaluation/retrieval/scoped-automatic-language-aware.json
```

Uses verified report-language mappings and original EN/VI questions. The current
runner automatically translates each original question with `GroqProvider`
(`GROQ_API_KEY`, optional `GROQ_MODEL`), so a full run can make 48 translation
API calls. It does not use the paired reference question as its translation.
BM25 searches each language group with the matching generated query; dense
keeps the original query and searches both reports. Translation errors fall
back to dense for hybrid; BM25 records an empty ranking. No database schema
or data changes are made. Source language is supplied by the benchmark;
automatic language detection is not implemented. `--self-check` needs no API
key and makes no calls. Previous reviewed-translation artifacts stay unchanged.

Automatic translation output records generated queries, model, per-case latency,
cache hits, token usage and failures; the default filenames contain `automatic`.
Missing token usage is reported separately and is not a measured zero cost.
Mocked offline checks: `.venv/bin/python -m unittest discover -s tests -p test_query_translation.py -q`.
