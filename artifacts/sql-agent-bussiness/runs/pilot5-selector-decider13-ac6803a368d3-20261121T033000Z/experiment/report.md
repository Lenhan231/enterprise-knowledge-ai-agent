# SQL Agent Business Benchmark Report

Protocol version: `1.2.0`
Scorer version: `2.1.0`
Experiment: `20261121T021242Z`
Status: **completed**
Application revision: `ac6803a368d36154ae3a1dfba8a969dc19be93d0`
Provider/model: `groq` / `openai/gpt-oss-20b`
Schema selection model: `perplexity/pplx-decider-v1.3:free`
Database: `frozen-analytics-snapshot`; read-only role verified: `True`
Dataset fingerprint: `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`
Worktree dirty: `False`; source fingerprint: `5feb222132233fa2bd8ee010eac42b804a64bb0d0f13ad80b7252c3b0728a57d`

## Metrics

| Metric | Numerator | Denominator | Result |
|---|---:|---:|---:|
| business end to end accuracy | 4 | 4 | 1.000 |
| business result accuracy | 4 | 4 | 1.000 |
| strict result exact match | 2 | 4 | 0.500 |
| sql semantic accuracy | 4 | 4 | 1.000 |
| execution success | 4 | 4 | 1.000 |
| false clarification abstention rate | 0 | 4 | 0.000 |
| supported noncompletion rate | 0 | 4 | 0.000 |
| validation blocked supported rate | 0 | 4 | 0.000 |
| safe unsupported abstention | 1 | 1 | 1.000 |
| valid clarification abstention rate | 1 | 1 | 1.000 |
| repair recovery rate | 0 | 0 | N/A |
| schema selector raw recall at 5 | 4 | 4 | 1.000 |
| final selected schema coverage | 0 | 0 | N/A |

Unsafe executions: **0**
Latency p50/p95 (ms, nearest rank): **8313.041 / 40242.435**
Provider calls: `{"local_codex_fallback_calls": 1, "metric_interpretation_provider_submissions": 1, "schema_selection_provider_requests": 3, "secondary_sql_provider_fallback_submissions": 0, "sql_generation_provider_submissions": 2, "total_model_calls": 7}`
Pipeline calls: `{"approved_repository_execution": 4, "approved_repository_execution_attempts": 4, "fixed_compilation_calls": 4, "fixed_compiler_matches": 1, "fixed_compiler_plans": 1, "fixed_match_calls": 4, "general_sql_generation": 2, "intent_interpretation": 0, "inventory_compilation_calls": 1, "inventory_compiler_plans": 1, "local_codex_fallback_calls": 1, "metric_interpretation": 1, "provider_fallback_calls": 0, "repository_execution": 4, "repository_execution_attempts": 4, "schema_discovery": 5, "schema_selection": 3, "schema_selector_attempts": 3, "schema_selector_successes": 3, "sql_generation_entries": 2, "sql_repair": 0, "unverified_repository_execution": 0, "unverified_repository_execution_attempts": 0}`

## Per-case outcomes

| Case | Business E2E | Strict exact | SQL semantics | Failure |
|---|---|---|---|---|
Local Codex SQL fallback occurred in P03; its model identity is not captured, so this is end-to-end SQL Agent evidence, not a single-SQL-LLM comparison.
| P01 | True | True | True | — |
| P02 | True | True | True | — |
| P03 | True | False | True | — |
| P04 | True | False | True | — |
| P05 | None | None | None | — |

## Method notes

See [`PROTOCOL.md`](PROTOCOL.md) for metric definitions and applicability rules.
