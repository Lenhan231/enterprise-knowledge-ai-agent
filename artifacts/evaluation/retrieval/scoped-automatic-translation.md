# Automatic translation retrieval benchmark — 2026-10-16

## Result

Automatic translation with document-language-aware BM25 substantially improves retrieval over the original dense and single-query hybrid baselines on this two-report test. BM25 alone remains stronger than the tested dense+lexical fusion. The run completed 48 original-language cases representing 24 paired intents, with zero reported translation failures or dense fallbacks. Semantic translation accuracy has not been independently scored.

## Verified protocol

- Source artifact: [scoped-automatic-translation.json](scoped-automatic-translation.json). Run timestamp: 2026-10-16T09:57:56.807994+00:00.
- Same frozen 249 indexed chunks, two documents and 24 questions per original language as prior scoped runs. Corpus and both case hashes match the reviewed-translation reference.
- PVFCCo report is manually mapped to English; Long Hau financial statements are manually mapped to Vietnamese. Each case searches both language groups; the expected source is not used to choose a scope.
- The original question is retained for multilingual dense retrieval. Only that question and its supplied source-language label are passed to the translator; the paired reviewed question is not passed.
- Generated English text searches English documents; generated Vietnamese text searches Vietnamese documents. Lexical ranks are fused equally (RRF k=60), then optionally fused with dense ranks (dense 1, lexical 2). Candidate cap 100, final top-k 10.
- Embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, device `cuda`. Translation model: `openai/gpt-oss-20b` via the configured Groq provider.
- Retrieval uses an admin benchmark role and a read-only database transaction. No document data/schema or stored vectors were modified. There are translation API calls but no answer-generation calls.

## Comparison with original scoped methods

| Query language | Method | Recall@10 | Precision@10 | MRR | nDCG@10 |
|---|---|---:|---:|---:|---:|
| en | Dense | 39.58% | 4.17% | 0.2606 | 0.2865 |
| en | Original BM25 | 45.83% | 5.00% | 0.3935 | 0.3989 |
| en | Original hybrid | 45.83% | 5.00% | 0.2583 | 0.3036 |
| en | Automatic language-aware BM25 | 77.08% | 8.33% | 0.4729 | 0.5391 |
| en | Automatic language-aware hybrid | 72.92% | 7.92% | 0.4090 | 0.4819 |
| vn | Dense | 43.75% | 4.58% | 0.2174 | 0.2675 |
| vn | Original BM25 | 35.42% | 3.75% | 0.2465 | 0.2726 |
| vn | Original hybrid | 31.25% | 3.33% | 0.2182 | 0.2348 |
| vn | Automatic language-aware BM25 | 83.33% | 8.75% | 0.5326 | 0.5938 |
| vn | Automatic language-aware hybrid | 66.67% | 7.08% | 0.5245 | 0.5439 |

## Automatic versus reviewed translations

Both runs use the same language routing, candidate settings and gold labels. Changes reflect generated query wording, while ranking remains deterministic. Reviewed translations are a reference condition, not a guaranteed upper bound.

| Original language | Method | Reviewed Recall@10 | Automatic Recall@10 | Reviewed MRR | Automatic MRR |
|---|---|---:|---:|---:|---:|
| en | bm25 | 81.25% | 77.08% | 0.4938 | 0.4729 |
| en | hybrid | 72.92% | 72.92% | 0.4418 | 0.4090 |
| vn | bm25 | 81.25% | 83.33% | 0.4938 | 0.5326 |
| vn | hybrid | 64.58% | 66.67% | 0.4352 | 0.5245 |

## Recall by document group

| Original language | Method | PVFCCo (12 questions) | Long Hau (10 questions) | Both reports (2 questions) |
|---|---|---:|---:|---:|
| en | bm25 | 79.17% | 80.00% | 50.00% |
| en | hybrid | 87.50% | 60.00% | 50.00% |
| vn | bm25 | 87.50% | 90.00% | 25.00% |
| vn | hybrid | 87.50% | 50.00% | 25.00% |

## Translation overhead

- 48 original-query translation attempts; 0 reported failures; 0 cache hits; usage available for all 48 cases.
- Mean translation latency: 751.31 ms; median: 389.45 ms; nearest-rank p95: 2649.96 ms; maximum: 2678.51 ms.
- Tokens: 6,663 input + 3,143 output = 9,806 total. Usage is counted once per original query, not twice for BM25/hybrid output rows.
- These are translation-step measurements, not complete application response latency. No monetary cost is inferred from token counts.

## Translation observations and remaining misses

Zero API/schema failures does not mean every translation is correct. A spot check of Q01 shows the Vietnamese output prepends `Câu hỏi:` and changes “mission” to “Mục tiêu”; it also changes the expanded PVFCCo company name. The Vietnamese-to-English output similarly changes the expanded company name while keeping the acronym. Preserve entity names more strictly and inspect financial terminology, numbers, units and dates before production. These are observed examples, not a measured overall translation-error rate.

BM25 cases whose recall changed versus reviewed translations:

- en Q18: 1.00 → 0.00.
- vn Q08: 0.00 → 1.00.
- vn Q24: 0.50 → 0.00.

## Validation and limits

- Verified all 96 result rows: 24 cases per language per method, original-query preservation, unchanged gold labels, unique top-10 chunk IDs, scope membership, recomputed per-case metrics and recomputed aggregates.
- Runner/translator SHA-256 hashes match current source. Token totals and mean translation latency were independently recomputed from the 48 distinct query cases.
- This is a small, scoped exact-chunk benchmark with sparse labels. It does not establish generated-answer correctness, mixed-corpus robustness, automatic source-language detection, automatic document-language detection, repeated-run stability, production latency, or general superiority.
- The original query language is supplied by the dataset; document language is manually mapped. The 48 cases contain only 24 paired intents and must not be presented as independent samples.
- Baseline scores are saved verified runs; their historical timings are not a controlled speed comparison with this run.

## Next steps

1. Review the changed/missed cases and the actual translations, especially company identities and accounting terms.
2. Keep automatic language-aware BM25 as the leading measured candidate on these two reports; inspect why hybrid suppresses useful lexical hits rather than assuming fusion is better.
3. Repeat with real language detection and a broader mixed corpus before changing application defaults. Report retrieval accuracy alongside translation failure rate, latency and usage.

## Reproduction

```bash
.venv/bin/python scripts/retrieval/evaluate_bilingual_two_document_benchmark.py \
  --language-aware --device cuda \
  --output artifacts/evaluation/retrieval/scoped-automatic-translation.json
```

This command makes translation API calls. Existing reviewed-translation artifacts remain unchanged.
