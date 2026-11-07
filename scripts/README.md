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


## Frozen VietStyle dense baseline

```bash
.venv/bin/python scripts/retrieval/evaluate_vietstyle_dense.py --snapshot artifacts/evaluation/embedding-comparison-20261018 --output artifacts/evaluation/embedding-comparison-20261018/dense-baseline.json
```

Uses the snapshot's model/revision/input limit and exact five-document scope in a
read-only DB transaction. Refuses changed text, metadata or vectors. Reports
expected-source-file recall in the top ten chunks for all 20 questions; this is
not passage relevance or answer accuracy. Missing README.txt stays in the scoring
denominator. No translation, generation, or remote model download is performed.


## Local candidate embedding models

```bash
.venv/bin/python scripts/retrieval/evaluate_embedding_candidates.py --snapshot artifacts/evaluation/embedding-comparison-20261018 --model multilingual-e5-base --device cuda --batch-size 2
```

The same script accepts `bge-m3` and `qwen3-embedding-0.6b` (batch size 1 was
used for Qwen on 6 GB VRAM). Model weights/tokenizers download as needed;
embedding and cosine search run locally. No database or inference API access.
Frozen chunks/questions stay unchanged; model-specific formatting and every
input length are checked before embedding. Existing vectors/results are
preserved; use a fresh `--output-dir` for repeats. See the snapshot comparison.md
for results and before/after code explanation.

E5-large-v2 is also supported by the frozen candidate runner: use `--model e5-large-v2` with the same snapshot/device arguments. Its model card specifies English-only support; the VietStyle run keeps Vietnamese inputs for comparison.

### Four-direction multilingual dense benchmark

Frozen output: `artifacts/evaluation/four-direction-20261018/comparison.md`.
Uses the complete old PVFCCo English and Long Hau Vietnamese PDFs and 24 paired intents (48 queries). This measures labelled evidence-page coverage among top ten chunks, not the VietStyle source-file score. Both reports remain candidates for every query; target language does not filter retrieval.

```bash
.venv/bin/python scripts/retrieval/prepare_four_direction_benchmark.py
HF_HUB_OFFLINE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 .venv/bin/python scripts/retrieval/evaluate_embedding_candidates.py --snapshot artifacts/evaluation/four-direction-20261018 --model multilingual-e5-base --device cuda --batch-size 2
```

Local preparation requires Tesseract with eng/vie and retained historical contexts included in the snapshot for page-label validation. Cached original pages are reused. All three tokenizers are checked before encoding; shared chunks are 60 whitespace words with 12-word overlap, cap 512. Use the revisions recorded in candidate configs for exact repeats, and a fresh `--output-dir` because existing results are protected. BGE uses batch 2; Qwen uses batch 1. `preflight-100-word-attempt/` is an incomplete superseded attempt; use only the top-level final candidate results. No Supabase writes or inference API calls.

### Build corrected local English VietStyle simulation files

`.venv/bin/python scripts/retrieval/build_vietstyle_english.py` rebuilds the separately versioned English pack from the preserved originals and translation sources in `artifacts/evaluation/vietstyle-bilingual-20261019/`. It preserves workbook values/formulas and CSV policy data, regenerates a text-extractable SOP PDF, and packages five documents plus English benchmark questions/build notes. No database or model calls. See that folder's BUILD_NOTES.md; question/reference-answer files are evaluation inputs, not retrieval evidence.

### Validate bilingual VietStyle evidence labels

`.venv/bin/python scripts/retrieval/validate_vietstyle_evidence.py --self-check` verifies evaluation-only source spans and generates a human-readable review. See `artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v1/README.md` for 20 paired intents, required/optional components, Q14 policy-role issues, and the next retrieval-to-source mapping step. Uses the standard library; no models, database or scoring run. Never index label/question/reference-answer files as evidence.

Source mapping step 1 is now implemented in the shared token chunker. See `artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v1/source-mapping-step1.md` for fields, before/after behavior, checks and the remaining evidence-scoring step. Existing database rows/saved corpora were not rebuilt.

Evidence scoring step 2 is implemented in `src/core/evaluation/evidence_metrics.py`; see `artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v1/evidence-coverage-step2.md` for AND/OR, overlap, Q14, tests and oracle-only verification. Run `.venv/bin/python -m unittest discover -s tests -p test_evidence_metrics.py -v`. This is not yet wired into a model benchmark.

### VietStyle exact-evidence dense benchmark (four directions)

`artifacts/evaluation/vietstyle-bilingual-20261019/dense-evidence-benchmark-v1/` contains the shared 1,063 provenance-bearing chunks and 80 cases per candidate (20 paired intents). Read IMPLEMENTATION.md for before/after code changes and repeat commands; comparison.md has the model results.

- Prepare a fresh snapshot: `.venv/bin/python scripts/retrieval/prepare_vietstyle_evidence_benchmark.py --output-dir artifacts/evaluation/vietstyle-evidence-repeat`.
- Use existing `evaluate_embedding_candidates.py --snapshot <folder> --model <candidate> --device cuda --batch-size 2` (Qwen batch 1). Evidence-enabled snapshots automatically invoke the new scorer; older snapshots retain their metrics.
- Replay saved ranks and character coverage, without encoders: `.venv/bin/python scripts/retrieval/compare_vietstyle_evidence.py` (or `--snapshot <folder>`).
- Checks: `.venv/bin/python -m unittest discover -s tests -p 'test_evidence*.py' -v`.

Each direction searches all five target-language files, without gold-source filtering. The new component/full-intent metrics are not comparable directly to the old file/page metric. Q14 remains excluded from full-intent scoring. This is dense-only, without automatic translation, generation, database writes or production configuration changes.

### Evidence v2 label review and rescoring

Versioned labels: `artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v2/README.md`; before/after component changes are in annotation-changes.json. Validate with `validate_vietstyle_evidence.py --folder artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v2 --self-check`.

`rescore_vietstyle_evidence.py` replays all three candidates' saved vectors/rankings and evaluates revised labels without models/GPU. The default output `dense-evidence-benchmark-v1/rescored-evidence-v2/` already exists; supply a fresh `--output-dir` to repeat. Original v1 labels/results remain untouched. Label-only score changes are not encoder improvement; v2 was reviewed after seeing v1 errors and is not an independent held-out evaluation. Q14 still needs policy resolution.

### Neighbor context with fixed token budgets

`evaluate_neighbor_context.py` reuses the saved E5 vectors/evidence v2 to compare dense10, immediate same-document neighbors and dense30 under 2,048/4,096 context-token caps. No encoder/GPU/API/DB calls. Existing output is `artifacts/evaluation/vietstyle-bilingual-20261019/dense-evidence-benchmark-v1/neighbor-context-e5-v1/`; read comparison.md and IMPLEMENTATION.md. Use a fresh `--output-dir` to repeat. Context tokens use the pinned E5 tokenizer as a proxy, not the generation/chat tokenizer. Labels do not guide selection.

Checks: `.venv/bin/python -m unittest discover -s tests -p test_neighbor_context.py -v`. Neighbor order is frozen parser serialization, not guaranteed physical PDF row order. This experimental policy is not integrated into production.

### VietStyle E5 + BGE cross-encoder reranking (no context-token cap)

`evaluate_vietstyle_reranker.py` reconstructs E5 top30 from saved vectors, runs the pinned local multilingual `BAAI/bge-reranker-v2-m3` CrossEncoder and scores its top10 against unchanged evidence v2. Both final outputs contain10 chunks; no context-token budget, neighbor expansion, translations or generation. Candidate-pool evidence@30 is reported separately. Existing Vinamilk CrossEncoder benchmark code remains unchanged.

Completed output: `artifacts/evaluation/vietstyle-bilingual-20261019/dense-evidence-benchmark-v1/reranker-bge-v2-m3-v1/`; see comparison.md and IMPLEMENTATION.md. Reproduce saved-score verification with `.venv/bin/python scripts/retrieval/evaluate_vietstyle_reranker.py --verify-only`; a fresh GPU run requires a new `--output-dir`. Model runtime files must be cached; download command is in IMPLEMENTATION.md. Checks: `.venv/bin/python -m unittest discover -s tests -p test_vietstyle_reranker.py -v`.

No production reranker was enabled: VI→VI complete evidence remained17/19 (fixedQ20, regressedQ15); VI→EN rose9→12/19. This is a small exploratory ranking benchmark, not generated-answer accuracy.

### Evidence v3: Q15 duplicate form/prose evidence

Current targeted label correction: `artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v3/README.md`. Adds one VI prose alternative for Q15.transaction_id; English already covered. Keeps all history controls and older labels/results. `rescore_vietstyle_evidence.py` supports consecutive revisions using paired `--previous-evidence`/`--previous-results-dir` options and optional `--reranker-report`. Exact repeat command is in the v3 README. Completed comparison: `dense-evidence-benchmark-v1/rescored-evidence-v3/comparison.md`. No model/vector/ranking change; Q15 reranker recognizes3/4 components but remains incomplete.
