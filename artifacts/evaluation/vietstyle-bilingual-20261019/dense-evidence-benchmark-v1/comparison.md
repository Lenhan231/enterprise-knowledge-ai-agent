# VietStyle dense evidence benchmark v1

20 paired intents, 80 cases per model, 4 directions. Each case searches all five documents in the target language. Shared 1,063 chunks (532 VI, 531 EN); no truncation, translation, hybrid, reranker or generation.

## Complete evidence in top 10

Q14 excluded from the full-intent denominator because required approval-role labels remain unresolved. Each direction has 19 eligible intents.

| Query → document | E5 multilingual base | BGE-M3 | Qwen3 0.6B |
|---|---:|---:|---:|
| vi->vi | 15/19 (78.9%) | 13/19 (68.4%) | 13/19 (68.4%) |
| en->en | 13/19 (68.4%) | 14/19 (73.7%) | 13/19 (68.4%) |
| vi->en | 8/19 (42.1%) | 14/19 (73.7%) | 14/19 (73.7%) |
| en->vi | 11/19 (57.9%) | 13/19 (68.4%) | 12/19 (63.2%) |

## Required component coverage in top 10

Includes ready components of Q14; pending and optional components excluded. This is binary completeness per annotated component, not raw character fraction or generated answer accuracy.

| Query → document | E5 multilingual base | BGE-M3 | Qwen3 0.6B |
|---|---:|---:|---:|
| vi->vi | 55/62 (88.7%) | 53/62 (85.5%) | 51/62 (82.3%) |
| en->en | 52/62 (83.9%) | 52/62 (83.9%) | 49/62 (79.0%) |
| vi->en | 38/62 (61.3%) | 51/62 (82.3%) | 52/62 (83.9%) |
| en->vi | 43/62 (69.4%) | 51/62 (82.3%) | 50/62 (80.6%) |

## Cases missing complete evidence

Q14 is excluded below; inspect candidate results.json for each missing component and alternative span.

### vi->vi

- multilingual-e5-base: Q11, Q13, Q18, Q20
- bge-m3: Q11, Q12, Q13, Q15, Q18, Q20
- qwen3-embedding-0.6b: Q11, Q12, Q13, Q17, Q18, Q20

### en->en

- multilingual-e5-base: Q11, Q12, Q13, Q15, Q18, Q20
- bge-m3: Q11, Q12, Q13, Q18, Q20
- qwen3-embedding-0.6b: Q11, Q12, Q15, Q17, Q18, Q20

### vi->en

- multilingual-e5-base: Q04, Q07, Q08, Q11, Q12, Q13, Q15, Q16, Q17, Q18, Q20
- bge-m3: Q11, Q12, Q13, Q18, Q20
- qwen3-embedding-0.6b: Q11, Q12, Q17, Q18, Q20

### en->vi

- multilingual-e5-base: Q08, Q11, Q12, Q13, Q15, Q17, Q18, Q20
- bge-m3: Q11, Q12, Q13, Q15, Q18, Q20
- qwen3-embedding-0.6b: Q11, Q12, Q13, Q15, Q17, Q18, Q20

## Interpretation and limits

Exact annotated evidence coverage is stricter than the previous expected-file metric; percentages are not comparable directly. Alternate valid evidence may be unlabelled. English files, queries and evidence are assistant-curated simulations, not independently certified. Four directions reuse the same 20 intents and are not 80 independent questions. This test isolates dense encoders within a target-language corpus; it does not evaluate production language selection or a mixed-language index. Q09/Q10 calculation inputs also come from the question; Q18 is unavailable-data abstention. These scores do not measure generated-answer correctness. The label validator and independent replay verified all 240 rankings and their span/component scores.

Production embedding service, live database/index, retrieval ranking and translation settings are unchanged. New outputs preserve the old benchmark artifacts.
