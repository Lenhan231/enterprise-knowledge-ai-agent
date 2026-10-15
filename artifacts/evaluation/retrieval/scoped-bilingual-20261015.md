# Paired bilingual retrieval experiment — 2026-10-15

48 original-language cases represent 24 paired EN/VI intents, not 48 independent questions. Each case is evaluated with bilingual BM25 and bilingual hybrid (96 result rows). Both use the existing reviewed translations, not an automatic translation service.

The corpus/case hashes match the earlier scoped baselines: 249 chunks from the same two reports. All results stayed in scope. Database access was read-only; no generation calls were made. GPU query embedding used paraphrase-multilingual-MiniLM-L12-v2.

English and Vietnamese BM25 searches each return up to 100 candidates, fused with equal reciprocal-rank weights (k=60). Bilingual hybrid fuses that top-100 ranking with original-language dense candidates, weighted dense:lexical 1:2. Deterministic chunk-ID tie breaking differs from SQL hybrid. Thus this tests a specific two-stage fusion recipe, not translation alone.

| Original query | Method | Recall@10 | MRR | nDCG@10 |
|---|---|---:|---:|---:|
| en | dense | 0.3958 | 0.2606 | 0.2865 |
| en | hybrid | 0.4583 | 0.2583 | 0.3036 |
| en | bm25 | 0.4583 | 0.3935 | 0.3989 |
| en | bilingual_bm25 | 0.4375 | 0.2035 | 0.2604 |
| en | bilingual_hybrid | 0.4375 | 0.2465 | 0.2890 |
| vn | dense | 0.4375 | 0.2174 | 0.2675 |
| vn | hybrid | 0.3125 | 0.2182 | 0.2348 |
| vn | bm25 | 0.3542 | 0.2465 | 0.2726 |
| vn | bilingual_bm25 | 0.4375 | 0.2035 | 0.2604 |
| vn | bilingual_hybrid | 0.4375 | 0.2639 | 0.3041 |

## Conclusion

Bilingual hybrid improves Vietnamese-query recall versus default hybrid (0.3125 to 0.4375), but English-query recall falls (0.4583 to 0.4375). Vietnamese MRR improves (0.2182 to 0.2639); English MRR declines (0.2583 to 0.2465). Bilingual BM25 has the same recall for both original languages by construction, and its MRR of 0.2035 is below either single-language BM25 aggregate.

Do not change defaults based on this recipe. Equal fusion of both language rankings still mixes useful and cross-language noisy candidates. Next isolate document-language-specific lexical querying, with genuine document-language metadata and a separate mixed-corpus evaluation; do not select languages from gold labels in a claimed production benchmark.

Evidence: `scoped-bilingual-20261015.json`. Reproduce with `scripts/retrieval/evaluate_bilingual_two_document_benchmark.py --device cuda`. Self-check: append `--self-check`.
