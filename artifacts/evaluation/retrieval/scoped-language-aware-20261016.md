# Document-language-aware retrieval — 2026-10-16

Controlled GPU run: 24 paired intents evaluated in both original languages (48 cases), with language-aware BM25 and hybrid (96 result rows). The same 249 chunks, cases, labels and scope as the saved baselines were hash-verified. All outputs stayed in the two-report scope; every lexical result also passed its query-language document-scope assertion. Database access was read-only.

## Protocol

- Fixed verified metadata: PVFCCo English; Long Hau Vietnamese. No database schema changes and no selection based on a question’s expected source.
- Search both language groups for every question: English query against English document(s), Vietnamese query against Vietnamese document(s). The other-language query comes from existing reviewed paired translations, not an automatic translator.
- Each lexical search returns up to 100 candidates. Fuse the two lists with equal RRF weights, k=60. This also changes corpus-local BM25 statistics because each search uses its own eligible language group.
- Hybrid then fuses original-query dense ranking over both reports with the language-aware lexical ranking (dense 1: lexical 2, k=60, 100 candidates each). Return top 10. Deterministic chunk-ID ties and two-stage fusion differ from the SQL hybrid baseline.
- Dense retains the original user-query language; it does not receive the paired translation.

| Original query | Method | Recall@10 | Precision@10 | MRR | nDCG@10 |
|---|---|---:|---:|---:|---:|
| en | dense | 0.3958 | 0.0417 | 0.2606 | 0.2865 |
| en | hybrid | 0.4583 | 0.0500 | 0.2583 | 0.3036 |
| en | language_aware_bm25 | 0.8125 | 0.0875 | 0.4938 | 0.5654 |
| en | language_aware_hybrid | 0.7292 | 0.0792 | 0.4418 | 0.5063 |
| vn | dense | 0.4375 | 0.0458 | 0.2174 | 0.2675 |
| vn | hybrid | 0.3125 | 0.0333 | 0.2182 | 0.2348 |
| vn | language_aware_bm25 | 0.8125 | 0.0875 | 0.4938 | 0.5654 |
| vn | language_aware_hybrid | 0.6458 | 0.0708 | 0.4352 | 0.4804 |

## Interpretation and limits

Language-aware lexical search improves recall versus both single-language hybrid and the earlier blind bilingual fusion. BM25 alone is strongest in this run: recall 0.8125, MRR 0.4938. Adding dense loses some lexical evidence, so default hybrid weights should not be adopted as universally better.

This is evidence for manually verified document-language routing with reviewed translations on two reports. It does not establish automatic language detection, automatic translation accuracy/latency, scalability, mixed-corpus robustness, or generated-answer quality. The two original-language evaluations share 24 intents and are not independent samples. BM25 is identical for both original languages by construction.

Next isolate real automatic translation quality/cost and verify routing over a broader multilingual corpus. Keep these frozen references and compare failed gold chunks before choosing the fusion policy.

Reproduce: `.venv/bin/python scripts/retrieval/evaluate_bilingual_two_document_benchmark.py --language-aware --device cuda --output artifacts/evaluation/retrieval/scoped-language-aware-20261016.json`.

Full evidence: `scoped-language-aware-20261016.json`.
