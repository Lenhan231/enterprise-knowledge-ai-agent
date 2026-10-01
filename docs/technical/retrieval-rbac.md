# Retrieval and RBAC

## Request path

`RetrievalService` embeds the question, then
`DocumentChunkRepository.similarity_search` joins chunks to authoritative
document metadata. Company and allowed-role filters apply in SQL before
dense or lexical candidate ranking. Dense pgvector cosine candidates and
PostgreSQL `tsvector`/`tsquery` candidates are fused with reciprocal-rank
fusion; a single explicit fiscal year is promoted within both candidate sets.
The default `RetrievalRequest.top_k` is 5, bounded to 1–100.

Access roles come from the authenticated server-side request and the
`documents.allowed_roles` source of truth. Client-supplied roles are not trusted.
`KnowledgeAgent` rejects a missing/blank trusted role before calling RAG, and
`RAGService` independently requires a non-empty role list before retrieval. An
omitted role therefore cannot fall through to an unfiltered repository query.
The `employee` role cannot query restricted financial reports. The seeded
financial documents allow `finance_analyst`, `executive`, and `admin`;
sustainability reports use their own role set. These demo assignments are
synthetic and do not describe Vinamilk's real permissions.

## Grounded answer response cache

`RAGService` caches only successfully generated, citation-validated grounded
answers. Every request performs role-filtered retrieval first; the cache key
includes the hash of the exact prompt/evidence, company, authenticated roles,
and generation model/reasoning configuration. A changed question or retrieved passage misses the cache, and entries
expire after 60 seconds with a 128-answer process-local cap. The cache stores
the answer and validated source IDs, not retrieved document content. Retrieval
and dynamic SQL analytics still run on each request; insufficient answers and
uncited/invalid model outputs are not cached. Unit tests cover reuse across
request-scoped service instances, role/company/model separation, evidence
changes, and expiry. Provider-backed latency savings have not yet been measured.

Application permissions are declared once in `src/app/main.py` as
`ROLE_PERMISSIONS`; FastAPI route guards derive their allowed roles from that
map, and the admin access matrix is rendered from the same data. This is
separate from document-level `allowed_roles`: application permissions gate
features such as analytics, metric review, upload, and role assignment, while
document roles filter passages before retrieval.

## Current evaluation boundary

A live read-only BM25 probe asked the same FY2024 finance question as
`employee` and `finance_analyst`. The employee received no candidate documents;
the analyst received 20 chunks from `VNM-AR-2024-VI`. A follow-up ACL read
confirmed every returned document included the requesting role. This is one
finance-specific query over the public demo corpus with synthetic role labels;
it does not establish isolation for private documents or the full query set.
See the [live isolation artifact](../../artifacts/evaluation/vinamilk-live-retrieval-rbac-isolation-20260928.json).

`scripts/retrieval/evaluate_retrieval.py` evaluates labeled cases at both document and
passage level when chunk judgments are present. It supports dense, BM25, hybrid
and parent-context modes. Before a run, passage IDs are checked against the
current ready corpus and the case's allowed roles; labels based on
`document_id::chunk::chunk_index` must be reviewed after re-ingestion or
re-chunking. Parent results are expanded to their returned child indices for
passage scoring.

### Retrieval code map

Each ranking method has its own SQL implementation under
`src/core/retrieval/methods/`: `dense.py` handles vector-distance ranking,
`bm25.py` handles lexical ranking, `hybrid.py` combines both with reciprocal
rank fusion, and `parent.py` expands dense child hits into ACL-filtered page or
section windows. `common.py` holds only shared eligible-document/ACL SQL,
BM25 scoring CTEs, and database-row mapping. `RetrievalService` dispatches the
selected mode, owns query-embedding lifecycle and maps results to the public
contract; `DocumentChunkRepository.similarity_search()` remains the compatible
database entry point and delegates SQL to those method modules. This makes a
single method's ranking easier to inspect without changing RAG/API callers.

Parent-context remains a bounded sibling-window approximation: stored
`parent_id`/`section_path` are not populated, and its expansion query stays in
`DocumentChunkRepository` because it owns the ACL-filtered database read.

The current file has twelve questions and 24 manually assigned selected
passage labels. The labels are pooled and non-exhaustive, so this remains a
smoke set. The 2026-09-28 live rerun uses the current case hash on PostgreSQL
17.6: 5,052 chunks/44 documents overall and 4,750 chunks/25 ready Vinamilk
documents. It includes all four proposal methods and is not a model-selection
result:

| Method | Document P@1 | Document MRR | Passage/context MRR | Passage Recall@5 or context gold coverage@5 | Mean latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dense | 1.000 | 1.000 | Passage 0.412 | Passage Recall@5 0.444 | 1,562 ms |
| BM25 | 0.917 | 0.958 | Passage 0.403 | Passage Recall@5 0.431 | 1,135 ms |
| Hybrid (dense:BM25 1:2, RRF k=60) | 0.917 | 0.944 | Passage 0.464 | Passage Recall@5 0.444 | 1,177 ms |
| Parent context | 1.000 | 1.000 | Context 0.469 | Gold-passage coverage@5 0.458 | 2,312 ms |

Parent scores are context-window metrics and are not directly interchangeable
with passage ranking metrics. Mean dense latency includes a 13-second first
query embedding-model load; subsequent dense queries were below one second.
The high document scores and lower passage scores show why document-only
evaluation is insufficient. The case-file SHA-256 is
`554f9837ed9ad6e3941e0edf38a88ac4d8614e2d138bb4d0c188374f21270b1a`. Per-query
ranks, settings and the exact live snapshot are in
`artifacts/evaluation/vinamilk-retrieval-live-12cases-20260928.json`; the prior
2026-09-27 run remains
`artifacts/evaluation/vinamilk-retrieval-12cases-expanded-corpus-20260927.json`;
the earlier pre-ingestion run remains
`artifacts/evaluation/vinamilk-retrieval-current-passage-comparison.json`;
the case file is `data/evaluation/archive/retrieval/vinamilk_retrieval_cases.json`. Labels must be
independently reviewed and expanded before selecting a retrieval method. Hybrid
has the highest passage MRR in this snapshot, while dense leads document MRR;
the selected judgments are too limited to select a winner. See
[the evaluation matrix](agents-and-evaluation.md#proposal-evaluation-master-matrix).

Fiscal-year preference reads authoritative `documents.fiscal_year`; missing
years are treated as non-matches so PostgreSQL does not sort SQL `NULL` ahead
of a matching report. This correction is included in the refreshed artifact.

Parent-context retrieval now expands dense-ranked child chunks with up to two
same-section, same-page neighbors (or same-page neighbors when headings are
absent), keeping cited page provenance accurate; it reapplies company,
ready-status and role filters during expansion. It is a
bounded runtime approximation because stored `parent_id`/`section_path` values
are absent and long sections do not fit as a whole. Reranker models have
offline comparison runs, but reranking is not enabled in the production
retrieval path. A second run against the same case hash and corpus snapshot
produced identical per-case rankings and all document, passage and context
metrics for all four methods. Mean latency varied between runs, so only the
ranking/metric reproduction is established. The repeat is
`artifacts/evaluation/vinamilk-retrieval-live-12cases-repeat2-20260928.json`.
After the section-title metadata backfills, a third live run again matched the
same per-case rankings and metrics; it is
`artifacts/evaluation/vinamilk-retrieval-post-section-title-backfill-12cases-20260928.json`.
Add independently reviewed passage labels and broader role-denial cases
before selecting a method. Preserve the security invariant that authorization
filters run before candidate limits and ranking.
