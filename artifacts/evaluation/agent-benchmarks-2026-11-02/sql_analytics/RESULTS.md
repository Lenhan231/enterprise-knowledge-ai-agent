# SQL benchmark results - 2026-11-02

Status: complete. All 30 original questions attempted; 90 current metric records, zero evaluator errors or pending metrics. Earlier attempts and scoring revisions remain in the audit files.

| Metric | Score | Scored cases | N/A |
| --- | ---: | ---: | ---: |
| Execution Accuracy | 21.4% | 28 | 2 |
| SQL Semantic Equivalence | 14.3% | 28 | 2 |
| Numerical Accuracy | 22.3% | 27 | 3 |

Nine requests returned rows; two executed with empty results. Fourteen requested clarification; five failed metric/SQL validation. There were 42 generation attempts including preserved quota retries. No latest SQL outcome is a quota failure.

S29/S30 lack valid current-stock/supplier evidence and have no executable numeric gold, so all three metrics are N/A. S01 requests a date, so Numerical Accuracy is N/A. Supported questions that fail to return the required result score zero.

Execution uses independent SQL results, including scoped numeric-cell comparisons. Semantic equivalence uses Ragas with Codex CLI `gpt-5.6-luna`, reasoning `medium`. Agent model: `qwen/qwen3.8-27b`, temperature 0. Full definitions and limitations are in the parent README.

The final catalog audit found 186 ambiguous product names among 2,412 product records. Names identify a product ID only when the full-catalog count is one; ambiguous names receive no entity-level numeric credit. Valid rows in a mixed result retain partial numerical credit. The identity audit supplements the original frozen oracle SQL/results without changing their values.

References are author-reviewed, not independently certified gold. Detail queries use a 200-row ceiling and explicit reference ordering; an alternative ordering/default limit can affect exact execution matching. Numerical scores use 1e-6 absolute / 1e-12 relative tolerance.

## Per-question results

| ID | Outcome | Execution | SQL semantic | Numerical |
| --- | --- | ---: | ---: | ---: |
| S01 | executed_with_rows | 100.0% | 0.0% | N/A |
| S02 | clarification_required | 0.0% | 0.0% | 0.0% |
| S03 | clarification_required | 0.0% | 0.0% | 0.0% |
| S04 | clarification_required | 0.0% | 0.0% | 0.0% |
| S05 | executed_empty | 0.0% | 0.0% | 0.0% |
| S06 | clarification_required | 0.0% | 0.0% | 0.0% |
| S07 | clarification_required | 0.0% | 0.0% | 0.0% |
| S08 | clarification_required | 0.0% | 0.0% | 0.0% |
| S09 | clarification_required | 0.0% | 0.0% | 0.0% |
| S10 | MetricDefinitionError | 0.0% | 0.0% | 0.0% |
| S11 | clarification_required | 0.0% | 0.0% | 0.0% |
| S12 | executed_with_rows | 100.0% | 0.0% | 100.0% |
| S13 | MetricDefinitionError | 0.0% | 0.0% | 0.0% |
| S14 | SQLValidationError | 0.0% | 0.0% | 0.0% |
| S15 | clarification_required | 0.0% | 0.0% | 0.0% |
| S16 | executed_with_rows | 0.0% | 0.0% | 0.0% |
| S17 | executed_with_rows | 0.0% | 0.0% | 48.1% |
| S18 | executed_empty | 0.0% | 100.0% | 0.0% |
| S19 | executed_with_rows | 100.0% | 100.0% | 100.0% |
| S20 | executed_with_rows | 100.0% | 0.0% | 100.0% |
| S21 | executed_with_rows | 0.0% | 0.0% | 53.8% |
| S22 | executed_with_rows | 100.0% | 100.0% | 100.0% |
| S23 | clarification_required | 0.0% | 0.0% | 0.0% |
| S24 | executed_with_rows | 100.0% | 100.0% | 100.0% |
| S25 | clarification_required | 0.0% | 0.0% | 0.0% |
| S26 | clarification_required | 0.0% | 0.0% | 0.0% |
| S27 | clarification_required | 0.0% | 0.0% | 0.0% |
| S28 | SQLValidationError | 0.0% | 0.0% | 0.0% |
| S29 | MetricDefinitionError | N/A | N/A | N/A |
| S30 | clarification_required | N/A | N/A | N/A |
