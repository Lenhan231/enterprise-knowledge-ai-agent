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

P02 is a semantic false acceptance: successful execution did not make the delivered-order population correct. The current worktree maps catalogued bilingual order-status wording to a typed population-filter contract, then checks the parsed SQL predicate and source lineage before execution. Regressions cover required delivered status, cancelled-status exclusion, canonical metric filters, unrequested status filters, repair success and repair exhaustion. This field-value vocabulary does not establish coverage of arbitrary named regions, customers or other unmodeled filters; broader population extraction remains a benchmark risk.

P03 is a semantic false rejection. The current ranking intent resolves “units sold” to `SUM(commerce.order_items.quantity)`, and a model-supplied returns metric cannot replace that typed measure. The regression verifies repair to the order-item quantity contract while preserving legitimate returns analytics elsewhere. The repository's approved schema contract declares `commerce.orders.order_date` as `DATE`; therefore an inclusive June 30 bound is equivalent to the gold half-open bound ending July 1. The scorer accepts that alternative only for `DATE`, and the benchmark preflight verifies the live database type before measurement.

### Fresh five-case rerun

The fresh five-case pilot completed on the frozen snapshot at application base revision `e6f3b90915bbd5359bff6966c7403fc1b6d5f0b5`, with a dirty worktree whose source hashes are recorded in `data.json`. Four supported cases executed with 4/4 business end-to-end accuracy, 4/4 business result accuracy, 4/4 SQL semantic accuracy and 4/4 execution success. Strict output exact match was 2/4: P03 used an accepted business alias with a different strict column name, and P04 included the permitted `snapshot_date` provenance field. The unsupported P05 request was safely clarified without SQL execution (1/1).

Latency was p50 6.80 s and p95 40.45 s across four supported cases; the five-question pilot is too small for a stable latency estimate. There were four SQL-generation provider submissions, including one secondary-provider fallback, two metric interpretation calls, four JEV requests and zero local Codex calls. Therefore these results measure the configured SQL Agent path and are not a single-model comparison. JEV returned HTTP 402 in all four schema-selection cases; recall@5 is not measurable and fallback schema coverage is not JEV recall. No unsafe or unverified SQL executions occurred. These descriptive pilot results do not establish model superiority, generalization or production readiness.

For this update, using Python 3.11.16, the benchmark package suite passed 37 tests, the SQL regression suite passed 383 tests with 10 explicit skips, inventory regressions passed 73 with 3 skips, metric mapping passed 23, and hybrid field contracts passed 5. These checks used local fixtures; the separate pilot above is the evidence involving the frozen database and configured providers.

## Chapter VII — Conclusions and limitations

The historical pilot exposed a delivered-order population omission and a ranking-metric interpretation mismatch. Regression tests now exercise both defects, and the local benchmark scorer distinguishes business-value correctness from strict output equality. The fresh pilot measured 4/4 supported business outcomes on the frozen snapshot, but its five-question development cohort is small, had one provider fallback, and did not measure JEV recall. It does not establish model superiority, generalization, or production readiness.

The next evaluation should freeze the 40 candidate questions only after two-person semantic review and reference generation on one verified non-production snapshot. Keep the five pilot cases in the development/debug set. For SQL model comparisons, hold application code, intent interpretation, schema selection, prompts, validators, repair budget, database snapshot and scoring fixed; vary only the SQL-generation model. Evaluate JEV separately and stratify by provider availability.

## Reproducibility references

- Benchmark package: [`artifacts/sql-agent-bussiness/`](.)
- Frozen pilot definitions and oracle rows: [`cases.json`](cases.json)
- Scorer and protocol: [`scorer.py`](scorer.py), [`PROTOCOL.md`](PROTOCOL.md)
- Read-only preflight and reference generation: [`preflight.py`](preflight.py), [`reference_runner.py`](reference_runner.py)
- SQL Agent runner and failure classes: [`runner.py`](runner.py), [`failure_classes.json`](failure_classes.json)
- Current fresh-run status: [`data.json`](data.json), [`report.md`](report.md)
- Historical pilot evidence: [`../sql-agent-business-pilot5-2026-11-20/report.md`](../sql-agent-business-pilot5-2026-11-20/report.md)
