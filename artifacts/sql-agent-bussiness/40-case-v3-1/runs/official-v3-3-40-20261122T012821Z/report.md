# SQL Agent 40-case benchmark report

- Scorer/protocol: 3.3.0 / 3.3.0
- Application revision: 37b5fed55a45fc30a5e46376e9e41d0abb6bb17f
- Harness revision: 659710ad607127fc79006b83a5cebe2a9854c733
- Database fingerprint: dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028
- Observed cases: 40/40

## Outcome counts

- Case statuses: {"INTERRUPTED": 0, "NOT RUN": 0, "clarification_required": 14, "executed": 19, "executed_empty": 1, "failed": 5, "provider_error": 0, "unsupported": 1}
- Business E2E decisions: {"FAIL": 20, "PASS": 10, "REVIEW_REQUIRED": 0}
- SQL semantic audit decisions: {"FAIL": 9, "INDETERMINATE": 7, "PASS": 14, "REVIEW_REQUIRED": 0}
- Provider calls: {"approved_repository_execution": 21, "general_sql_generation": 38, "local_codex_fallback_calls": 0, "provider_fallback_calls": 0, "repository_execution": 21, "repository_execution_attempts": 22, "schema_discovery": 40, "schema_selector_attempts": 40, "sql_repair": 10, "unverified_repository_execution": 0}
- Provider call records: 48; calls reporting token usage: 48; token totals: {"input_tokens": 152588, "output_tokens": 9737, "total_tokens": 162325}; cost: NOT REPORTED
- Case latency (ms): {"median_ms": 9333.998, "observed_cases": 40, "p95_ms": 36959.618, "total_ms": 516877.099}

| Metric | Numerator | Denominator | Value / status |
|---|---:|---:|---|
| supported_business_end_to_end_accuracy | 10 | 30 | 0.3333 |
| sql_semantic_accuracy | 14 | 30 | 0.4667 |
| business_result_accuracy | 11 | 20 | 0.5500 |
| supported_execution_success | 20 | 30 | 0.6667 |
| valid_clarification_abstention | 8 | 10 | 0.8000 |
| false_clarification_abstention | 6 | 30 | 0.2000 |
| supported_noncompletion | 16 | 30 | 0.5333 |
| validation_blocked_supported | 7 | 30 | 0.2333 |
| repair_recovery | 0 | 0 |  |
| overall_task_success_rate | 18 | 40 | 0.4500 |
| strict_result_exact_match_optional | 2 | 30 | 0.0667 |
| schema_selector_raw_recall_at_5 | 40 | 40 | 1.0000 |
| independent_semantic_audit_accuracy | 14 | 23 | 0.6087 |
| independent_semantic_audit_coverage | 23 | 30 | 0.7667 |
| output_contract_compliance | 13 | 20 | 0.6500 |
| business_end_to_end_accuracy | 10 | 30 | 0.3333 |

## Per-case decisions

| Case | Expected | Status | Semantic audit | Business result | E2E |
|---|---|---|---|---|---|
| B40-001 | execute | executed | PASS | FAIL | FAIL |
| B40-002 | execute | failed | FAIL | REVIEW_REQUIRED | FAIL |
| B40-003 | execute | executed | PASS | FAIL | FAIL |
| B40-004 | execute | executed | PASS | FAIL | FAIL |
| B40-005 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-006 | execute | executed | PASS | PASS | PASS |
| B40-007 | execute | executed | PASS | PASS | PASS |
| B40-008 | execute | executed | PASS | PASS | PASS |
| B40-009 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
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
| B40-020 | execute | executed | PASS | PASS | PASS |
| B40-021 | execute | executed | FAIL | FAIL | FAIL |
| B40-022 | execute | executed | PASS | FAIL | FAIL |
| B40-023 | execute | executed | FAIL | FAIL | FAIL |
| B40-024 | execute | executed | PASS | PASS | PASS |
| B40-025 | execute | executed | FAIL | FAIL | FAIL |
| B40-026 | execute | failed | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-027 | execute | executed | FAIL | FAIL | FAIL |
| B40-028 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-029 | execute | clarification_required | INDETERMINATE | REVIEW_REQUIRED | FAIL |
| B40-030 | execute | executed_empty | FAIL | REVIEW_REQUIRED | FAIL |
| B40-031 | clarify | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
| B40-032 | clarify | clarification_required | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |
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
- `output_safety_audit_sha256`: `79387f42001e13db8f6f6c239691857bdcf1f40581661917f8e41cbbfc926221`
- `raw_observations_sha256`: `123c26586f0438b35b6152a88a2116da129092645188a0766c2fad191f8d9876`
- `scorer_sha256`: `09736cff9ea4cb5edf40e470a0c1692c40b61f57e290e2384493e2f60c2a68f4`
- `semantic_audit_sha256`: `91fc40f533480d4775e20ecbd10c74b0cc67b874da647a78fc2c2077c8ce3905`
