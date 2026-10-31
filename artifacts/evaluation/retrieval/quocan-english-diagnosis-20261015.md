# English-query benchmark diagnosis — 2026-10-15

Inspected QuocAn commit 3ea4f43 (English benchmark introduced in 4fdb5a1). No production retrieval changes were made.

## Key finding

`long_hau_2008_en_retrieval.json` is a dense-only result, not a verified English hybrid comparison. All 24 saved rankings reproduce exactly with legacy dense and current Huy dense. None reproduce with Huy default hybrid. QuocAn still has dense-only RetrievalService and cosine-only repository SQL; the English artifact carries cosine scores.

## Controlled comparison

All variants used the same English case file, query vectors, top-k 10 and one read-only repeatable-read database snapshot. All saved gold texts still matched the indexed snapshot. No LLM generation or database writes were performed.

| Question group | Dense Recall@10 | BM25 Recall@10 | Hybrid 1:2 Recall@10 | Dense MRR | Hybrid MRR |
|---|---:|---:|---:|---:|---:|
| All 24 | 0.3958 | 0.4583 | 0.4167 | 0.2606 | 0.2420 |
| English queries → English PVFCCo, Q01–Q12 | 0.5000 | 0.8750 | 0.7917 | 0.3519 | 0.4674 |
| English queries → Vietnamese Long Hậu, Q13–Q22 | 0.3000 | 0.0000 | 0.0000 | 0.1533 | 0.0000 |
| Both documents, Q23–Q24 | 0.2500 | 0.2500 | 0.2500 | 0.2500 | 0.1000 |

## Interpretation

- Translating all questions into English makes PVFCCo same-language but Long Hậu cross-language. It does not create an entirely same-language benchmark.
- On English PVFCCo queries, default hybrid improves recall by 29.17 percentage points over dense. BM25 alone is stronger still on this small subset (87.50% recall; MRR 0.6667), so fusion is not automatically better than its components.
- Overall, hybrid recall is 41.67% versus English dense 39.58%, but hybrid MRR is lower (0.2420 versus 0.2606). There is no single winner across metrics.
- The older Vietnamese dense baseline has 43.75% recall. Comparing that against the 39.58% English dense result changes the query language and does not test English dense versus English hybrid.
- Q01 remains a fusion miss: BM25 finds the gold mission/vision chunk at rank 5, dense misses it, and hybrid also misses it. This shows that combining ranks can suppress a useful single-method hit even when languages match.
- `long_hau_2008_en.json` contains only Q01–Q11 (11 cases), whereas `long_hau_2008_en_retrieval.json` contains all 24. Their headline aggregates are not comparable.
- The new RAGAS script reads `long_hau_2008.json`, the old Vietnamese baseline artifact. Its CSV is answer-evaluation evidence for that input, not an English hybrid retrieval evaluation.

## Next evaluation

Use explicit method/weight settings in the runner. Run dense, BM25 and hybrid against the identical query set and snapshot. For a same-language comparison, use English Q01–Q12 and Vietnamese Q13–Q22, with a separately specified bilingual strategy for Q23–Q24. Report subset and overall metrics. These are sparse exact-chunk labels on a small dataset; do not claim general superiority or generated-answer quality.

Per-query evidence: `quocan-english-diagnosis-20261015.json`. Reproduction: `replay-quocan-english-diagnosis.py`.
