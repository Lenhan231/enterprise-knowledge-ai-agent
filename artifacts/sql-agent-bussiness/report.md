# SQL Agent Business Benchmark Report

Experiment: `sql-agent-business-pilot5-rerun-20261120`
Status: **NOT_RUN**
Application revision: `ca86bd6f9d22810fa50f4efc394f269a5a0f10ae`

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
Command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main/.venv/bin/python -m unittest discover -s artifacts/sql-agent-bussiness/tests -v`
Fresh pilot execution: **NOT RUN**.
Database preflight: **NOT RUN** — SQL_BENCHMARK_DATABASE_URL is not configured; ANALYTICS_DATABASE_URL was not reused.

## SQL semantic regression verification

At application revision `ca86bd6f9d22810fa50f4efc394f269a5a0f10ae`, local SQL regressions passed using Python 3.11.16:

| Suite | Command | Passed | Failed | Skipped |
|---|---|---:|---:|---:|
| SQL regressions | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main/.venv/bin/python -m unittest discover -s tests/sql -p 'test_sql_*.py' -v` | 382 | 0 | 10 |
| Inventory regressions | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main/.venv/bin/python -m unittest discover -s tests -p 'test_inventory*.py' -v` | 73 | 0 | 3 |
| Benchmark tooling | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main/.venv/bin/python -m unittest discover -s artifacts/sql-agent-bussiness/tests -v` | 34 | 0 | 0 |

The P02 regression proves a missing delivered-order filter is repaired before execution and remains rejected after the bounded repair budget is exhausted. The P03 regression proves `return product_id` is treated as an output instruction, a wrong `returns.return_quantity` plan is repaired, and only the corrected `order_items.quantity` query reaches the repository. These are code-level regression results, not fresh model-accuracy measurements. The SQL benchmark runner's source manifest now hashes the query-intent, population, ranking and assistant validation modules used by these checks.

Syntax compilation and `git diff --check`: **PASS**. Tests used local fixtures and mocks; no SQL database query or model provider call was made.

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
