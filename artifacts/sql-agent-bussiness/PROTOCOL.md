# SQL Agent Business Benchmark Protocol

Protocol version: `1.0.0`

Pilot case set: `cases.json`

Primary application under test: SQL Agent only. Knowledge and Auto orchestration are excluded.

## Research question and scope

Measure whether the SQL Agent converts frozen business questions into safe SQL that preserves the requested population, metric, time scope, grain, ranking and output, and returns the independently verified business result. The five pilot cases are development evidence; they are not a representative sample of all analytics requests. Fixed and inventory compiler cases measure end-to-end SQL Agent behavior, not SQL-generation-model quality.

## Frozen inputs

`cases.json` contains exact question text, supported/unsupported status, required source tables, gold SQL, bound values, frozen reference rows, output policy, numeric tolerance and semantic contract. `benchmark_40_plan.json` is a design-only candidate cohort. Its gold fields are intentionally null until a non-production database and reference approval are available.

P03 records `commerce.orders.order_date` as PostgreSQL `DATE`. The scorer accepts an inclusive `<= 2025-06-30` upper bound as equivalent to `< 2025-07-01` only for that declared type. The database preflight reads the live column type from schema discovery, rejects a mismatch, and includes the verified type in the dataset fingerprint. A timestamp column requires the exclusive next-day bound.

Before generation, the runner verifies the case-set hash and data fingerprint against the separately generated reference artifact. A changed database fingerprint stops the run. Gold SQL/results must be regenerated and reviewed under a new artifact version; never overwrite a frozen case set after observing model output.

## Metrics

All rate metrics report integer numerator, denominator and a `null` value when the denominator is zero. `NOT RUN` cases are excluded. Denominators include only applicable cases.

| Metric | Definition | Applicable denominator |
|---|---|---|
| Business End-to-End Accuracy (primary) | Supported cases with executed SQL, all required SQL semantics, and business rows correct ÷ supported cases | All attempted supported cases |
| Business Result Accuracy | Executed supported cases whose requested rows and values match the reference under the frozen business schema policy ÷ executed supported cases | Executed supported cases |
| Strict Result Exact Match | Executed supported cases with exact strict output columns, column order, rows, values and SQL semantics ÷ supported cases | All attempted supported cases |
| SQL Semantic Accuracy | Supported cases whose parsed SQL preserves required tables, filters, date bounds, aggregate, grouping, join, ranking direction, tie-break and limit ÷ supported cases | All attempted supported cases |
| Execution Success | Supported cases reaching `executed` or `executed_empty` ÷ supported cases | All attempted supported cases |
| False-Refusal Rate | Supported cases clarified, rejected or abstained without successful execution ÷ supported cases | All attempted supported cases |
| Valid Clarification/Abstention | Unsupported cases with clarification/abstention and no SQL or execution ÷ unsupported cases | All attempted unsupported cases |
| JEV Raw Recall@5 | Required tables in JEV's raw top-five candidates ÷ required tables across cases where JEV succeeded | JEV-successful cases only; on HTTP failure recall is not measurable |
| Final Schema Coverage | Required tables present in the final schema sent to SQL planning ÷ required tables for cases with a selected schema | Cases with observable final schema; fixed compiler bypasses are excluded |
| Repair Recovery Rate | Cases that execute after at least one internal SQL repair ÷ cases with an internal SQL repair | Internal SQL repair cases only; Auto revise is a separate mechanism |
| Unsafe Execution Count | Execution events that did not pass the repository security boundary | Count; target is exactly zero |
| Latency p50/p95 | End-to-end case latency using nearest-rank percentiles | Executed benchmark attempts with recorded latency |
| Provider Calls | Count SQL-generation submissions, metric-mapping submissions, JEV HTTP requests, and local Codex fallback calls; secondary SQL-provider submissions are also shown as a subset of SQL-generation submissions | Count, reported by stage; fixed compiler calls should be zero |

SQL generation token usage is reported only when the selected provider exposes token counts. Current provider interfaces return generated text without reliable usage metadata; token usage is therefore `NOT AVAILABLE`, never estimated.

`general_sql_generation` counts each provider submission made by the SQL generation stage, including a secondary provider after a primary failure. `provider_fallback_calls` is the secondary-provider subset of that count; `local_codex_fallback_calls` is counted separately. `metric_interpretation` counts metric-mapping provider submissions. `total_model_calls` sums SQL-generation submissions, metric-mapping submissions, JEV HTTP requests and local Codex calls; it does not add the fallback subset a second time. Pipeline counters are reported separately: fixed matching calls and matches, fixed compilation calls and plans, inventory compilation calls and plans, `schema_discovery`, `schema_selection`, SQL generation entries/repairs, repository execution attempts, and successful repository executions. A repository execution event is recorded only after its query call returns successfully; failed attempts remain visible in the attempt counters.

Because the aggregate `total_model_calls` includes JEV HTTP requests (including failed requests), use the per-stage counts to distinguish generated SQL/model submissions from schema-selection availability. A JEV request count is not a successful JEV selection count.

The package is intentionally separate from `evaluation/run_agent_benchmarks.py` (a 75-prompt, three-agent RAGAS run) and the older `evaluation/agent_benchmarks/sql_analytics_agent_benchmark.json` cohort (25 questions, recorded data through 2022-12-31). Their case sets, snapshots and scoring contracts differ, so their scores must not be combined with this pilot.

## Business and strict result policies

Business End-to-End correctness requires SQL semantics and requested values to match. Ordered ranking cases compare row order including stable tie-breaks; unordered cases compare row multisets. IDs and integer counts are exact. Numeric tolerances are case-specific and are frozen before model calls. `NULL` matches only `NULL`.

Requested output aliases may be accepted for business correctness only when explicitly listed in `column_aliases`. A known provenance field can be accepted as a business-valid extra only when its value equals the frozen provenance value. For P04, `snapshot_date=2026-11-13` is such a field. Strict matching still requires the exact frozen output columns and order. Missing requested columns or unexpected additional columns fail business-result comparison.

SQL semantic accuracy is scored separately from result matching. Executable SQL is not automatically semantically correct. A query with correct rows by coincidence but a missing required population filter fails Business End-to-End Accuracy.

## Data and oracle

Commerce data is synthetic competition data, not observed retailer operations. Frozen result rows are limited to the five cases. No full database dump is stored. Reference generation runs the frozen gold SQL through the repository's approved read-only executor and stores a compact aggregate data fingerprint plus the case outputs. It must use a separately designated non-production PostgreSQL endpoint and the repository's least-privilege role validation.

The preflight fails closed unless `SQL_BENCHMARK_DATABASE_URL` and `SQL_BENCHMARK_ALLOWED_HOSTS` are set and the repository verifies a least-privilege read-only role. Use either `SQL_BENCHMARK_DB_CLASSIFICATION=non-production` for a dedicated test database, or `SQL_BENCHMARK_DB_CLASSIFICATION=frozen-analytics-snapshot` when the configured analytics snapshot is explicitly frozen. Frozen mode requires the benchmark URL to exactly match `ANALYTICS_DATABASE_URL` and `SQL_BENCHMARK_FROZEN_SNAPSHOT_ACK=I_CONFIRM_ANALYTICS_SNAPSHOT_IS_FROZEN`. Never use frozen mode for a database that can still change during the run. The benchmark records classification and a content-coverage fingerprint; secrets are read from environment variables and never written to artifacts.

## Runtime, tracing and recovery

Use a pinned application revision. If the worktree is dirty, explicitly allow it and record relevant source hashes and dirty state. The runner records provider/model settings, package versions, prompt hashes, repair budget, case-set hash, reference hash, schema selection, compiled path, SQL/parameters, rows, status, exception type/reason, calls and latency. Provider methods are instrumented with wrappers preserving their original signatures. The runner writes each case atomically before moving to the next one.

SQL Agent repair remains its bounded internal loop. Auto revise is not invoked by this benchmark and must not be merged into its retry count. Completed experiments and terminal case results are immutable. Resume is allowed only for an incomplete experiment with the same configuration fingerprint; already terminal case IDs are skipped. A forcibly terminated `RUNNING` case is rerun as a new attempt only after explicitly resuming, and the prior attempt record is retained. Unsupported cases are persisted without requiring gold SQL.

## JEV interpretation

Report raw JEV top-five candidates, required tables, ontology-added sources, approved join-bridge additions, final schema and final schema coverage separately. When JEV fails, report `availability=FAILED`, its HTTP status, and `recall@5=NOT MEASURABLE`. `full_schema_fallback` coverage is not JEV recall. Do not compare fallback and JEV-enabled runs as if schema selection conditions matched.

Explicit order-status population wording is resolved through the field-value vocabulary in `metric_ontology.py` into a typed `(source, column, operator, values)` contract. SQL is checked through parsed predicate lineage before execution. Canonical metric filters remain allowed and are independently validated by the metric catalog. The vocabulary is bounded; requests involving unmodeled population fields still need dedicated regression cases before the 40-case cohort is frozen.

## Reproduction workflow

From the repository root, configure the database and provider through environment variables. For the frozen snapshot mode used in this pilot, confirm the database is frozen, set `SQL_BENCHMARK_DATABASE_URL` to exactly the same URL as `ANALYTICS_DATABASE_URL`, add its hostname to `SQL_BENCHMARK_ALLOWED_HOSTS`, and set the explicit freeze acknowledgement described above. Run preflight first and check the read-only role and fingerprint before reference generation.

```bash
PYTHONPATH=src uv run python artifacts/sql-agent-bussiness/preflight.py --output /tmp/sql-benchmark-preflight.json
PYTHONPATH=src uv run python artifacts/sql-agent-bussiness/reference_runner.py \
  --cases artifacts/sql-agent-bussiness/cases.json \
  --output artifacts/sql-agent-bussiness/runs/<run-id>/reference.json
PYTHONPATH=src uv run python artifacts/sql-agent-bussiness/runner.py \
  --application-revision "$(git rev-parse HEAD)" \
  --provider cloudflare --model '@cf/openai/gpt-oss-20b' \
  --cases artifacts/sql-agent-bussiness/cases.json \
  --reference artifacts/sql-agent-bussiness/runs/<run-id>/reference.json \
  --output artifacts/sql-agent-bussiness/runs/<run-id>/experiment
```

To run on a dirty worktree, add `--allow-dirty`; source hashes and dirty status are recorded. The runner rejects an existing non-empty output directory. For an interrupted run, use `--resume` only with the same revision, case set, provider/model settings and reference. A completed experiment cannot be resumed or overwritten.

Offline protocol tests:

```bash
PYTHONPATH=src uv run python -m unittest discover -s artifacts/sql-agent-bussiness/tests -v
```

## 40-case model comparison

The 40-case file is not executed by this protocol run. Before treating it as held out, annotate and adjudicate each item, generate approved gold SQL and result rows on one verified non-production snapshot, freeze its hash, and keep P01–P05 as a development/debug cohort. For SQL-LLM-only comparisons, exclude deterministic compiler and inventory compiler cases, hold code, intent, schema selection, prompts, validators, retry budget, database snapshot and scoring protocol fixed, and vary only the SQL-generation model. Report JEV separately.
