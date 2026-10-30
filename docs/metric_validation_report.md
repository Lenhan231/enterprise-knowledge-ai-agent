# Metric validation report

Status: pre-implementation baseline, 2026-10-30. Application code, models, Report generation, database records, RLS and migrations are unchanged.

## Existing tests

Executed through the repository's Python virtual environment and standard-library unittest runner, with LangSmith tracing disabled:

- test_sql_generation
- test_sql_metric_definitions
- test_sql_join_duplication
- test_report_agent
- test_report_reliability
- test_report_orchestration
- test_report_provider
- test_orchestration_contracts
- test_orchestration_clients

Result: **84 tests run, 83 passed, one failure, zero errors or skips**. The failing test is `test_orchestration_clients.WebConversationTest.test_inflight_answer_cannot_cross_a_conversation_reset`. Its mock template input lacks `.files`, causing the existing UI setup call to raise before the conversation-reset assertion. This failure exists before any task implementation and was not altered. Details: [offline-baseline.json](../artifacts/evaluation/vietstyle-metrics-v1/preflight/offline-baseline.json); the adjacent ignored `.log` retains the full local output.

An additional 30 tests all passed in `test_analytics_agents`, `test_bounded_execution`, `test_request_planning`, `test_report_grounding`, `test_report_delivery` and `test_report_templates`. Details: [contracts-baseline.json](../artifacts/evaluation/vietstyle-metrics-v1/preflight/contracts-baseline.json). Combined baseline: **114 tests, 113 passes and the one existing fixture failure**.

Full discovery and the new deterministic semantic regression suite have not run at this pre-implementation review gate. They must run after implementation; do not interpret this focused baseline as a clean full repository suite.

## Live SQL baseline, unchanged model

[llm-before.json](../artifacts/evaluation/vietstyle-metrics-v1/preflight/llm-before.json) freezes the questions, original plans/repair prompts, raw generation outputs, returned rows, stage outcomes, timing, usage, commit and source hashes.

Environment: `qwen/qwen3.8-27b`, temperature 0, reasoning disabled as configured by the existing provider, maximum 1,000 output tokens, sequential cases with 20 seconds between cases. This runs SQLAnalyticsAgent only, without answer/report synthesis. The existing analytics reader verifies its role and runs read-only queries. No live UPDATE/write probe was run.

| Case | Before outcome | Meaning |
| --- | --- | --- |
| Q5 monthly revenue and gross profit, 2022 | Executed, 12 rows | Existing source-sales definition; not proof of net revenue |
| Q6 top products by units, category and sales value | Clarification | Day-grain revenue conflict; suggests inventory units as an alternative |
| Q7 category return rates | Clarification | Correctly asks order-based versus unit-based definition |
| Q8 lowest product fill rates, latest snapshot | Rejected: MetricDefinitionError | Unsupported output dimension; no query executed |
| Q9 average delivery time by shipping month, 2022 | Executed, 12 rows | Ship-date cohort |
| Orders by status | Executed, six rows | No recognized canonical metric in baseline |
| Recorded payment value | Executed, one row | No recognized canonical metric in baseline |
| Unsupported website conversion | Clarification | No approved definition/attribution; arbitrary user formula must not create authorization |

Four executions, three clarifications and one rejection are outcome counts only. Generation success, AST validation, execution accuracy, metric correctness and clarification quality require separate scoring. There is no after result yet.

## Database reconciliation and risks

The [profile evidence](../artifacts/evaluation/vietstyle-metrics-v1/preflight/database-profile.json) rechecks the source totals, types, keys, NULLs, date ranges, states, inventory coverage, monetary differences and fanout. Specifically:

- Source revenue 16,430,476,585.53; recorded payments and calculated net item value each 15,680,869,265.43. Equality is not metric equivalence.
- A payment/item fanout SELECT produces an invalid inflated total of 17,106,421,854.80. Preserve rejection of this pattern in application validation.
- All inventory rows are month-end snapshots, latest 2022-12-31. Latest coverage is 424 of 2,412 catalog IDs, not the complete catalog.
- Sixteen order/product pairs have multiple item lines. Two return pairs have repeated events. Correct return-quantity calculations require pair-level aggregation and uniqueness proofs.
- Signup chronology and incomplete traffic channel-day coverage constrain acquisition and attribution claims.
- Controlled policy excerpts require unknown currency, compatible grain, explicit historical dates, read-only authority, evidence and clarification.

## Planned verification after review

- Catalog schema, unique IDs/versions, bilingual/plural aliases, status/provenance separation, valid column references, unresolved execution rejection.
- Real calculations on small deterministic fixtures, including orders with multiple lines, repeated returns, cancellations, partial returns, zero denominators, missing snapshots and varied SKU coverage.
- Per-metric dimensions/source lineage, required filters, explicit request-period scope, scalar stored-value versus aggregate semantics, and safe latest-snapshot behavior.
- Q6: product units and value use the reviewed transaction definition; never substitute inventory units without an explicit choice.
- Q7: bare return rate clarifies; explicit category order/unit variants calculate the correct cohort and denominator without fanout.
- Q8: historical latest-snapshot SKU ranking returns the correct stored fill values and as-of scope.
- RBAC denial happens before provider or execution; malformed/unapproved SQL, unsafe joins, writes and unsupported aggregates never execute.
- Analytics summary and Report source contracts retain limitations and clarification without changing Report generation behavior.
- Replay frozen before-case outputs through the new validator to isolate enforcement changes, then run the same-model live after benchmark. Record provider failures and scope changes rather than attributing them to semantic improvement.

## Files added in this inspection phase

| File | Reason and contents | Checks/results |
| --- | --- | --- |
| CAPABILITY-MAP-business-metric-dictionary.md | Proposed module responsibilities, dependencies and initial assumptions | Human review pending |
| docs/business_metric_dictionary.md | Existing path inspection, live data findings, catalog shape, conventions and unresolved decisions | Cross-referenced to SELECT evidence and baseline |
| docs/metric_validation_report.md | This pre-implementation report and verification plan | 84 existing focused tests; results above |
| artifacts/evaluation/vietstyle-metrics-v1/preflight/database-profile.json | SQL/results and selected policy evidence | Read-only metadata/aggregates; no customer rows |
| artifacts/evaluation/vietstyle-metrics-v1/preflight/offline-baseline.json | Existing test IDs and outcomes | 83 pass, one existing fixture failure |
| artifacts/evaluation/vietstyle-metrics-v1/preflight/contracts-baseline.json | Additional analytics, routing, planning and Report contract baseline | All 30 pass |
| artifacts/evaluation/vietstyle-metrics-v1/preflight/llm-before.json | Frozen original-model baseline, plans and returned data | Eight cases completed; no provider/model changes |

No runtime files have been changed. The executable catalog, enforcement changes, new tests and before/after comparison remain to be implemented after the invoked specification review gates.
