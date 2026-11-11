# Report benchmark results - 2026-11-02

Status: evaluation complete with provider/reference-coverage limitations. All 30 original questions attempted; 120 current metric records, zero evaluator errors or pending metrics. Knowledge-agent benchmarking remains deferred.

| Metric | Score | Scored cases | N/A |
| --- | ---: | ---: | ---: |
| Faithfulness | 84.5% | 4 | 26 |
| Factual Correctness | 6.9% | 30 | 0 |
| Numerical Accuracy | 100.0% | 3 | 27 |
| Report Completeness | 9.2% | 30 | 0 |

**Numerical Accuracy is not a whole-report correctness rate.** It covers 75 independently verified claims; 206 extracted claims lack adequate independent reference coverage. Verification coverage is 26.7%. Its mean covers only three cases and cannot be compared directly with SQL's row-based numerical score.

One complete and three partial downloads were produced. The remaining first-response outcomes are structured clarification, unsupported/confirmation responses or failures. See generation_outcomes in summary.json; completeness is scored across all 30 cases.

There were 50 preserved attempts, including quota retries, harness corrections and later user-authorized third-key retries. Four latest outcomes still have provider limitations. These results are an operationally constrained baseline, not a clean capability-only comparison.

Agent: qwen/qwen3.8-27b, temperature 0. Ragas judge: Codex CLI gpt-5.6-luna, medium reasoning, unchanged throughout. Generation falls back from the primary and numbered backup keys to GROQ_API_KEY_RAGAS. A process-local alias covers nested document providers; .env and application code are not edited.

References are independently queried and author-reviewed, not externally certified gold. Policy passages were not supplied as reference answers, and detail samples are bounded. Faithfulness uses actual retrieved evidence; factual correctness uses independent references. Missing reference coverage is disclosed, not substituted with manual scores.

## Per-question results

| ID | Outcome | Faithfulness | Factual | Numerical | Completeness |
| --- | --- | ---: | ---: | ---: | ---: |
| R01 | partial | 86.4% | 36.0% | 100.0% | 50.0% |
| R02 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R03 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R04 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R05 | complete | 93.1% | 40.0% | 100.0% | 50.0% |
| R06 | partial | 87.7% | 72.0% | 100.0% | 50.0% |
| R07 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R08 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R09 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R10 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R11 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R12 | unsupported | N/A | 0.0% | N/A | 25.0% |
| R13 | confirmation_required | N/A | 0.0% | N/A | 0.0% |
| R14 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R15 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R16 | failed | N/A | 0.0% | N/A | 0.0% |
| R17 | partial | 70.8% | 0.0% | N/A | 25.0% |
| R18 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R19 | clarification_required | N/A | 20.0% | N/A | 0.0% |
| R20 | unsupported | N/A | 0.0% | N/A | 0.0% |
| R21 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R22 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R23 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R24 | clarification_required | N/A | 0.0% | N/A | 0.0% |
| R25 | failed | N/A | 0.0% | N/A | 0.0% |
| R26 | failed | N/A | 0.0% | N/A | 0.0% |
| R27 | clarification_required | N/A | 0.0% | N/A | 25.0% |
| R28 | failed | N/A | 0.0% | N/A | 0.0% |
| R29 | clarification_required | N/A | 40.0% | N/A | 50.0% |
| R30 | failed | N/A | 0.0% | N/A | 0.0% |
