# E5 top30 → BGE reranker → top10

Evidence v2; unchanged E5 vectors/candidate scope. No total context-token cap. Both baseline and reranker return10 chunks; evidence availability in all30 candidates is diagnostic only. Q14 remains excluded from full-intent denominator.

| Query → document | Dense top10 | Reranked top10 | Evidence available in top30 |
|---|---:|---:|---:|
| vi->vi | 17/19 | 17/19 | 19/19 |
| en->en | 14/19 | 14/19 | 18/19 |
| vi->en | 9/19 | 12/19 | 14/19 |
| en->vi | 12/19 | 12/19 | 14/19 |

## Required evidence components /61

| Direction | Dense top10 | Reranked top10 | Candidate top30 |
|---|---:|---:|---:|
| vi->vi | 57/61 | 58/61 | 61/61 |
| en->en | 52/61 | 55/61 | 60/61 |
| vi->en | 38/61 | 46/61 | 51/61 |
| en->vi | 43/61 | 49/61 | 51/61 |

## Gains and regressions

- vi->vi: gained Q20; lost Q15.
- en->en: gained Q15; lost Q01.
- vi->en: gained Q07, Q15, Q16, Q17; lost Q01.
- en->vi: gained Q17; lost Q01.

Local30-pair reranking: mean 402ms, median 379ms. Device NVIDIA GeForce RTX 2060; dtype float16; batch2. Load/warmup excluded.

Per-pair preflight: max507 tokens, model limit configured1024, zero truncated inputs. This per-pair limit is not a context-token budget.

Small post-hoc assistant-reviewed evidence v2, not an independent held-out test. Candidate pool coverage is availability, not a top10 oracle. No context-token budget; final chunk lengths may differ. Local rerank timing excludes model loading, dense retrieval, preflight and evidence scoring. No end-to-end answer latency or quality evaluated.

All saved scores, candidate retrieval and evidence views independently replayed by --verify-only. No production retrieval, embedding service, database/index or LLM changes.
