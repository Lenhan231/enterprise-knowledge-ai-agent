# SQL Agent Business Benchmark Report

Experiment: `20261120T191013Z`
Status: **completed_with_failures**
Application revision: `8e4abbd1e0a1352c93d747c825c15bf1aff3a1b4`
Provider/model: `cloudflare` / `@cf/openai/gpt-oss-20b`
Database: `frozen-analytics-snapshot`; read-only role verified: `True`
Dataset fingerprint: `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`
Worktree dirty: `False`; source fingerprint: `0d6890689ca5011440a31ebfe3ca69e67a879f977273100c61bc38ba8c2f9571`

## Metrics

| Metric | Numerator | Denominator | Result |
|---|---:|---:|---:|
| business end to end accuracy | 3 | 4 | 0.750 |
| business result accuracy | 3 | 3 | 1.000 |
| strict result exact match | 1 | 4 | 0.250 |
| sql semantic accuracy | 3 | 4 | 0.750 |
| execution success | 3 | 4 | 0.750 |
| false refusal rate | 0 | 4 | 0.000 |
| safe unsupported abstention | 0 | 1 | 0.000 |
| valid clarification abstention rate | 0 | 1 | 0.000 |
| repair recovery rate | 0 | 1 | 0.000 |
| jev table recall at 5 | 0 | 0 | N/A |
| final selected schema coverage | 0 | 0 | N/A |

Unsafe executions: **0**
Latency p50/p95 (ms, nearest rank): **7884.425 / 14957.067**
Provider calls: `{"jev_requests": 4, "local_codex_fallback_calls": 0, "metric_interpretation_provider_submissions": 2, "secondary_sql_provider_fallback_submissions": 1, "sql_generation_provider_submissions": 6, "total_model_calls": 12}`
Pipeline calls: `{"approved_repository_execution": 3, "approved_repository_execution_attempts": 3, "fixed_compilation_calls": 5, "fixed_compiler_matches": 1, "fixed_compiler_plans": 1, "fixed_match_calls": 5, "general_sql_generation": 6, "intent_interpretation": 0, "inventory_compilation_calls": 1, "inventory_compiler_plans": 1, "jev_attempts": 4, "jev_successes": 0, "local_codex_fallback_calls": 0, "metric_interpretation": 2, "provider_fallback_calls": 1, "repository_execution": 3, "repository_execution_attempts": 3, "schema_discovery": 5, "schema_selection": 4, "sql_generation_entries": 5, "sql_repair": 2, "unverified_repository_execution": 0, "unverified_repository_execution_attempts": 0}`

## Per-case outcomes

| Case | Business E2E | Strict exact | SQL semantics | Failure |
|---|---|---|---|---|
| P01 | True | True | True | — |
| P02 | False | False | False | agent_failure |
| P03 | True | False | True | — |
| P04 | True | False | True | — |
| P05 | None | None | None | invalid_unsupported_execution_or_response |

## Method notes

See [`PROTOCOL.md`](PROTOCOL.md) for metric definitions and applicability rules.

JEV availability: **FAILED** (HTTP 402); recall@5 is not measurable.
