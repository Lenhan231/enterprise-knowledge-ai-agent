# Evidence v1 → v2: label-only rescore

Post-hoc label review after observing v1 errors. V2 is exploratory, not held-out performance improvement. Rankings and encoders unchanged; evaluate every candidate under the same v2.

Same top ten chunks, 1,063 shared passages and 80 cases/model from 20 paired intents. No encoder/GPU, translation, reranker, generation or DB run. Q14 remains excluded from full-intent denominator.

## Complete-evidence cases: v1 → v2

All counts below are out of 19 eligible intents per direction.

| Query → documents | E5 multilingual base | BGE-M3 | Qwen3 0.6B |
|---|---:|---:|---:|
| vi->vi | 15 → 17 | 13 → 14 | 13 → 14 |
| en->en | 13 → 14 | 14 → 15 | 13 → 14 |
| vi->en | 8 → 9 | 14 → 15 | 14 → 15 |
| en->vi | 11 → 12 | 13 → 14 | 12 → 13 |

## Required component coverage (v2)

Denominator is 61 ready required components per direction, versus 62 in v1; Q18.no_guess moved to optional context. Do not treat a percentage rise as encoder improvement.

| Query → documents | E5 multilingual base | BGE-M3 | Qwen3 0.6B |
|---|---:|---:|---:|
| vi->vi | 57/61 (93.4%) | 54/61 (88.5%) | 52/61 (85.2%) |
| en->en | 52/61 (85.2%) | 53/61 (86.9%) | 50/61 (82.0%) |
| vi->en | 38/61 (62.3%) | 52/61 (85.2%) | 53/61 (86.9%) |
| en->vi | 43/61 (70.5%) | 52/61 (85.2%) | 51/61 (83.6%) |

## Remaining incomplete VI → VI intents

- multilingual-e5-base: Q13, Q20
- bge-m3: Q11, Q12, Q13, Q15, Q20
- qwen3-embedding-0.6b: Q11, Q12, Q13, Q17, Q20

Original v1 files and scores are preserved. V2 is assistant-reviewed, not independently certified; alternative evidence is still non-exhaustive. No generated answers were evaluated. See evidence-v2/annotation-changes.json for every before/after component and semantic rationale.
