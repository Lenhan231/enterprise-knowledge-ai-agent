# Fresh reviewed v1 — Colab results

Completed on Colab NVIDIA L4, FP32. Returned 2026-10-21; copied from Downloads to colab-results/ with byte-hash checks. Original download retained. Verified locally using code and inputs extracted from the EXACT uploaded bundle, not an assumed current checkout: 48 dense pools,144 reranked case rankings,4320 saved score entries, rendered inputs, identical-input lineage and independent character coverage passed. Colab verification is preserved as colab-verification.json.

## Full required evidence in final ten original chunks

| Query → document | Dense | Plain reranker | Parent-plain | Narrative-parent | Available in candidate30 |
|---|---:|---:|---:|---:|---:|
| vi->vi | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| en->en | 11/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| vi->en | 8/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| en->vi | 8/12 | 10/12 | 10/12 | 10/12 | 10/12 |

## Required components

| Direction | Dense | Each reranker variant | Candidate30 |
|---|---:|---:|---:|
| vi->vi | 28/28 | 28/28 | 28/28 |
| en->en | 26/28 | 28/28 | 28/28 |
| vi->en | 19/28 | 28/28 | 28/28 |
| en->vi | 18/28 | 23/28 | 23/28 |

## Findings

- Dense covers39/48 full cases and91/112 required components. Each reranker covers46/48 cases and107/112 components. Directional cases reuse12 bilingual paired intents; these are not48 independent questions.
- Plain reranking fixes EN→EN F10; VI→EN F04,F09,F10,F12; EN→VI F09,F12. No full-intent or required-component regressions relative to dense in any variant.
- All three rerankers have IDENTICAL per-case evidence outcomes, not necessarily identical rankings. Added predecessor/narrative context has no additional evidence gain on this fresh set. It does not independently confirm the improvement observed on the original repeatedly inspected questions.
- Every reranker reaches the full-evidence availability of its candidate30 pool on this set. Remaining errors are candidate retrieval misses, not final reranker selection failures.
- F03 EN→VI (three required emergency-PO record fields): gold Manual chunk5 is dense rank187 among Vietnamese passages, so none of those components enters top30.
- F08 EN→VI (variant identifiers and no merging): gold SOP chunk2 is dense rank33, just outside top30. These ranks are offline diagnostics using SAVED query/document vectors, not a new embedding run.
- A modest larger pool could expose F08 but would not resolve F03 at rank187. Next investigation should focus on EN→VI candidate generation (for example compare the existing automatic translated-hybrid candidate path under the same frozen scope), rather than more reranker changes or a blanket very large pool. Any follow-up tuning makes this set development data; retain this original result unchanged.

## Runtime and scope

Pinned E5 queries: 1.74s. Shared reranking compute: 39.98s across48 cases on NVIDIA L4. These exclude several setup/preflight/evaluation steps and do NOT measure standalone per-arm latency or end-to-end answer time. Narrative scores reuse exact matching new-run plain/parent inputs, never historical-question scores.

Observed query max42/512 and candidate-pair max678/1024 tokens; zero truncation. Existing1063 document vectors were reused,24 new query texts embedded for48 directional cases. Five target-language documents compete; admin scope. No automatic translation/hybrid, generation, production integration, new parser output, database write or re-embedding of documents occurred.

Labels are assistant-prepared/reviewed and user-approved; source documents/English translations are simulated and alternatives remain curated. This small extension has overlap with prior questions and is not independently held-out proof. Scores measure annotated evidence retrieval, not LLM answer accuracy. Frozen questions, labels, inputs and benchmark outputs are unchanged.
