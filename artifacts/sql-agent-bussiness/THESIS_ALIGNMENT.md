# SQL Analytics Agent Evaluation: Thesis Alignment

## Research objective

This evaluation examines whether a business analytics SQL Agent can translate a natural-language request into a safe query that preserves the requested metric, data population, time interval, grouping grain and ranking, and returns the independently verified result. The unit of evaluation is the complete SQL Agent path rather than the SQL-generation model in isolation. The five-case pilot is formative debugging evidence and is not statistically representative of business analytics requests.

## Chapter IV — Methodology

The system under evaluation follows this path:

```text
Frozen question and authorized SQL request
  → metric and scope interpretation
  → schema selection or deterministic compiler selection
  → parameterized SQL generation or compilation
  → read-only, source, schema, join and semantic validation
  → bounded repair where allowed
  → approved repository execution
  → result and limitation reporting
```

The benchmark invokes the SQL mode directly. It excludes Knowledge retrieval and the outer Auto planner/revise workflow. Fixed compiler and inventory mapping cases remain part of the end-to-end SQL Agent pilot, but must be excluded from a SQL-LLM-only comparison. The internal SQL repair budget is recorded separately from Auto revisions.

The five original questions, SQL references, parameters and output rows are frozen in [`cases.json`](cases.json). The original report and raw observations are preserved in [`../sql-agent-business-pilot5-2026-11-20/`](../sql-agent-business-pilot5-2026-11-20/). The later 40-question cohort is specified in [`benchmark_40_plan.json`](benchmark_40_plan.json), but it is not executed and its oracle fields remain unprepared.

## Data source and limitations

The Commerce database represents synthetic competition data. It must not be interpreted as observed operating results from a real retailer. The five-case artifact stores only selected case outputs and a historical aggregate preflight; it is not a database dump. The original five-case run reported these historical coverage values: `commerce.sales` 2023-01-01 through 2026-11-13, `commerce.orders` 2023-01-01 through 2026-11-13, and `commerce.inventory` 2023-01-31 through 2026-11-13.

The current pilot used the explicitly frozen analytics snapshot in read-only mode. Preflight confirmed the least-privilege role, the declared `commerce.orders.order_date` PostgreSQL `DATE` type, and dataset fingerprint `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`. The benchmark stores only the selected case outputs and aggregate coverage; it does not include a database dump. The historical pilot remains unchanged.

## Chapter IV — Evaluation metrics

The protocol defines numerators, denominators and applicability in [`PROTOCOL.md`](PROTOCOL.md). The primary metric is Business End-to-End Accuracy: supported cases must preserve SQL semantics and match reference rows/values. Business Result Accuracy separates returned values from SQL semantics. Strict Result Exact Match additionally requires the exact output columns and order. SQL Semantic Accuracy, execution success, false-refusal rate, valid unsupported abstention, JEV raw recall@5, final schema coverage, repair recovery, unsafe executions, latency and provider calls are reported separately.

For ordered ranking cases, both result rows and tie-break order must match. Unordered rows are compared as multisets. Identifiers and integer counts are exact; numeric tolerance is frozen per case; `NULL` matches only `NULL`. A provenance field is business-valid only when enumerated with its expected value, but strict output matching may still reject it.

## Chapter V — System design and implementation

The SQL Agent selects either deterministic fixed compilation, inventory interpretation plus compilation, or general SQL generation. All paths still depend on the read-only repository boundary and its source/schema checks. The benchmark runner captures route, source hashes, prompt hashes, provider/model settings, package versions, schema-selection evidence, SQL, parameters, rows, error details, execution events, calls and latency. Per-case output is atomically persisted. Completed experiments and terminal case records cannot be overwritten.

The evaluation requires `SQL_BENCHMARK_DATABASE_URL`, `SQL_BENCHMARK_DB_CLASSIFICATION`, and `SQL_BENCHMARK_ALLOWED_HOSTS`. In frozen-snapshot mode, the benchmark URL must exactly match `ANALYTICS_DATABASE_URL` and an explicit freeze acknowledgement is required. The repository verifies read-only database permissions. No credentials are written to benchmark artifacts.

## Chapter VI — Results and discussion

### Historical five-case pilot

The original pilot report recorded these results at application revision `c0e5aa7753ffffde20390fb19a91b168c4a0ab9b`:

| Metric | Historical result |
|---|---:|
| Strict end-to-end accuracy | 1/4 |
| Business-value accuracy | 2/4 |
| SQL semantic contract accuracy | 3/4 |
| Approved execution acceptance | 3/4 |
| Safe unsupported abstention | 1/1 |
| JEV availability | 0/4; recall@5 not measurable |
| Bounded repair recovery | 0/1 |
| Latency, descriptive only | p50 8.19 s; p95 14.85 s |

The report's per-case interpretation was: P01 executed and matched; P02 executed without the explicitly requested delivered-order filter; P03 used quantity-based ranking semantics but was rejected after the phrase “return product_id” was interpreted as return-domain intent; P04 returned the requested stock values plus a `snapshot_date` provenance column; P05 abstained without business SQL but did not explain all missing dimensions.

P02 was a semantic false acceptance in the historical run: successful execution did not make the delivered-order population correct. The current implementation maps supported bilingual order-status wording to a population contract and validates the parsed SQL predicate before execution. In the latest clean-revision run, the generator and its bounded repair both omitted `delivered`; the validator rejected the query before business SQL execution. This fixes the unsafe false acceptance, but P02 remained an end-to-end failure. Regressions cover required delivered status, cancelled-status exclusion, canonical metric filters, unrequested status filters, repair success and repair exhaustion. This vocabulary does not establish coverage of arbitrary named regions, customers or other unmodeled filters; broader population extraction remains a benchmark risk.

P03 is a semantic false rejection. The current ranking intent resolves “units sold” to `SUM(commerce.order_items.quantity)`, and a model-supplied returns metric cannot replace that typed measure. The regression verifies repair to the order-item quantity contract while preserving legitimate returns analytics elsewhere. The repository's approved schema contract declares `commerce.orders.order_date` as `DATE`; therefore an inclusive June 30 bound is equivalent to the gold half-open bound ending July 1. The scorer accepts that alternative only for `DATE`, and the benchmark preflight verifies the live database type before measurement.

### Fresh five-case reruns

The first rerun used the frozen snapshot at base revision `e6f3b90915bbd5359bff6966c7403fc1b6d5f0b5` from a dirty worktree. Its exact source hashes and trace are preserved in [`runs/pilot5-origin-main-e6f3b909/`](runs/pilot5-origin-main-e6f3b909/); it scored 4/4 business end-to-end and 2/4 strict exact. A subsequent run used the clean, committed revision `8e4abbd1e0a1352c93d747c825c15bf1aff3a1b4` on the same snapshot and frozen five questions. At run time, all 17 SQL/source hashes and 12 benchmark-tool hashes matched the committed tree. The current preflight reconfirmed the same dataset fingerprint, `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`, and the repository's database-role verifier accepted the read-only role.

| Case | Latest clean run | Interpretation |
|---|---|---|
| P01 | Exact deterministic match | Annual compiler; no SQL generation call |
| P02 | Failed closed | The generated query and one bounded repair omitted `order_status = 'delivered'`; validator prevented execution |
| P03 | Business rows correct; strict schema mismatch | Correct delivered units ranking and DATE upper bound; output alias was `units` instead of `units_sold` |
| P04 | Business values correct; strict mismatch | Correct snapshot/ranking, with additional `snapshot_date` provenance column |
| P05 | Invalid clarification; no business SQL | Clarification option schema failed validation; not counted as a valid abstention |

Across four answerable cases, business end-to-end accuracy was 3/4, business result accuracy was 3/3 executed cases, SQL semantic accuracy was 3/4, execution success was 3/4, and strict result exact match was 1/4. Safe unsupported abstention was 0/1 because P05 did not produce a valid clarification object. No unsafe or unverified SQL ran. The older dirty run's 4/4 score is retained as a separate observation; this is not a controlled model comparison, so the score difference cannot be attributed to one patch.

The latest run recorded six SQL-generation provider submissions (one secondary-provider fallback), two metric interpretation submissions, four JEV requests and two bounded repair attempts. Three approved business queries executed; P02 and P05 executed none. JEV returned HTTP 402 for each attempted selection; recall@5 is not measurable and full-schema fallback is not JEV recall. The artifact retains the HTTP status but not the provider response body, so the specific balance, key-cap or in-flight-budget cause is unverified. Provider token usage was not exposed by the captured telemetry. Latency p50/p95 was 7.88/14.96 seconds over four supported cases; the small development cohort is descriptive only and does not establish model superiority, generalization or production readiness.

Using Python 3.11.16, the benchmark package suite passed 37 tests, the SQL regression suite passed 383 tests with 10 explicit skips, inventory regressions passed 73 tests with 3 skips, metric mapping passed 23, and hybrid field contracts passed 5. GitHub CI passed for `8e4abbd1`; these automated checks are separate from the live frozen-snapshot pilot.

## Chapter VII — Conclusions and limitations

The historical pilot exposed a delivered-order population omission and a ranking-metric interpretation mismatch. Regression tests now exercise both defects, and the scorer separates business results from strict output equality. The latest clean-revision pilot shows the delivered-filter defect is blocked before execution, while the bounded repair did not recover the answer; an invalid P05 clarification also remains a failure. The 40-case cohort is `NOT_READY_FOR_40_CASE_BENCHMARK`: questions still need two-reviewer adjudication and gold SQL/results, and the cohort has not been executed. The five pilot questions are development/debug cases only. For later SQL-model comparisons, hold code, interpretation, schema selection, prompts, validators, repair budget, snapshot and scoring fixed while varying only the SQL-generation model. Evaluate JEV separately and stratify by provider availability.

The next evaluation should freeze the 40 candidate questions only after two-person semantic review and reference generation on one verified non-production snapshot. Keep the five pilot cases in the development/debug set. For SQL model comparisons, hold application code, intent interpretation, schema selection, prompts, validators, repair budget, database snapshot and scoring fixed; vary only the SQL-generation model. Evaluate JEV separately and stratify by provider availability.

## Reproducibility references

- Benchmark package: [`artifacts/sql-agent-bussiness/`](.)
- Frozen pilot definitions and oracle rows: [`cases.json`](cases.json)
- Scorer and protocol: [`scorer.py`](scorer.py), [`PROTOCOL.md`](PROTOCOL.md)
- Read-only preflight and reference generation: [`preflight.py`](preflight.py), [`reference_runner.py`](reference_runner.py)
- SQL Agent runner and failure classes: [`runner.py`](runner.py), [`failure_classes.json`](failure_classes.json)
- Latest clean-revision run: [`runs/pilot5-main-8e4abbd1-20261121/`](runs/pilot5-main-8e4abbd1-20261121/)
- Earlier dirty-worktree run: [`runs/pilot5-origin-main-e6f3b909/`](runs/pilot5-origin-main-e6f3b909/)
- Current summary: [`data.json`](data.json), [`scores.json`](scores.json), [`report.md`](report.md)
- Historical pilot evidence: [`../sql-agent-business-pilot5-2026-11-20/report.md`](../sql-agent-business-pilot5-2026-11-20/report.md)
