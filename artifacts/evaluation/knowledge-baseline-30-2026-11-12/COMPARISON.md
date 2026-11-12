# Corrected Knowledge baseline versus integrated v3

In this corrected run, v3 scores +2.29 percentage points on faithfulness, +0.05 points on answer relevancy, and +3.62 points on context precision. The earlier apparent overall regression is not reproduced. Relevancy is effectively unchanged; this is one run, not a significance claim.

The historical runtime is import-verified. The earlier 2026-11-11 experiment was invalid and is not used. See [method, schema adaptation and limitations](README.md). Both cohorts use identical questions, references and indexed policy data.

## all_common

| Metric | Common scored cases | Historical baseline | Integrated v3 | Change (pp) |
|---|---:|---:|---:|---:|
| faithfulness | 24 | 92.71% | 95.00% | +2.29 |
| answer_relevancy | 30 | 75.19% | 75.24% | +0.05 |
| context_precision | 30 | 84.63% | 88.25% | +3.62 |

## supported_only

| Metric | Common scored cases | Historical baseline | Integrated v3 | Change (pp) |
|---|---:|---:|---:|---:|
| faithfulness | 24 | 92.71% | 95.00% | +2.29 |
| answer_relevancy | 25 | 90.22% | 90.28% | +0.06 |
| context_precision | 25 | 84.53% | 90.10% | +5.57 |

## Outcomes

| Outcome | Historical baseline | Integrated v3 |
|---|---|---|
| generation_failures | [] | [] |
| supported_refusals | ['K17'] | ['K17'] |
| correct_unsupported_refusals | 5 | 5 |

Faithfulness is N/A for refusals. Supported-only metrics exclude the five intentionally unsupported lookups. Context precision depends on passage ranking and LLM relevance judgments; answer relevancy uses generated questions and embeddings. Neither is a deterministic correctness test. Quantization, prompt changes and hosted inference/judge variation are confounded; this run cannot establish which change caused a score difference. No statistical-significance or speed claim is made.

Per-case score differences and equal-answer/equal-context checks are in [comparison.json](comparison.json). All raw generations, contexts, scores, runtime-import hashes and read-only database snapshots are retained.
