# SQL Agent 40-case benchmark protocol v3.1

This protocol applies only to `cases_v3_1_draft.json`, `gold_sql_v3_1_draft.json`, and their versioned v3.1 references. It does not alter the historical v3 protocol or results. The case set is a draft; independent review and freeze are still pending.

## Attempt and denominator policy

Only attempted cases enter quality denominators. Explicit `NOT RUN` cases are excluded; a zero denominator is reported as `NOT MEASURABLE`.

For supported (`expected_behavior=execute`) cases:

- **Business End-to-End Accuracy** = executed, independently audited PASS cases with business rows matching Gold / attempted supported cases.
- **SQL Semantic Accuracy** = independently audited PASS cases / attempted supported cases. Missing, duplicate, invalid, or unresolved audit records do not pass; audit coverage and unresolved counts are reported separately.
- **Independent Semantic Audit Accuracy** = audit PASS / determinate audit decisions (PASS + FAIL). It is `NOT MEASURABLE` when no determinate audit exists.
- **Independent Semantic Audit Coverage** = determinate audit decisions / attempted supported cases.
- **Business Result Accuracy** = executed supported cases whose projected columns and row values match the case contract and Gold / executed supported cases. This metric does not establish SQL semantic correctness by itself.
- **False Clarification/Abstention Rate** = supported cases incorrectly clarified or abstained / attempted supported cases.
- **Supported Noncompletion Rate** = supported attempts without a successful semantic execution / attempted supported cases. This includes validation and provider failures, which are separately classified.
- **Validation-Blocked Supported Rate** = supported attempts blocked by SQL/semantic validation / attempted supported cases.
- **Repair Recovery** = end-to-end successful cases that used repair / attempted supported cases that used repair.

For unsupported (`clarify` or `abstain_without_query`) cases, **Valid Clarification/Abstention Rate** is valid safe outcomes / attempted unsupported cases. A malformed clarification, provider failure, or SQL execution is not a valid unsupported outcome. Provider/network failures are reported separately and are not relabeled semantic refusals. Unsafe executions must remain zero.

All rates report exact numerator and denominator. The scorer's conservative SQL Semantic Accuracy treats unresolved audit decisions as non-passes for that metric; the separate audit accuracy, coverage, and unresolved fields distinguish a failed audit from missing evidence.

## Independent SQL audit linkage

An audit record must name the case, auditor ID/version, decision (`PASS`, `FAIL`, `REVIEW_REQUIRED`, or `INDETERMINATE`), and non-empty evidence. It is linked to SHA-256 values for the exact SQL text, SQL parameters, case contract, and full case set. Missing/duplicate records or any hash/parameter mismatch produce `INDETERMINATE`. The Agent's `sql_semantic_valid` boolean is not trusted by the v3.1 scorer.

The linkage protects against accidentally scoring an audit for different inputs. It does not authenticate the auditor, prove reviewer independence, or replace two independent human reviews and adjudication. Those are freeze gates.

The scorer also checks explicit `ORDER BY`/tie-break and TOP-N structure conservatively with SQLGlot. This AST check is a narrow guard, not a complete semantic audit. Unsupported expressions require review; it does not convert a structural pass into a full SQL semantic PASS.

## Result order and ranking

Business row-multiset comparison ignores output sequence when `output_contract.ordered` is false. That does not remove a query's semantic ranking obligation. For example, B40-005 returns one TOP-1 row, so row sequence is irrelevant while correct rank keys, tie-break, and `LIMIT 1` determine which row must be selected. Seven other executable cases explicitly require ordered result rows; v3.1 checks eight ranking/TOP-N obligations in total.

## Reference generation and mutation probes

Before generation or mutation execution, verify the allowlisted frozen analytics database, read-only role, frozen data fingerprint, and case/Gold hashes. A mismatch stops execution. Use only the approved repository executor. Preserve every run in a new immutable versioned path; never replace historical v3 results. SQL Agent calls and held-out execution are forbidden during reference or mutation runs.

Mutation result detection excludes invalid probes and reports valid observationally equivalent mutations separately. Join, fanout, and population-validator detection are separate diagnostics, not additions to the result-based rate. A mutation that returns the same result on this frozen data is not counted as detected by output comparison.

## Freeze and execution gates

Freeze requires independent reviews of the exact case, Gold SQL, and result hashes; adjudication; approved read-only reference provenance; complete test evidence; and an immutable freeze manifest. The 40-case Agent run must not occur before the cohort is independently reviewed and frozen. Draft readiness for review is not authorization to execute the held-out cohort.
