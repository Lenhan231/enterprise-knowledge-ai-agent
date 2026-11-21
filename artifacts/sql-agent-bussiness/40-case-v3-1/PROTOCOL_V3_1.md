# SQL Agent benchmark v3.1 case set / v3.3 scoring protocol

This scoring protocol applies to `cases_v3_1_draft.json`, `gold_sql_v3_1_draft.json`, and their versioned v3.1 references. Scorer/protocol v3.3.0 retains v3.2 result matching while making Business End-to-End Accuracy business-centric. It does not change the case set, Gold SQL, reference rows, historical v3 artifacts, or previous scores. The cohort remains a draft; adjudication and freeze are pending.

## Attempt and metric policy

Only attempted cases enter quality denominators. Explicit `NOT RUN` cases are excluded; a zero denominator is reported as `NOT MEASURABLE`. Each metric reports its exact numerator and denominator.

For supported (`expected_behavior=execute`) cases:

- **Business End-to-End Accuracy** = successfully executed supported cases with a linked independent SQL audit `PASS`, Business Result Accuracy `PASS`, runner security validation `PASS`, zero unsafe executions, and all essential output requirements satisfied / attempted supported cases. Column order, approved aliases, and row order for unordered cases are harmless formatting deviations. If Output Contract Compliance fails only because of unapproved extra columns, E2E may still pass only when every extra column has one valid linked safety audit with decision `PASS`. Any material contract violation fails E2E; missing, ambiguous, or stale safety evidence is `REVIEW_REQUIRED`, not a pass or a fail.
- **SQL Semantic Accuracy** = linked independent audit `PASS` decisions / attempted supported cases. Missing, duplicate, invalid, or unresolved audit records do not pass; audit coverage and unresolved counts are separate.
- **Independent Semantic Audit Accuracy** = audit `PASS` / determinate audit decisions (`PASS` + `FAIL`). It is `NOT MEASURABLE` when no determinate audit exists.
- **Independent Semantic Audit Coverage** = determinate audit decisions / attempted supported cases.
- **Business Result Accuracy** = executed supported cases whose canonical required-field values and rows match Gold / executed supported cases. Column order and unapproved extra output columns do not change this metric. This metric does not establish SQL semantic correctness by itself.
- **Output Contract Compliance** = executed supported cases that satisfy required output columns, approved aliases/provenance, row limits, and declared ordering / executed supported cases. Column position is ignored. Unapproved extra columns fail this metric.
- **False Clarification/Abstention Rate** = supported cases incorrectly clarified or abstained / attempted supported cases.
- **Supported Noncompletion Rate** = supported attempts without a successful semantic execution / attempted supported cases. This includes validation and provider failures, which are separately classified.
- **Validation-Blocked Supported Rate** = supported attempts blocked by SQL/semantic validation / attempted supported cases.
- **Repair Recovery** = end-to-end successful cases that used repair / attempted supported cases that used repair.

For unsupported (`clarify` or `abstain_without_query`) cases, **Valid Clarification/Abstention Rate** is valid safe outcomes / attempted unsupported cases. A malformed clarification, provider failure, or SQL execution is not a valid unsupported outcome. Provider/network failures are reported separately and are not relabeled semantic refusals. Unsafe executions must remain zero.

E2E reason codes and sub-decisions are emitted per case. Missing security-validation evidence is `REVIEW_REQUIRED`; an explicit failed security check or unsafe execution is `FAIL`. These checks do not infer safety from a model-provided flag.

## Canonical columns and row comparison

Canonical output alignment accepts case-insensitive exact names, case-specific `column_aliases`, and an otherwise unknown output label only when SQLGlot can show the same normalized projection expression with resolved source-column lineage in the Gold and observed SQL. Column position is ignored. No fuzzy string matching is used. If multiple canonical fields are plausible, the comparison is `REVIEW_REQUIRED`; an unrecognized extra column instead fails output-contract compliance.

Projection lineage is deliberately narrow. It does not prove filters, joins, aggregation, grouping, snapshot selection, population, NULL semantics, grain, or ranking. `COUNT(*)` and other projections without source-column lineage cannot establish a new alias by themselves. SQLGlot structural checks are not a substitute for an independent SQL semantic audit.

Business rows use `business_key_columns` only when the case explicitly declares them. Gold keys must be non-null and unique; invalid Gold keys require review. Duplicate or NULL observed keys fail business accuracy and the key-uniqueness output requirement. Without an explicit key, the scorer uses maximum bipartite multiset matching, preserving duplicate rows and handling overlapping decimal tolerances without greedy mispairing. `NULL` matches only `NULL`; it is never coerced to zero. Decimal values are compared with the case's absolute/relative tolerance, while identifiers and count columns remain exact.

Business Result Accuracy compares row content independent of order. For a case with `output_contract.ordered=true`, Output Contract Compliance separately requires the ordered rows to match Gold when the row multiset matches. If business rows differ, the ordered output is `REVIEW_REQUIRED` because its sequence cannot be independently assessed from mismatched values. Row limits and TOP-N result-count limits are checked separately. Result correctness never overrides an independent SQL audit failure or review requirement.

## Additional-column safety policy

Unapproved extra columns continue to fail Output Contract Compliance. They do not change Business Result Accuracy. To permit Business E2E when extras are the only contract deviation, each extra column needs a separately supplied independent safety decision bound to the exact case, case set, SQL, parameters, full observed result, and extra-column values. The decision must include reviewer ID/version, a schema/security policy reference and SHA-256, evidence for all checks below, and `decision: PASS`:

- required business fields and values are unchanged;
- row cardinality, grain, population, metric, and aggregation are unchanged;
- the extra information does not distort the requested meaning;
- it contains no sensitive data and is authorized by the cited access policy.

Missing or invalid linkage yields `REVIEW_REQUIRED`; an explicit failed check yields `FAIL`. The scorer performs the row-cardinality and required-business-value comparisons itself. It does not use an LLM judge. Its records are plain JSON with `authenticated: false`; reviewer identity, independence, policy contents, and the truth of reviewer evidence are not cryptographically verified. Do not create or infer review decisions from Agent output.

Keep output safety decisions in a separate reviewer JSON file, then export them to a new experiment file (the CLI uses exclusive creation):

```bash
uv run --locked --project . python artifacts/sql-agent-bussiness/40-case-v3-1/output_safety_audit_v3_3.py \
  --cases artifacts/sql-agent-bussiness/40-case-v3-1/cases_v3_1_draft.json \
  --experiment artifacts/sql-agent-bussiness/40-case-v3-1/experiment.json \
  --decisions artifacts/sql-agent-bussiness/40-case-v3-1/output_safety_decisions.json \
  --output artifacts/sql-agent-bussiness/40-case-v3-1/experiment_with_output_safety.json
```

## Independent SQL audit linkage

An SQL semantic audit record names the case, auditor ID/version, decision (`PASS`, `FAIL`, `REVIEW_REQUIRED`, or `INDETERMINATE`), and non-empty evidence. It links SHA-256 values for the exact SQL text, SQL parameters, case contract, and full case set. Missing/duplicate records or any hash/parameter mismatch produce `INDETERMINATE`. The Agent's `sql_semantic_valid` boolean is not trusted. This audit is distinct from the additional-output safety review above.

`semantic_audit_v3_1.py` exports reviewer decisions supplied in a separate JSON file:

```bash
uv run --locked --project . python artifacts/sql-agent-bussiness/40-case-v3-1/semantic_audit_v3_1.py \
  --cases artifacts/sql-agent-bussiness/40-case-v3-1/cases_v3_1_draft.json \
  --experiment artifacts/sql-agent-bussiness/40-case-v3-1/experiment.json \
  --decisions artifacts/sql-agent-bussiness/40-case-v3-1/reviewer_decisions.json \
  --output artifacts/sql-agent-bussiness/40-case-v3-1/experiment_with_audits.json
```

The decisions file carries `format_version: "sql-semantic-audit-decisions.v1"`, the canonical `case_set_sha256`, `auditor_id`, `auditor_version`, and a `decisions` list with `case_id`, `decision`, and non-empty `evidence`. The exporter rejects stale case-set hashes, duplicate/unknown/non-execute case IDs, missing SQL, invalid decisions, and empty evidence. It records export time and leaves unreviewed SQL case IDs visible. Output is created exclusively so an existing experiment is never overwritten.

The export is plain JSON: it links the recorded decision to exact inputs but does not authenticate the auditor, prove reviewer independence, or create a human review. Do not synthesize decisions. The `recorded_at_utc` value is export time, not the original review time. Human review and adjudication remain freeze gates.

The scorer also checks explicit `ORDER BY`/tie-break and TOP-N structure conservatively. A structural pass is not full SQL semantic approval; unsupported expressions require review.

## Reference generation, mutations, and freeze

Before generation or mutation execution, verify the allowlisted frozen analytics database, read-only role, frozen data fingerprint, and case/Gold hashes. A mismatch stops execution. Use only the approved repository executor. Preserve every run in a new immutable versioned path; never replace historical v3 results. SQL Agent calls and held-out execution are forbidden during reference or mutation runs.

Mutation result detection excludes invalid probes and reports valid observationally equivalent mutations separately. Join, fanout, and population-validator detection are separate diagnostics, not additions to the result-based rate. A mutation that returns the same result on this frozen data is not counted as detected by output comparison.

Freeze requires independent reviews of the exact case, Gold SQL, and result hashes; adjudication; approved read-only reference provenance; complete test evidence; and an immutable freeze manifest. The 40-case Agent run must not occur before the cohort is independently reviewed and frozen. Draft readiness for review is not authorization to execute the held-out cohort.
