# Analysis of An’s latest benchmarks — 2026-10-17

Inspected QuocAn commit [`67f8157`](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/67f815761714d01c330d1f53bc2d7dda208d8173). This is an audit of committed code and saved artifacts, not a new inference run. No translation/generation API calls or database queries were made.

## Main conclusions

1. An adopted the current Huy retrieval modules, including the query translator file, but the financial benchmark does not call that translator. Its normal service call uses untranslated hybrid with dense:BM25 1:2 and no document/company/role scope. Copying the translator module does not enable it automatically.
2. The finance result is not a new test of our automatic language-aware pipeline. Recall@10 remains 0.2292, the same as the earlier unscoped untranslated Huy run. MRR falls slightly from 0.2014 to 0.1935; only Q08’s metric values changed (first gold rank 3 to 7).
3. The new VietStyle result is promising for source discovery but protocol details are inconsistent: 79 of 200 retrieved chunks, across 18 of 20 questions, are outside its listed five-document pack. This shows the saved contexts are not limited to the advertised pack. It does not demonstrate an authorization-filter bypass; the run may simply have omitted the document filter.
4. Source-file recall, exact-chunk recall and answer quality must be reported separately. A score of 83.33% source recall is not 83.33% answer accuracy.

## Finance: Long Hau / PVFCCo, 24 Vietnamese questions

| Metric | Older dense baseline | Earlier unscoped hybrid | New latest hybrid |
|---|---:|---:|---:|
| Recall@10 | 0.4375 | 0.2292 | 0.2292 |
| Precision@10 | 0.0458 | 0.0250 | 0.0250 |
| MRR | 0.2174 | 0.2014 | 0.1935 |
| nDCG@10 | 0.2675 | 0.1977 | 0.1907 |

All 24 new per-case recall/MRR/nDCG values were independently recomputed from ranked IDs. Saved gold text matches the earlier unscoped hybrid artifact. The new report lacks corpus/case hashes and precise retrieval configuration, so unchanged gold text alone does not prove an identical whole corpus.

The language pattern remains: PVFCCo exact-chunk Recall@10 8.33%, Long Hau 40%, and cross-document cases 25%. Vietnamese queries against the English report remain weak without translated lexical queries.

The runner still calls `retrieval.retrieve(RetrievalRequest(...))` without method/scope arguments. The service defaults to hybrid and does not import or invoke QueryTranslator. The normal app/service remains distinct from our automatic-translation benchmark.

Our saved automatic-language-aware scores (77.08%/83.33% BM25, 72.92%/66.67% hybrid for EN/VI queries) are scoped, translated exact-chunk experiments. They cannot be presented as a directly paired improvement over this unscoped untranslated run.

### Finance generation completion

| Model | Completed | Rate-limit errors |
|---|---:|---:|
| gpt_oss_20b | 15 | 9 |
| gemini_flash | 6 | 18 |
| qwen3 | 24 | 0 |

45 of 72 planned model answers completed. The other 27 failed with RateLimitError. This is a provider-availability limitation, not proof of retrieval failure or model answer inferiority. Raw completion counts do not establish answer accuracy; restrict model comparisons to matching completed questions and review citations/facts.

## VietStyle: 20 policy questions

- Recomputed mean source-file Recall@10: **83.33%**.
- Generated answers: **19/20** completed. Q05 failed citation validation; it used unbracketed source mentions instead of accepted citation tokens. Keep the validator and fix prompting/formatting rather than weakening citation checks.
- Actual scope: **79/200 chunks (39.5%)** come from outside the five listed VietStyle documents; **18/20 questions** are affected. Returned outside sources include synthetic Commerce Demo policies, Shopee, Tiki, inventory-allocation and Long Hau content.
- Q15 has source recall 1.0, but **9 of its 10 chunks** are outside the listed pack. This illustrates why source recall does not measure context precision or resistance to distractors.
- Q01 has source recall 0.0, yet the answer states the expected v1.0, 16/10/2026, and unapproved/simulated status, citing another VietStyle passage. This is a source-label/answer-evidence mismatch requiring review, not an automatic answer failure.
- README.txt is declared absent and is expected by Q01/Q18/Q19. If that is the only missing expected source, the maximum achievable source recall under the existing labels is **95%**, not 100%. Keep the raw score and report coverage separately; index README or review benchmark eligibility rather than silently changing denominators.

### Cases with incomplete expected-source coverage

| Case | Source recall | Outside-pack chunks / 10 | Missing expected files |
|---|---:|---:|---|
| Q01 | 0.0000 | 7 | 01_Inventory_Management_Policy_Manual.docx; 03_Policy_Rules_Registry.csv; README.txt |
| Q05 | 0.5000 | 4 | 03_Policy_Rules_Registry.csv |
| Q11 | 0.5000 | 4 | 02_SOP_Cycle_Count_and_Stock_Adjustment.pdf |
| Q14 | 0.6667 | 1 | 05_Inventory_Policy_Training_Deck.pptx |
| Q16 | 0.6667 | 2 | 03_Policy_Rules_Registry.csv |
| Q18 | 0.6667 | 0 | README.txt |
| Q19 | 0.6667 | 5 | README.txt |

### Earlier scoped pilot versus latest first five questions

| Method / run | Questions | Mean source Recall@10 |
|---|---|---:|
| Pilot dense, scoped pack | Q01–Q05 | 0.8333 |
| Pilot hybrid, scoped pack | Q01–Q05 | 0.9333 |
| Pilot translated hybrid, scoped pack | Q01–Q05 | 0.8333 |
| Latest hybrid, contexts include outside documents | Q01–Q05 | 0.7000 |

All pilot returned contexts stayed inside its listed five-document scope. The latest first-five scores are Q01=0, Q02=1, Q03=1, Q04=1, Q05=0.5; pilot hybrid had Q01=0.6667 and all four others=1. The scope/protocol changed, so this is not evidence that the adopted retrieval implementation itself regressed.

The 20-question policy artifact is not a paired dense/BM25/hybrid comparison: it contains only latest hybrid. The five-question translated pilot does not prove general translation benefit or harm. Source languages, translation telemetry and a reproducible VietStyle runner are not committed with these artifacts; the exact translated path cannot be fully verified from the results alone.

## Practical next actions

1. **Make runtime selection explicit.** Finance: pass the selected method, both report IDs, and benchmark role. For an automatic-translation test, invoke the actual translation-and-language-routing pipeline, not the raw RetrievalService default.
2. **Repair VietStyle scope reporting.** For a scoped test, apply all five document IDs to every method and verify every returned ID. For a mixed-corpus test, retain distractors but label it explicitly as mixed and keep the scoped result separately. Persist the runner used to generate the 20-question artifact.
3. **Run a fair same-snapshot matrix:** dense, BM25, hybrid, and automatic language-aware lexical/hybrid on the same cases, permissions, corpus and scope. Record git/source hashes, input hashes, method/weights, translation model/output/errors, and exact source IDs.
4. **Separate three score layers:** expected-file discovery, relevant passage retrieval, and answer correctness/citation validity. Add passage labels and independently review alternate valid evidence. Do not change labels solely to improve a score.
5. **Fix corpus coverage and API-run completeness:** index or explicitly account for README; resume rate-limited generation only for failed calls, preserving earlier outputs. No additional inference was performed by this audit.

## Evidence links

- [Latest finance artifact](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/67f815761714d01c330d1f53bc2d7dda208d8173/artifacts/benchmark/long_hau_2008_q01-24_latest_retrieval.json).
- [Latest VietStyle 20-question artifact](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/67f815761714d01c330d1f53bc2d7dda208d8173/artifacts/benchmark/vietstyle_q01-20_latest_retrieval.json).
- [Scoped five-question policy pilot](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/67f815761714d01c330d1f53bc2d7dda208d8173/artifacts/benchmark/vietstyle_q01-05_huy.json).
- [Finance runner](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/67f815761714d01c330d1f53bc2d7dda208d8173/evaluation/run_generation_benchmark.py).
- [RetrievalService](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/67f815761714d01c330d1f53bc2d7dda208d8173/src/core/retrieval/retrieval_service.py).
- [Machine-readable audit](an-latest-benchmark-analysis-20261017.json): source commit, artifact hashes, per-case scope/recall checks and completion counts.
