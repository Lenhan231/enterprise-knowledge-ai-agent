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
The `employee` role cannot query restricted financial reports. The seeded
financial documents allow `finance_analyst`, `executive`, and `admin`;
sustainability reports use their own role set. These demo assignments are
synthetic and do not describe Vinamilk's real permissions.

Application permissions are declared once in `src/app/main.py` as
`ROLE_PERMISSIONS`; FastAPI route guards derive their allowed roles from that
map, and the admin access matrix is rendered from the same data. This is
separate from document-level `allowed_roles`: application permissions gate
features such as analytics, metric review, upload, and role assignment, while
document roles filter passages before retrieval.

## Current evaluation boundary

`scripts/evaluate_retrieval.py` evaluates labeled cases at both document and
passage level when chunk judgments are present. It supports dense, BM25, hybrid
and parent-context modes. Before a run, passage IDs are checked against the
current ready corpus and the case's allowed roles; labels based on
`document_id::chunk::chunk_index` must be reviewed after re-ingestion or
re-chunking. Parent results are expanded to their returned child indices for
passage scoring.

The current file has nine questions and 21 manually assigned selected passage
labels; the labels are not exhaustive, so this remains a smoke set. The
2026-09-27 rerun uses the current case hash and the expanded snapshot of 5,052
chunks/44 documents overall, 4,750 chunks/25 ready Vinamilk documents,
PostgreSQL 17.6. It is preserved separately from the earlier pre-governance
baseline:

| Method | Document P@1 | Document MRR | Passage/context MRR | Passage Recall@5 or context gold coverage@5 | Mean latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dense | 1.000 | 1.000 | Passage 0.373 | Passage Recall@5 0.259 | 2,082 ms |
| BM25 | 0.889 | 0.944 | Passage 0.307 | Passage Recall@5 0.352 | 1,393 ms |
| Hybrid | 0.889 | 0.926 | Passage 0.384 | Passage Recall@5 0.370 | 1,422 ms |
| Parent context | 1.000 | 1.000 | Context 0.431 | Gold-passage coverage@5 0.278 | 2,236 ms |

Parent scores are context-window metrics and are not directly interchangeable
with passage ranking metrics. The high document scores and low passage scores
show why document-only evaluation is insufficient. The case hash, per-query
ranks and settings are in
`artifacts/evaluation/vinamilk-retrieval-expanded-corpus-20260927.json`;
the earlier pre-ingestion run remains
`artifacts/evaluation/vinamilk-retrieval-current-passage-comparison.json`;
the case file is `data/evaluation/vinamilk_retrieval_cases.json`. Labels must be
independently reviewed and expanded before selecting a retrieval method. Hybrid
has the highest ordinary passage MRR in this snapshot, while BM25 is faster;
the difference is too small and the judgment set too limited to select a
winner. See
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
retrieval path. Add passage-level judgments, broader role-denial cases and
repeated runs where appropriate. Preserve the security invariant that
authorization filters run before candidate limits and ranking.
