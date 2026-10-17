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
this runner does not detect query language (the integrated method below does).
`--self-check` needs no API
key and makes no calls. Previous reviewed-translation artifacts stay unchanged.

Automatic translation output records generated queries, model, per-case latency,
cache hits, token usage and failures; the default filenames contain `automatic`.
Missing token usage is reported separately and is not a measured zero cost.
Mocked offline checks: `.venv/bin/python -m unittest discover -s tests -p test_query_translation.py -q`.


## Integrated automatic translation

`translated_hybrid` is now available in `RetrievalService`, `RAGService`, and
`AskRequest.retrieval_method`. In the app choose **Hybrid + EN/VI Translation**.
The existing `hybrid` default remains the untranslated baseline.

For An's `run_vietstyle_benchmark.py`, replace the retrieval call with:

```python
contexts = rag.retrieve_contexts(
    q, limit=10, company="Commerce Demo", roles=["admin"],
    retrieval_method="translated_hybrid",
    document_ids=IDS,
)
```

Pass `document_ids=IDS` for dense and regular hybrid too, so the comparison
uses the same corpus. Company and role checks still apply to every candidate
search. A document whitelist does not grant access to its documents.

The default detects EN/VI query language and translates to the other language
in one structured LLM call, then runs original-query dense retrieval and both
BM25 queries. It uses existing `GROQ_API_KEY` / `GROQ_MODEL` configuration;
callers may inject `QueryTranslator(other_llm)` into `RetrievalService`.
Only the question goes to the translation model, not retrieved document text.
Known-language benchmarks may pass `query_language="vn"` or `"en"` to avoid
language detection and use the existing translation prompt.

Without verified document languages, both BM25 queries search the entire
permitted document scope (the bilingual variant). This is **not** identical
to the earlier language-aware experiment and does not inherit its scores.
To match that experiment's routing, additionally pass a complete verified map:

```python
document_ids = [
    "UPLOAD-11e62199551047c0a1ddcd5e6684a1c1",  # PVFCCo annual report
    "UPLOAD-5149fb823530440da1a2f09704c695d6",  # Long Hau financial statements
]
contexts = rag.retrieve_contexts(
    q, limit=10, roles=["admin"], retrieval_method="translated_hybrid",
    document_ids=document_ids,
    document_languages={document_ids[0]: "en", document_ids[1]: "vn"},
    query_language="vn",  # Use "en" for the English question set.
)
```

Language-aware mode rejects a missing/invalid language for a scoped document;
it never infers document language from the query or gold answer. No database
language column or hardcoded application document mapping is added.

The candidate budget is `top_k * 10` per search (100 when top_k=10).
EN/VI BM25 lists are fused equally, then their first candidate-budget results
are fused with original-query dense results using weights 2:1, RRF k=60 and
stable chunk-ID ties, matching the experimental fusion helper. This differs
from the ordinary SQL hybrid policy. Queries are cached per translator instance
(up to 256); search results are never cached across permission filters.

The shared response's `retrieval_details` and each RAG context's
`retrieval_details` record generated `lexical_queries`, translation model,
translation latency, scope, weights, and `dense_fallback` / `effective_method`.
Translation API/configuration/validation failures return scoped dense results
and record the failure type instead of pretending translation succeeded.
`RetrievalResponse.latency_ms` includes translation, embedding and search.
The service closes only translation providers it creates itself.

Validation (mocked translation/embedding/DB, no paid calls):

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_translated_hybrid.py'
```

The original two-report runner remains an experimental report generator; it
now shares the fusion helper with the integrated method. Existing saved
benchmark JSON files are unchanged. Rerun all strategies with the same scope,
questions and corpus before reporting new comparative scores.
