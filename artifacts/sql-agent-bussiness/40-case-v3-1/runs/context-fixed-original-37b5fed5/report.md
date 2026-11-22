# SQL Agent 40-case benchmark report

- Scorer/protocol: 3.3.0 / 3.3.0
- Application revision: 37b5fed55a45fc30a5e46376e9e41d0abb6bb17f
- Harness revision: 659710ad607127fc79006b83a5cebe2a9854c733
- Database fingerprint: dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028
- Observed cases: 40/40

## Outcome counts

- Case statuses: {"INTERRUPTED": 0, "NOT RUN": 0, "clarification_required": 20, "executed": 15, "executed_empty": 0, "failed": 4, "provider_error": 0, "unsupported": 1}
- Business E2E decisions: {"FAIL": 23, "PASS": 7, "REVIEW_REQUIRED": 0}
- SQL semantic audit decisions: {"FAIL": 5, "INDETERMINATE": 14, "PASS": 11, "REVIEW_REQUIRED": 0}
- Provider calls: {"approved_repository_execution": 17, "general_sql_generation": 62, "local_codex_fallback_calls": 8, "provider_fallback_calls": 31, "repository_execution": 17, "repository_execution_attempts": 17, "schema_discovery": 40, "schema_selector_attempts": 40, "sql_repair": 7, "unverified_repository_execution": 0}
- Provider call records: 70; calls reporting token usage: 70; token totals: {"input_tokens": 90983, "output_tokens": 5033, "total_tokens": 96016}; cost: NOT REPORTED
- Case latency (ms): {"median_ms": 8657.287, "observed_cases": 40, "p95_ms": 28734.298, "total_ms": 459982.889}

| Metric | Numerator | Denominator | Value / status |
|---|---:|---:|---|
| supported_business_end_to_end_accuracy | 7 | 30 | 0.2333 |
| sql_semantic_accuracy | 11 | 30 | 0.3667 |
| business_result_accuracy | 9 | 15 | 0.6000 |
| supported_execution_success | 15 | 30 | 0.5000 |
| valid_clarification_abstention | 9 | 10 | 0.9000 |
| false_clarification_abstention | 11 | 30 | 0.3667 |
| supported_noncompletion | 19 | 30 | 0.6333 |
| validation_blocked_supported | 10 | 30 | 0.3333 |
| repair_recovery | 0 | 0 |  |
| overall_task_success_rate | 16 | 40 | 0.4000 |
| strict_result_exact_match_optional | 2 | 30 | 0.0667 |
| schema_selector_raw_recall_at_5 | 41 | 41 | 1.0000 |
| independent_semantic_audit_accuracy | 11 | 16 | 0.6875 |
| independent_semantic_audit_coverage | 16 | 30 | 0.5333 |
| output_contract_compliance | 11 | 15 | 0.7333 |
| business_end_to_end_accuracy | 7 | 30 | 0.2333 |

## Per-case decisions

| Case | Expected | Status | Semantic audit | Business result | E2E |
|---|---|---|---|---|---|
| B40-001 | execute | executed | PASS | FAIL | FAIL |
| B40-002 | execute | executed | PASS | FAIL | FAIL |
| B40-003 | execute | executed | PASS | FAIL | FAIL |
| B40-004 | execute | executed | PASS | FAIL | FAIL |
| B40-005 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-006 | execute | executed | PASS | PASS | PASS |
| B40-007 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-008 | execute | executed | PASS | PASS | PASS |
| B40-009 | execute | failed | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-010 | execute | executed | PASS | PASS | PASS |
| B40-011 | execute | failed | FAIL | REVIEW_REQUIRED | FAIL |
| B40-012 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-013 | execute | executed | FAIL | PASS | FAIL |
| B40-014 | execute | failed | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-015 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-016 | execute | executed | PASS | PASS | PASS |
| B40-017 | execute | executed | PASS | PASS | PASS |
| B40-018 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-019 | execute | executed | FAIL | PASS | FAIL |
| B40-020 | execute | executed | PASS | PASS | PASS |
| B40-021 | execute | executed | FAIL | FAIL | FAIL |
| B40-022 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-023 | execute | executed | FAIL | FAIL | FAIL |
| B40-024 | execute | executed | PASS | PASS | PASS |
| B40-025 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-026 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-027 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-028 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-029 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-030 | execute | failed | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-031 | clarify | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-032 | clarify | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-033 | clarify | unsupported | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-034 | clarify | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-035 | clarify | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-036 | abstain_without_query | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-037 | abstain_without_query | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-038 | abstain_without_query | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-039 | abstain_without_query | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-040 | abstain_without_query | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |

## Scoring input hashes

- `case_set_canonical_sha256`: `36dbd0876167fccb954923dd4ad2f9961a31e6fd05e8d76ec5f99fecf4a012ce`
- `cases_sha256`: `f5030b254f81d237b73b50ef491df583cd0076f4c98a44958c6612afdb01a625`
- `gold_reference_sha256`: `33e80eee02f59aa8140b725d233ee209ba6e5cd68a3241329f220e1e67700f84`
- `output_safety_audit_sha256`: `7e83063e75a25e2c648c409526b6212aec818f2a5d61acd67f9323c154691edb`
- `raw_observations_sha256`: `3a4cfc293a9f221ba5b35042dbdb2be0dbe40ac1f5f32465c45d43f63ce4c7bf`
- `scorer_sha256`: `09736cff9ea4cb5edf40e470a0c1692c40b61f57e290e2384493e2f60c2a68f4`
- `semantic_audit_sha256`: `e96df41a517e3edbded25032991765daedeb9c50de1760425b66883e65a1c0ed`
