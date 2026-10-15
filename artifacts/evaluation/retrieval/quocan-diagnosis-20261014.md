# QuocAn retrieval diagnosis — 2026-10-14

## Conclusion

The observed regression is reproducible and comes from hybrid ranking with dense:BM25 weights 1:2. Current Huy dense retrieval reproduces the older dense-only baseline exactly. This is a configuration/method regression on this dataset, not evidence that the dense implementation regressed.

## Controlled replay

- QuocAn artifact commit: `6564702c93a028d803c309431e60e447d87bc0c3`.
- Local Huy retrieval commit: `751469c1dafc573aa28c7b52e49bf7c4a447ccb7` (retrieval code identical to origin/Huy 84393ed at inspection).
- Same read-only repeatable-read snapshot: 827 chunks; identical query vectors for every variant; top-k 10.
- All 24 legacy dense rankings and all 24 default-hybrid rankings match the saved artifacts exactly, including order. All gold text matches the indexed snapshot.
- Embedding model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. Neither database data nor production retrieval code was changed. No generation calls were made.
- Metrics below are exact labeled-chunk retrieval, not document retrieval or answer quality. Precision is sparse-label precision, not a full human relevance assessment.

| Method | Dense:BM25 | Recall@10 | MRR | nDCG@10 |
|---|---|---:|---:|---:|
| Older baseline | — | 0.4375 | 0.2174 | 0.2675 |
| Current Huy dense | — | 0.4375 | 0.2174 | 0.2675 |
| BM25 | — | 0.3542 | 0.2292 | 0.2578 |
| Default hybrid | 1:2 | 0.2292 | 0.2014 | 0.1977 |
| Hybrid | 1:1 | 0.2708 | 0.2028 | 0.2137 |
| Hybrid | 2:1 | 0.3958 | 0.2323 | 0.2652 |
| Hybrid | 4:1 | 0.3958 | 0.2431 | 0.2741 |

## Why it drops

- Q01–Q12 are Vietnamese queries over the English PVFCCo report. Dense Recall@10 is 0.5833, BM25 is 0.0000, default hybrid is 0.0833. BM25 uses literal PostgreSQL simple lexemes without translation; unrelated Vietnamese passages displace English evidence in the weighted rank fusion.
- Q13–Q22 query Vietnamese Long Hậu OCR text. Dense Recall@10 is 0.3000, default hybrid is 0.4000, BM25 is 0.8000. Lexical retrieval is useful on this subset, but fusion can still suppress useful BM25-only hits.
- Example Q04: dense retrieves the labeled PVFCCo fertilizer-import chunk at rank 1; default hybrid misses it and ranks Long Hậu tables and a Tiki passage first. With weights 2:1 the gold chunk returns at rank 7, and with 4:1 at rank 4.
- Both documents have company `Commerce Demo`, no fiscal year, and status `ready`. There are no orphaned or non-ready chunks in this live snapshot. Year preference therefore cannot explain these benchmark-document ranks.
- Benchmark calls retrieval without company or role scope, so it searches the mixed corpus. Changing a shared company filter to Commerce Demo would not distinguish PVFCCo from Long Hậu or the commerce documents. Actual company/document scope requires appropriate metadata and caller inputs.

## Evaluation caveats

- `long_hau_2008_huy_retrieval.json` contains all 24 questions. `long_hau_2008_huy_full_verified.json` contains only Q01–Q18; compare on matching case IDs, not their headline aggregates.
- Saved reports omit retrieval method/weights, source commit, corpus/case hashes and applied scope. Future comparisons should record these and run all methods on the same frozen snapshot.
- Exact chunk labels are non-exhaustive. Q14 retrieves another page containing an OCR form of the auditor name but misses the labeled auditor chunk. That is a labeled retrieval miss; judge actual answer evidence separately.
- Several cases fail under every tested method (including Q01, Q03, Q07, Q11, Q12, Q15, Q16 and Q24). Weight tuning alone does not resolve those cases; inspect OCR, table context, bilingual queries and gold coverage.
- Diagnostic pitfall: integer weight parameters cause PostgreSQL integer division in the current RRF expression. The final replay uses floats matching production defaults. Supporting integer caller inputs would require explicit floating-point division; this did not cause QuocAn’s saved regression.

## Recommended next steps

1. Make the benchmark method and weights explicit. Keep current dense as the reproducible baseline; do not replace its baseline numbers with document-level embedding-benchmark scores.
2. Use dense for the cross-language benchmark path while evaluating bilingual lexical queries or explicit language-aware method selection. Keep BM25 available for same-language finance queries.
3. Treat dense:BM25 2:1 or 4:1 as measured tuning candidates, not a new universal default. They recover Recall@10 to 0.3958, still below dense 0.4375; 4:1 improves MRR to 0.2431 on this small set.
4. Review actual company, document language, source revision and gold coverage with the data owner. Preserve OCR/table page context; do not fabricate headings or restrict search to gold documents simply to inflate metrics.

Per-query rankings and hashes: `quocan-diagnosis-20261014.json`. Read-only reproduction: `replay-quocan-diagnosis.py`.
