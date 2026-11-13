# Report benchmark using current SQL agent

Resumed on 2026-11-07 with the current working-tree source. The interrupted three-case scope and independently frozen questions/references were retained. Old generations were not reused. All 28 supported SQL snapshot checks match. Application source hashes are recorded and remained unchanged.

| Case | Outcome | Faithfulness | Factual correctness | Numerical accuracy | Completeness |
|---|---|---:|---:|---|---:|
| R01 | partial | 0.846 | 0.430 | Judge timeout | 0.500 |
| R06 | clarification_required | N/A | 0.000 | N/A | 0.000 |
| R07 | clarification_required | N/A | 0.000 | N/A | 0.000 |

R01 produced a downloadable partial report with 804 facts. Product detail hit the 200-row ceiling, and narrative generation failed. R06 initially hit a provider rate limit; the one provider-only retry ended with a missing reviewed metric definition. R07 rejected the planned historical period twice and requested clarification. Both R06 attempts remain in the append-only checkpoint.

R01 numerical evaluation timed out after 180 seconds. No numerical accuracy is claimed. Faithfulness has only one applicable case; two clarification responses are N/A. These three cases do not establish performance on the full 30-case suite. No paired current baseline was run.

Application code was not modified. Tests were not rerun for this benchmark-only task. Raw generations, attempts, evidence, judge traces and source provenance are saved beside this file.
