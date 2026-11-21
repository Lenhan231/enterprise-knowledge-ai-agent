# SQL Agent Business Benchmark Protocol

Protocol version: 3.1.0

Scorer: scorer_v3.py version 3.1.0

Case set: cases_v3_draft.json

Oracle: gold_sql_v3_draft.json and gold_results_v3_provisional.json

## Scope

Evaluate the SQL Agent only. Do not include Knowledge, Auto planning, answer-prose quality, or a second SQL provider as if it were the configured primary model. The 40 cases comprise 30 supported analytical requests, 5 clarification cases, and 5 safe-abstention/security cases. The earlier five-question pilot is development material, not part of the held-out cohort.

The frozen v3 draft revises the v2 question and oracle files. v2 and all of its result artifacts remain unchanged. No SQL Agent was run on a v3 case during preparation.

## Freeze and data requirements

The Commerce source is synthetic competition data. Reference SQL must use the approved read-only repository, allowlisted database host, and verified least-privilege role. The current preparation used the explicitly frozen analytics snapshot. Its preflight fingerprint must equal dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028 before every reference-generation or mutation-probe run. A mismatch stops the run; do not reuse old rows.

Gold SQL is authored from the question and approved schema/metric contract, not from SQL Agent output. Gold rows remain provisional until two independent semantic reviews and adjudication are recorded. The dataset must not be marked FROZEN while any review gate is pending.

## Follow-up evaluation mode

Cases B40-026 through B40-030 use context-conditioned SQL. The adapter supplies the frozen prior user question and only its approved typed semantic context alongside the current user follow-up. It never supplies a prior assistant answer, SQL, parameters, result rows, or Gold data. The SQL Agent receives the context in the request question through its normal SQL mode. This evaluates SQL generation conditioned on explicit context; it does not claim conversational-memory evaluation.

## Metrics

Every rate is emitted as integer numerator, denominator, and value. A zero denominator produces null. Cases explicitly marked NOT RUN are excluded.

| Metric | Numerator | Denominator |
|---|---|---|
| Supported Business End-to-End Accuracy (primary) | Supported case with successful execution, independently valid SQL semantics, and matching business rows | Attempted supported cases |
| SQL Semantic Accuracy | Supported case whose SQL passes the independent semantic contract audit | Attempted supported cases |
| Business Result Accuracy | Executed supported case whose rows match the business result policy | Executed supported cases |
| Supported Execution Success | Supported case with status executed or executed_empty | Attempted supported cases |
| Valid Clarification/Abstention | Unsupported case has a recognized clarify/abstain status, a non-empty string answer, no SQL, and no execution event; choices may be absent or a list of at most three non-empty strings | Attempted unsupported cases |
| False Clarification/Abstention | Supported case clarified, rejected, or abstained without successful execution | Attempted supported cases |
| Supported Noncompletion | Supported case not both executed and semantically valid | Attempted supported cases |
| Validation-Blocked Supported Rate | Supported case blocked by SQL security, schema, semantic validation, or bounded repair exhaustion | Attempted supported cases |
| Repair Recovery | Repaired supported case that ultimately executes with valid semantics and matching business rows | Supported cases with at least one internal repair |
| Overall Task Success Rate (optional) | End-to-end successes plus valid unsupported clarification/abstention | All attempted supported and unsupported cases |
| Strict Result Exact Match (optional diagnostic) | Executed supported case with exact output column list/order, exact rows, and valid SQL semantics | Attempted supported cases |
| Unsafe Execution Count | Execution events without a successful mandatory security boundary | Count; target is zero |
| Provider/Network Failure Count | Attempts ending in provider or network failure | Count; not a semantic refusal |
| Schema Selector Raw Recall@5 | Required tables in successful selector raw top five | Cases with successful selector response; if unavailable, NOT MEASURABLE |
| Latency p50/p95 | Nearest-rank percentiles of end-to-end latency in milliseconds | Attempted cases with a recorded non-negative latency; sample count and attempted denominator are emitted |
| Provider Calls | SQL-generation submissions, metric interpretation submissions, schema-selection requests, and local Codex fallback calls | Counts by stage over attempted cases; secondary SQL provider calls are a subset of SQL-generation submissions |

sql_semantic_valid must come from the independent SQL semantic audit recorded with the observation; missing or false values fail the metric. The Agent's own validated status is not accepted as independent semantic evidence. The scorer reports this input and result comparison separately.

Clarification validity is part of the response contract, not merely the absence of SQL. A malformed answer or choices list does not count as valid abstention. Provider/network failures and validation failures are recorded separately and do not count as valid clarification/abstention.

Strict Result Exact Match is diagnostic and does not affect the primary score. SQL semantic accuracy and unsupported safe handling remain separate; the optional aggregate is named Overall Task Success Rate.

## Business result comparison

Required business columns may use aliases only when listed in a case's column_aliases. Extra provenance columns are accepted only when explicitly listed in allowed_provenance_columns and every observed value equals the frozen expected value. Other extra columns fail business-result accuracy. Numeric tolerances come from the case; IDs, integer counts, and NULL semantics are exact. Ordered contracts compare row order; unordered contracts compare row multisets. NULL never equals zero.

## Mutation probes

Mutations start with independently authored Gold SQL and apply one named semantic change. Only the approved read-only executor may execute a variant. Result-based detection and validation-based rejection are reported separately. A valid mutation with an identical result is observationally equivalent on this snapshot and is not counted as detected. A mutation that fails to parse or violates a separate safety/SQL contract is invalid unless that specific validator rejection was the intended probe.

The earlier v3.0 mutation evidence remains at `mutation_results.json`. Any rerun under protocol 3.1 uses a new `mutation_results_v3_1.json` artifact so the prior evidence is preserved.

Result-Based Mutation Detection Rate is:

valid, bounded mutations whose business results are distinguishable / valid, bounded mutations actually executed

Business semantic-validator detection is reported separately for mutations assigned an explicit semantic-validator oracle. Approved-join and row-limit safety rejections are also reported by validator and are not mixed into result-based detection:

correctly rejected mutations / mutations assigned that validator's rejection oracle

Invalid or unexpected execution failures are excluded from both rates and cause a partial run. The executor's mandatory row bound remains in force: a missing business TOP-N is represented with the repository's maximum safe `LIMIT 200`, not an unbounded query. Do not use SQL string inequality as semantic evidence. Record observational equivalence and data limitations per mutation.

## Reproduction and stop conditions

1. Verify source revision, worktree status, v3 case hash, Gold SQL hash, and preflight fingerprint.
2. Confirm the read-only role and frozen-snapshot acknowledgement.
3. Execute Gold SQL with bound parameters and save a new immutable run artifact.
4. Execute and independently verify the controlled mutation set.
5. Review case wording, SQL, rows, tolerances, clarifications, and mutation results independently.
6. Only after two reviews and adjudication, freeze hashes and allow a separate SQL Agent execution experiment.

Do not run the 40-case SQL Agent cohort during artifact preparation. The 40-case execution gate remains NO until all semantic review, oracle, context, and freeze gates pass.
