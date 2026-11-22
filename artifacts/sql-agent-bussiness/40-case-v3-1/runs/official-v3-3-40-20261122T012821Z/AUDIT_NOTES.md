# Official SQL Agent v3.3 run audit notes

Run ID: `20261122T012821Z`

Run status: `completed_with_failures` (40/40 cases attempted)

Application: `37b5fed55a45fc30a5e46376e9e41d0abb6bb17f`

Harness: `659710ad607127fc79006b83a5cebe2a9854c733`

Scorer/protocol: `3.3.0 / 3.3.0`

The frozen case set, Gold SQL, Gold rows, scorer and raw run were not changed. The linked review files assess the observed SQL separately from execution and output shape. SQL semantic decisions were AI-assisted by Codex, are unauthenticated, and are not a substitute for a human audit. The 23 observed SQL statements received 15 reviewer `PASS` and 8 `FAIL` decisions. Seven supported cases returned no SQL and remain indeterminate. The scorer also applies its own conservative ranking check; it therefore changes B40-011 from reviewer `PASS` to effective `FAIL` as described below.

## v3.3 scored results

| Metric | Result |
|---|---:|
| Business end-to-end accuracy | 10/30 (33.3%) |
| SQL semantic accuracy, including scorer ranking check | 14/30 (46.7%) |
| Independent semantic audit accuracy | 14/23 (60.9%) |
| Independent semantic audit coverage | 23/30 (76.7%) |
| Business result accuracy | 11/20 (55.0%) |
| Output contract compliance | 13/20 (65.0%) |
| Valid clarification/abstention | 8/10 (80.0%) |
| Unsafe executions | 0 |
| JEV raw required-table Recall@5 | 40/40 required-table references across 29 applicable cases |

Per-case outcomes and all scoring input hashes are in [`report.md`](report.md) and [`scores.json`](scores.json). The fixed run observations and provider metadata are in [`data.json`](data.json).

## Interpretation limits and scorer findings

- **B40-001 and B40-004 date output representation:** the frozen reference schema declares `web_traffic.date` and `orders.order_date` as `DATE`. In both SQL statements `DATE_TRUNC('month', date)` returned month-start values serialized as `YYYY-MM-01T00:00:00+00:00`; Gold uses `DATE_TRUNC(... )::date` and serialized `YYYY-MM-01`. An independent comparison of the saved rows found all 48/48 and 12/12 rows equal after normalizing only exact UTC-midnight month timestamps to their calendar date. The SQL uses `EXTRACT(YEAR FROM DATE)` for the year filter, equivalent to the Gold half-open calendar-year range for these verified `DATE` columns. Scorer 3.3 compares row values literally, so its business-result score marks both cases `FAIL`; no result or Gold was changed.
- **B40-011 ranking check false negative:** the linked semantic review marks the SQL `PASS`: it projects `p.cogs AS catalog_cogs`, orders by `p.cogs DESC, p.product_id ASC`, and limits to 5. The scorer's ranking checker only accepts the requested field name or listed aliases (`unit_cogs`, `cogs_per_unit`) and returns `ranking_key_0_mismatch` for the source expression `p.cogs`. This downgrades the effective semantic score to `FAIL`; SQL execution was also blocked by the same ranking validator issue. The frozen case and alias list were not edited.
- **Repair metric instrumentation gap:** the scorer reports repair recovery as `0/0` because it reads top-level `repair_count`/`repairs`, while the runner stores repair events at `calls.sql_repair`. Raw telemetry records 10 repair cases: B40-002, 004, 011, 014, 016, 018, 022, 025, 026, and 040. Two ended in E2E `PASS` (B40-016, B40-018), so the separately derived recovery from run telemetry is 2/10. The official scorer metric remains not measurable.
- **JEV availability and fallback:** the configured schema selector succeeded for 38/40 cases; B40-026 and B40-040 used full-schema fallback. No HTTP status was captured for those two failures, so no provider cause is inferred. No SQL-provider fallback or local Codex fallback occurred. The 40/40 Recall@5 numerator is required-table coverage from raw successful selector candidates, not coverage inferred from full-schema fallback.
- **Output safety:** 10 unapproved output columns across 6 cases were individually linked to the run and left `REVIEW_REQUIRED`. No extra output was granted a safety `PASS`; these are unresolved output-contract questions, not hidden passes.
- **Unsupported B40-033:** the agent returned a safe “current snapshot unavailable” response without generated business SQL, but one approved repository event was recorded during snapshot availability checking. The protocol scorer excludes it from valid abstention for that event; unsafe execution count remains zero.

## Run and execution summary

- Outcome statuses: 19 `executed`, 1 `executed_empty`, 14 `clarification_required`, 1 `unsupported`, 5 `failed`.
- Successful approved repository calls: 21; attempts: 22; unverified executions: 0.
- SQL generation calls: 38; metric interpretation calls: 10; schema selector requests: 40; total captured model calls: 88.
- SQL provider: Cloudflare `@cf/openai/gpt-oss-20b`; secondary SQL provider submissions: 0; local Codex fallback calls: 0.
- Captured token usage: 152,588 input and 9,737 output tokens. Provider cost was not reported by the adapters.
- JEV full-schema fallback cases: B40-026 and B40-040. The recorded data contains no HTTP status for either.
- Database classification: frozen analytics snapshot; read-only role verified; fingerprint matched Gold; database writes: 0.

## Verification

- `PYTHONPATH=src uv run --no-sync python -m unittest discover -s artifacts/sql-agent-bussiness/tests -v` — PASS, 54 tests.
- `PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests/sql -p 'test_benchmark_v3_1_contract.py' -v` — PASS, 52 tests.
- `PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests/sql -v` — PASS, 575 tests run, 565 passed and 10 skipped.
- `git diff --check` and Python compile checks for runner/audit modules — PASS.

This run is immutable evidence. No case was rerun for scoring, and the 40-case run should not be repeated to address scorer limitations; scorer fixes belong in a separately versioned scorer and a clearly labeled rescore of this saved data.
