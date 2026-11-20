# SQL Agent Business Benchmark Report

Experiment: `sql-agent-business-pilot5-rerun-20261120`
Status: **NOT_RUN**
Application revision: `d16f013102b90ba3aa58692bff40caa99bb932ff`

## Metrics

| Metric | Numerator | Denominator | Result |
|---|---:|---:|---:|
| business end to end accuracy | 0 | 0 | N/A |
| business result accuracy | 0 | 0 | N/A |
| strict result exact match | 0 | 0 | N/A |
| sql semantic accuracy | 0 | 0 | N/A |
| execution success | 0 | 0 | N/A |
| false refusal rate | 0 | 0 | N/A |
| safe unsupported abstention | 0 | 0 | N/A |
| valid clarification abstention rate | 0 | 0 | N/A |
| repair recovery rate | 0 | 0 | N/A |
| jev table recall at 5 | 0 | 0 | N/A |
| final selected schema coverage | 0 | 0 | N/A |

Unsafe executions: **0**
Latency p50/p95 (ms, nearest rank): **None / None**
Provider calls: `{"jev_requests": 0, "local_codex_fallback_calls": 0, "metric_interpretation_provider_submissions": 0, "secondary_sql_provider_fallback_submissions": 0, "sql_generation_provider_submissions": 0, "total_model_calls": 0}`
Pipeline calls: `{}`

## Per-case outcomes

| Case | Business E2E | Strict exact | SQL semantics | Failure |
|---|---|---|---|---|
| P01 | None | None | None | environment_blocker |
| P02 | None | None | None | environment_blocker |
| P03 | None | None | None | environment_blocker |
| P04 | None | None | None | environment_blocker |
| P05 | None | None | None | environment_blocker |

## Method notes

See [`PROTOCOL.md`](PROTOCOL.md) for metric definitions and applicability rules.

## Execution status

No fresh SQL Agent benchmark case was executed. All fresh-run quality and latency metrics are N/A.
Blocker: NOT RUN: SQL_BENCHMARK_DATABASE_URL is not configured; the benchmark will not reuse ANALYTICS_DATABASE_URL. No benchmark case, gold reference query, or provider call was executed.
JEV diagnostic: FAILED; HTTP 402; recall@5 is not measurable.
JEV diagnostic detail: Insufficient credits; the OpenRouter account never purchased credits. JEV recall@5 is not measurable.

## Historical trace limitation

Original report states full provider prompts and raw traces are retained locally outside the repository. They are not present in this workspace, so original attempts/calls cannot be independently reconstructed from source traces.

## Artifact verification

Offline suite: **PASS** (34 passed, 0 failed, 0 skipped).
Command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run python -m unittest discover -s artifacts/sql-agent-bussiness/tests -v`
Fresh pilot execution: **NOT RUN**.
Database preflight: **NOT RUN** — SQL_BENCHMARK_DATABASE_URL is not configured; ANALYTICS_DATABASE_URL was not reused.

## Historical pilot (preserved; not rescored)

These are the original report's figures from its original application revision. They are not a controlled before/after comparison with this fresh-run status.

| Historical metric | Result |
|---|---:|
| Strict end-to-end accuracy | 1/4 |
| Business-value accuracy | 2/4 |
| SQL semantic contract accuracy | 3/4 |
| Approved execution acceptance | 3/4 |
| Safe unsupported abstention | 1/1 |
| JEV availability | 0/4; recall@5 not measurable |
| Bounded repair recovery | 0/1 |
| End-to-end latency | p50 8.19 s; p95 14.85 s |
