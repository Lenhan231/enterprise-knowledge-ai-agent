# Retrieval and RBAC

## Request path

The authenticated server supplies the caller's role. `RetrievalService`
dispatches to dense, BM25, hybrid, or parent-context retrieval. Document status,
company, metadata, and `documents.allowed_roles` are checked in PostgreSQL
before candidate ranking/limits; the browser cannot choose its trusted roles.
The default hybrid mode combines vector and lexical rankings with reciprocal
rank fusion. If query embedding fails, hybrid falls back to ACL-filtered BM25
and reports the method actually used. Explicit dense and parent requests surface
embedding errors rather than silently changing methods.
Knowledge questions that name one page (`page 11` / `trang 11`) add that page to
the same pre-ranking metadata filter, so retrieval cannot silently cite a
neighboring page. It composes with Commerce-domain and RBAC filters.

Parent retrieval expands ranked child chunks to bounded same-page neighbors.
It is a context-window approximation: persisted `parent_id` and `section_path`
are not populated, and the expansion reapplies role and document filters.

## Citation provenance

Document citations carry `document_id`, source page, chunk index, and a
`retrieval_chunk_id` of `document_id::chunk::index`. That composite ID is a
trace aid for the current index, not a persistent database key across re-chunking.
`source_chunk_id` remains the numeric `document_chunks.id` link used by verified
metric evidence. `source_content_hash` prefers a chunk-level hash and falls back
to the ingested source file's `source_sha256` when only file provenance exists.

Application feature permissions and document access are separate controls.
`ROLE_PERMISSIONS` in `src/app/main.py` gates routes and UI features; document
`allowed_roles` filters passages at retrieval time. Missing trusted roles fail
closed in the knowledge path.

## Answer cache

Grounded-answer cache lookup happens only after role-filtered retrieval. Its
key includes the evidence/prompt, company, roles, and generation configuration;
entries expire after 60 seconds and are capped per process. It stores validated
answers and source IDs, not retrieved document text. Analytics SQL is executed
per request and does not use this answer cache.

## Methods and evaluation

Ranking code is split under `src/core/retrieval/methods/`: `dense.py`,
`bm25.py`, `hybrid.py`, and `parent.py`. `RetrievalService` dispatches and maps
results to the shared response contract. Run the same labeled cases across
methods with:

```bash
PYTHONPATH=src .venv/bin/python tools/retrieval/evaluate_retrieval.py --help
```

Commerce case labels and the current method-comparison artifact are linked from
[`commerce-decision-support.md`](../commerce-decision-support.md). The labels
are small and document-level; do not use them as proof that a method is best.
Preserve the security invariant that authorization is applied before ranking
and candidate limits.
