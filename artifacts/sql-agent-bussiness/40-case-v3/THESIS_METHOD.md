# Thesis Method: SQL Agent Business Benchmark v3

## Research objective

Measure whether the SQL Agent preserves the business population, metric definition, calendar or snapshot scope, grouping grain, ranking, and requested output, while remaining inside the approved read-only SQL boundary. The unit of future evaluation is the complete SQL Agent path. Knowledge retrieval, Auto orchestration, response prose quality, and model-only claims are outside this cohort.

The v3 draft contains 40 questions: 30 supported analytical requests, 5 clarification requests, and 5 safe-abstention/security requests. The five-question pilot remains a development cohort and is not pooled with v3.

## Dataset revision and source

v3 is based on the v2 draft at commit 60eafaee964a6de48a0c8d13925e3207d5116588. v2 files, provisional result rows, and historical runs are preserved. v3 changes are enumerated in V2_TO_V3_CHANGELOG.md.

The database represents synthetic Commerce competition data. Preparation used the frozen analytics snapshot with fingerprint dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028; the approved read-only role was verified. database_preflight_v3.json stores schema and coverage metadata without credentials. Gold rows are provisional, have zero reviewer approvals, and must not be described as approved ground truth.

## Follow-up condition

B40-026 through B40-030 are evaluated in context-conditioned SQL mode. The adapter places a frozen prior user question and its typed semantic state in the direct SQL request, followed by the current user follow-up. It injects no assistant output, SQL, parameters, or results. Adapter tests verify that the normal SQL request and SQL-generation prompt receive this context. This is not evidence of full conversational-memory behavior; model use of the context remains unmeasured until a separately authorized cohort run.

## Reference creation and safety

Gold SQL was drafted from the question and approved schema/metric contract, without SQL Agent output. Each query is structurally checked for allowed sources, columns, joins, parameter binding, output contract, date scope, grouping/ranking, TOP-N, and read-only execution. Gold SQL and mutation variants use the repository's approved executor and the frozen read-only role. A fingerprint change aborts reference generation.

All 30 Gold SQL references executed successfully as provisional read-only queries on fingerprint `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`. The 28 controlled mutation probes produced 23 result-distinguishable variants out of 26 executed variants (88.46%); three valid variants were observationally equivalent on this snapshot. Two additional mutations were correctly rejected by the approved JOIN safety validators. The delivered-order population validator rejected the missing-delivered-filter mutation (1/1). These probe results measure this mutation set on this database only; they do not establish broad SQL Agent accuracy.

The frozen dataset has specific limits: all return reasons are non-NULL in the reviewed 2023-2025 interval; all selected 2025 shipping fees are non-NULL; and both selected B40-023 snapshots contain the same 97 product IDs. These limits are recorded, not hidden or converted into fabricated edge cases.

## Evaluation metrics

The primary outcome is Supported Business End-to-End Accuracy. It requires successful execution, an independent SQL semantic pass, and business rows matching the provisional oracle. SQL Semantic Accuracy, Business Result Accuracy, Valid Clarification/Abstention, False Clarification/Abstention, Supported Noncompletion, Validation-Blocked Rate, Repair Recovery, Unsafe Execution Count, Schema Selector Raw Recall@5, latency, and provider calls are secondary metrics. A valid clarification needs a non-empty answer, no SQL or execution, and an absent choices field or no more than three non-empty string choices. Exact numerators, denominators, zero-denominator handling, alias/provenance rules, tolerances, and optional Strict Result Exact Match are specified in the adjacent v3 PROTOCOL.md and implemented by scorer_v3.py.

Strict Result Exact Match is an optional diagnostic and does not determine the primary score. Provider/network failure is reported separately from semantic refusal. NOT RUN cases do not enter applicable denominators.

## Approval and execution status

No independent human semantic approvals are recorded. The v3 cohort has not been run through the SQL Agent. Technical preparation is complete enough to begin independent human review; reviewers must consider the recorded observational-equivalence limits and may request versioned corrections. The cohort is not ready for 40-case SQL Agent execution until two independent reviews, adjudication, approved Gold SQL/results, and final freeze hashes are present.
