# SQL Agent 40-case benchmark report

- Scorer/protocol: 3.3.0 / 3.3.0
- Application revision: 8649a7eb3576f8b8d3b68a8377fb2b688c6eb31b
- Harness revision: 8649a7eb3576f8b8d3b68a8377fb2b688c6eb31b
- Database fingerprint: dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028
- Observed cases: 40/40

## Outcome counts

- Case statuses: {"INTERRUPTED": 0, "NOT RUN": 0, "clarification_required": 8, "executed": 27, "executed_empty": 0, "failed": 4, "provider_error": 0, "unsupported": 1}
- Business E2E decisions: {"FAIL": 15, "PASS": 14, "REVIEW_REQUIRED": 1}
- SQL semantic audit decisions: {"FAIL": 5, "INDETERMINATE": 3, "PASS": 22, "REVIEW_REQUIRED": 0}
- Provider calls: {"approved_repository_execution": 28, "general_sql_generation": 53, "local_codex_fallback_calls": 0, "provider_fallback_calls": 0, "repository_execution": 29, "repository_execution_attempts": 29, "schema_discovery": 40, "schema_selector_attempts": 40, "sql_repair": 17, "unverified_repository_execution": 1}
- Provider call records: 61; calls reporting token usage: 61; token totals: {"input_tokens": 179750, "output_tokens": 14953, "total_tokens": 194703}; cost: NOT REPORTED
- Case latency (ms): {"median_ms": 9986.565, "observed_cases": 40, "p95_ms": 33530.658, "total_ms": 538302.827}

| Metric | Numerator | Denominator | Value / status |
|---|---:|---:|---|
| supported_business_end_to_end_accuracy | 14 | 30 | 0.4667 |
| sql_semantic_accuracy | 22 | 30 | 0.7333 |
| business_result_accuracy | 16 | 26 | 0.6154 |
| supported_execution_success | 26 | 30 | 0.8667 |
| valid_clarification_abstention | 6 | 10 | 0.6000 |
| false_clarification_abstention | 2 | 30 | 0.0667 |
| supported_noncompletion | 9 | 30 | 0.3000 |
| validation_blocked_supported | 1 | 30 | 0.0333 |
| repair_recovery | 0 | 0 |  |
| overall_task_success_rate | 20 | 40 | 0.5000 |
| strict_result_exact_match_optional | 6 | 30 | 0.2000 |
| schema_selector_raw_recall_at_5 | 41 | 41 | 1.0000 |
| independent_semantic_audit_accuracy | 22 | 27 | 0.8148 |
| independent_semantic_audit_coverage | 27 | 30 | 0.9000 |
| output_contract_compliance | 17 | 26 | 0.6538 |
| business_end_to_end_accuracy | 14 | 30 | 0.4667 |

## Per-case decisions

| Case | Expected | Status | Semantic audit | Business result | E2E |
|---|---|---|---|---|---|
| B40-001 | execute | executed | PASS | FAIL | FAIL |
| B40-002 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-003 | execute | executed | PASS | FAIL | FAIL |
| B40-004 | execute | executed | PASS | FAIL | FAIL |
| B40-005 | execute | failed | PASS | REVIEW_REQUIRED | FAIL |
| B40-006 | execute | executed | PASS | PASS | PASS |
| B40-007 | execute | executed | PASS | PASS | PASS |
| B40-008 | execute | executed | PASS | PASS | PASS |
| B40-009 | execute | failed | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-010 | execute | executed | PASS | PASS | PASS |
| B40-011 | execute | executed | PASS | PASS | PASS |
| B40-012 | execute | executed | PASS | PASS | PASS |
| B40-013 | execute | executed | FAIL | PASS | FAIL |
| B40-014 | execute | executed | FAIL | FAIL | FAIL |
| B40-015 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-016 | execute | executed | PASS | PASS | PASS |
| B40-017 | execute | executed | PASS | PASS | PASS |
| B40-018 | execute | executed | PASS | PASS | PASS |
| B40-019 | execute | executed | PASS | PASS | PASS |
| B40-020 | execute | executed | PASS | PASS | PASS |
| B40-021 | execute | executed | FAIL | FAIL | FAIL |
| B40-022 | execute | executed | PASS | FAIL | FAIL |
| B40-023 | execute | executed | PASS | FAIL | FAIL |
| B40-024 | execute | executed | PASS | PASS | PASS |
| B40-025 | execute | executed | FAIL | FAIL | FAIL |
| B40-026 | execute | executed | PASS | FAIL | FAIL |
| B40-027 | execute | executed | PASS | PASS | PASS |
| B40-028 | execute | executed | FAIL | FAIL | FAIL |
| B40-029 | execute | executed | PASS | PASS | PASS |
| B40-030 | execute | executed | PASS | PASS | REVIEW_REQUIRED |
| B40-031 | clarify | executed | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-032 | clarify | failed | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-033 | clarify | unsupported | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-034 | clarify | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-035 | clarify | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-036 | abstain_without_query | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-037 | abstain_without_query | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-038 | abstain_without_query | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-039 | abstain_without_query | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-040 | abstain_without_query | failed | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |

## Scoring input hashes

- `case_set_canonical_sha256`: `36dbd0876167fccb954923dd4ad2f9961a31e6fd05e8d76ec5f99fecf4a012ce`
- `cases_sha256`: `f5030b254f81d237b73b50ef491df583cd0076f4c98a44958c6612afdb01a625`
- `gold_reference_sha256`: `33e80eee02f59aa8140b725d233ee209ba6e5cd68a3241329f220e1e67700f84`
- `output_safety_audit_sha256`: `c75d6b23394d2126091826715e1713f80ccc782bbc913ed47418141c6305afb6`
- `raw_observations_sha256`: `0bee923061578cf0fc718b92fc4ee45391aa6ee103b93d172aba7622e8edf6e8`
- `scorer_sha256`: `09736cff9ea4cb5edf40e470a0c1692c40b61f57e290e2384493e2f60c2a68f4`
- `semantic_audit_sha256`: `460c3f00dfa47e60c35c49afc076d879faef7863521b754ef0abb77b7b6c6272`
