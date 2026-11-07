# vietstyle-bilingual-evidence-v2 → vietstyle-bilingual-evidence-v3: label-only rescore

Post-hoc evidence correction after inspecting reranker output; label-only score changes are not retrieval/model improvement. No independent held-out claim.

Same top ten chunks, 1,063 shared passages and 80 cases/model from 20 paired intents. No encoder/GPU, translation, reranker, generation or DB run. Q14 remains excluded from full-intent denominator.

## Complete-evidence cases: previous → revised

All counts below are out of 19 eligible intents per direction.

| Query → documents | multilingual-e5-base | bge-m3 | qwen3-embedding-0.6b | e5-bge-reranker-v2-m3 |
|---|---:|---:|---:|---:|
| vi->vi | 17 → 17 | 14 → 15 | 14 → 14 | 17 → 17 |
| en->en | 14 → 14 | 15 → 15 | 14 → 14 | 14 → 14 |
| vi->en | 9 → 9 | 15 → 15 | 15 → 15 | 12 → 12 |
| en->vi | 12 → 12 | 14 → 15 | 13 → 13 | 12 → 12 |

## Required component coverage (revised labels)

Required-component counts are shown explicitly. Label-only score changes do not indicate model improvement.

| Query → documents | multilingual-e5-base | bge-m3 | qwen3-embedding-0.6b | e5-bge-reranker-v2-m3 |
|---|---:|---:|---:|---:|
| vi->vi | 57/61 (93.4%) | 55/61 (90.2%) | 52/61 (85.2%) | 59/61 (96.7%) |
| en->en | 52/61 (85.2%) | 53/61 (86.9%) | 50/61 (82.0%) | 55/61 (90.2%) |
| vi->en | 38/61 (62.3%) | 52/61 (85.2%) | 53/61 (86.9%) | 46/61 (75.4%) |
| en->vi | 43/61 (70.5%) | 53/61 (86.9%) | 51/61 (83.6%) | 49/61 (80.3%) |

## Remaining incomplete VI → VI intents

- multilingual-e5-base: Q13, Q20
- bge-m3: Q11, Q12, Q13, Q20
- qwen3-embedding-0.6b: Q11, Q12, Q13, Q17, Q20
- e5-bge-reranker-v2-m3: Q13, Q15

Previous label files and scores are preserved. Revised labels are assistant-reviewed, not independently certified; alternative evidence is still non-exhaustive. No generated answers were evaluated. See the revised label folder annotation-changes.json for every before/after component and semantic rationale.
