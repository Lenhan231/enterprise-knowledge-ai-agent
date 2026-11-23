# SQL Agent 40-case benchmark report

- Scorer/protocol: 3.3.0 / 3.3.0
- Application revision: 37b5fed55a45fc30a5e46376e9e41d0abb6bb17f
- Harness revision: 659710ad607127fc79006b83a5cebe2a9854c733
- Database fingerprint: dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028
- Observed cases: 40/40

## Outcome counts

- Case statuses: {"INTERRUPTED": 0, "NOT RUN": 0, "clarification_required": 15, "executed": 20, "executed_empty": 0, "failed": 4, "provider_error": 0, "unsupported": 1}
- Business E2E decisions: {"FAIL": 21, "PASS": 9, "REVIEW_REQUIRED": 0}
- SQL semantic audit decisions: {"FAIL": 6, "INDETERMINATE": 9, "PASS": 15, "REVIEW_REQUIRED": 0}
- Provider calls: {"approved_repository_execution": 22, "general_sql_generation": 34, "local_codex_fallback_calls": 0, "provider_fallback_calls": 0, "repository_execution": 22, "repository_execution_attempts": 22, "schema_discovery": 40, "schema_selector_attempts": 40, "sql_repair": 9, "unverified_repository_execution": 0}
- Provider call records: 42; calls reporting token usage: 42; token totals: {"input_tokens": 130898, "output_tokens": 9337, "total_tokens": 140235}; cost: NOT REPORTED
- Case latency (ms): {"median_ms": 7714.854, "observed_cases": 40, "p95_ms": 28347.739, "total_ms": 486915.128}

| Metric | Numerator | Denominator | Value / status |
|---|---:|---:|---|
| supported_business_end_to_end_accuracy | 9 | 30 | 0.3000 |
| sql_semantic_accuracy | 15 | 30 | 0.5000 |
| business_result_accuracy | 10 | 19 | 0.5263 |
| supported_execution_success | 19 | 30 | 0.6333 |
| valid_clarification_abstention | 8 | 10 | 0.8000 |
| false_clarification_abstention | 7 | 30 | 0.2333 |
| supported_noncompletion | 15 | 30 | 0.5000 |
| validation_blocked_supported | 9 | 30 | 0.3000 |
| repair_recovery | 0 | 0 |  |
| overall_task_success_rate | 17 | 40 | 0.4250 |
| strict_result_exact_match_optional | 3 | 30 | 0.1000 |
| schema_selector_raw_recall_at_5 | 41 | 41 | 1.0000 |
| independent_semantic_audit_accuracy | 15 | 21 | 0.7143 |
| independent_semantic_audit_coverage | 21 | 30 | 0.7000 |
| output_contract_compliance | 11 | 19 | 0.5789 |
| business_end_to_end_accuracy | 9 | 30 | 0.3000 |

## Per-case decisions

| Case | Expected | Status | Semantic audit | Business result | E2E |
|---|---|---|---|---|---|
| B40-001 | execute | executed | PASS | FAIL | FAIL |
| B40-002 | execute | executed | PASS | FAIL | FAIL |
| B40-003 | execute | executed | PASS | FAIL | FAIL |
| B40-004 | execute | executed | PASS | FAIL | FAIL |
| B40-005 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-006 | execute | executed | PASS | PASS | PASS |
| B40-007 | execute | executed | PASS | PASS | PASS |
| B40-008 | execute | executed | PASS | PASS | PASS |
| B40-009 | execute | failed | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-010 | execute | executed | PASS | PASS | PASS |
| B40-011 | execute | failed | FAIL | REVIEW_REQUIRED | FAIL |
| B40-012 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-013 | execute | executed | FAIL | PASS | FAIL |
| B40-014 | execute | failed | FAIL | REVIEW_REQUIRED | FAIL |
| B40-015 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-016 | execute | executed | PASS | PASS | PASS |
| B40-017 | execute | executed | PASS | PASS | PASS |
| B40-018 | execute | executed | PASS | PASS | PASS |
| B40-019 | execute | executed | PASS | PASS | PASS |
| B40-020 | execute | executed | PASS | FAIL | FAIL |
| B40-021 | execute | executed | FAIL | FAIL | FAIL |
| B40-022 | execute | executed | PASS | FAIL | FAIL |
| B40-023 | execute | executed | FAIL | FAIL | FAIL |
| B40-024 | execute | executed | PASS | PASS | PASS |
| B40-025 | execute | executed | FAIL | FAIL | FAIL |
| B40-026 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-027 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-028 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-029 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-030 | execute | failed | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-031 | clarify | executed | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
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
- `output_safety_audit_sha256`: `8b2874c52ce73c6030a82005924bbc94a78f81e5f67b6a136294443895424adf`
- `raw_observations_sha256`: `3fcd1a55e93ec496ec5d345d3adc404ef9c38237d73e06e4bd30a9bba62f3411`
- `scorer_sha256`: `09736cff9ea4cb5edf40e470a0c1692c40b61f57e290e2384493e2f60c2a68f4`
- `semantic_audit_sha256`: `463adbefee246798320328046e45c3f7994ded335785bf3d4ba03c3635ddcceb`
