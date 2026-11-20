# SQL Agent Business Benchmark Report

Experiment: `20261120T183120Z`
Status: **completed**
Application revision: `e6f3b90915bbd5359bff6966c7403fc1b6d5f0b5`
Provider/model: `cloudflare` / `@cf/openai/gpt-oss-20b`
Database: `frozen-analytics-snapshot`; read-only role verified: `True`
Dataset fingerprint: `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`
Worktree dirty: `True`; source fingerprint: `1d1f6c83d3ef8c283d15b9a91a531b29c94eb3bdbe5d35edc951a0d7a5d92015`

## Metrics

| Metric | Numerator | Denominator | Result |
|---|---:|---:|---:|
| business end to end accuracy | 4 | 4 | 1.000 |
| business result accuracy | 4 | 4 | 1.000 |
| strict result exact match | 2 | 4 | 0.500 |
| sql semantic accuracy | 4 | 4 | 1.000 |
| execution success | 4 | 4 | 1.000 |
| false refusal rate | 0 | 4 | 0.000 |
| safe unsupported abstention | 1 | 1 | 1.000 |
| valid clarification abstention rate | 1 | 1 | 1.000 |
| repair recovery rate | 0 | 0 | N/A |
| jev table recall at 5 | 0 | 0 | N/A |
| final selected schema coverage | 0 | 0 | N/A |

Unsafe executions: **0**
Latency p50/p95 (ms, nearest rank): **6802.847 / 40447.753**
Provider calls: `{"jev_requests": 4, "local_codex_fallback_calls": 0, "metric_interpretation_provider_submissions": 2, "secondary_sql_provider_fallback_submissions": 1, "sql_generation_provider_submissions": 4, "total_model_calls": 10}`
Pipeline calls: `{"approved_repository_execution": 4, "approved_repository_execution_attempts": 4, "fixed_compilation_calls": 5, "fixed_compiler_matches": 1, "fixed_compiler_plans": 1, "fixed_match_calls": 5, "general_sql_generation": 4, "intent_interpretation": 0, "inventory_compilation_calls": 1, "inventory_compiler_plans": 1, "jev_attempts": 4, "jev_successes": 0, "local_codex_fallback_calls": 0, "metric_interpretation": 2, "provider_fallback_calls": 1, "repository_execution": 4, "repository_execution_attempts": 4, "schema_discovery": 5, "schema_selection": 4, "sql_generation_entries": 3, "sql_repair": 0, "unverified_repository_execution": 0, "unverified_repository_execution_attempts": 0}`

## Per-case outcomes

| Case | Business E2E | Strict exact | SQL semantics | Failure |
|---|---|---|---|---|
| P01 | True | True | True | — |
| P02 | True | True | True | — |
| P03 | True | False | True | — |
| P04 | True | False | True | — |
| P05 | None | None | None | — |

## Method notes

See [`PROTOCOL.md`](PROTOCOL.md) for metric definitions and applicability rules.

JEV availability: **FAILED** (HTTP 402); recall@5 is not measurable.
