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

The protocol defines numerators, denominators and applicability in [`PROTOCOL.md`](PROTOCOL.md). The primary metric is Business End-to-End Accuracy: supported cases must preserve SQL semantics and match reference rows/values. Business Result Accuracy separates returned values from SQL semantics. Strict Result Exact Match additionally requires the exact output columns and order. SQL Semantic Accuracy, execution success, false clarification/abstention, supported noncompletion, validation-blocked failures, valid unsupported abstention, JEV raw recall@5, final schema coverage, repair recovery, unsafe executions, latency and provider calls are reported separately.

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

P02 was a semantic false acceptance in an earlier historical run: successful execution did not make the delivered-order population correct. The implementation maps supported bilingual order-status wording to a population contract, includes that typed obligation in generation and repair prompts, and validates the parsed SQL predicate before execution. In the clean baseline run at revision `8e4abbd1`, both generated attempts omitted `delivered`; validation correctly prevented execution. In the patched run, the initial SQL included `delivered` and passed the semantic checks. Regressions cover required delivered status, cancelled-status exclusion, canonical metric filters, unrequested status filters, repair success and repair exhaustion. This vocabulary does not establish coverage of arbitrary named regions, customers or other unmodeled filters; broader population extraction remains a benchmark risk.

P03 is a semantic false rejection. The current ranking intent resolves “units sold” to `SUM(commerce.order_items.quantity)`, and a model-supplied returns metric cannot replace that typed measure. The regression verifies repair to the order-item quantity contract while preserving legitimate returns analytics elsewhere. The repository's approved schema contract declares `commerce.orders.order_date` as `DATE`; therefore an inclusive June 30 bound is equivalent to the gold half-open bound ending July 1. The scorer accepts that alternative only for `DATE`, and the benchmark preflight verifies the live database type before measurement.

### Fresh five-case reruns

An earlier dirty-worktree run at base revision `e6f3b90915bbd5359bff6966c7403fc1b6d5f0b5` remains preserved in [`runs/pilot5-origin-main-e6f3b909/`](runs/pilot5-origin-main-e6f3b909/). It scored 4/4 business end-to-end and 2/4 strict exact, but is not a controlled comparison with later runs. The clean baseline at revision `8e4abbd1e0a1352c93d747c825c15bf1aff3a1b4` used the same frozen snapshot and five questions. Its original outputs remain untouched in [`runs/pilot5-main-8e4abbd1-20261121/`](runs/pilot5-main-8e4abbd1-20261121/).

The protocol 1.1.2 / scorer 2.0.2 rescore of that baseline changes only scorer interpretation: its verified `DATE` column makes the SQL `EXTRACT(YEAR FROM order_date) = 2025` equivalent to the calendar-year range, while the missing `delivered` filter still fails. Baseline metrics remain 3/4 business end-to-end, 3/4 SQL semantic, 3/3 business results among executed cases, 1/4 strict exact, 0/4 false clarification/abstention, 1/4 supported noncompletion, 1/4 validation-blocked, and 0/1 valid unsupported abstention. This fixes the protocol/scorer date-range disagreement without changing P02's semantic failure.

A fresh patched run is stored in [`runs/pilot5-sqlfix-groq-b86b4d9-20261121T0047Z/experiment/`](runs/pilot5-sqlfix-groq-b86b4d9-20261121T0047Z/experiment/). It used the same verified snapshot fingerprint `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`, the frozen five-case file and reference hash `295c53652e5fe3a7fc8c3c35cffb9ecf4f6bc23e44b6db861955e369d0932a17`. The base revision is `b86b4d91fba24ad9f2ec14901c83eed0c7f84504`; the dirty-worktree state and source hashes are recorded. Scorer 2.0.2 reports:

| Metric | Result |
|---|---:|
| Business End-to-End Accuracy | 4/4 supported |
| Business Result Accuracy | 4/4 executed supported |
| SQL Semantic Accuracy | 4/4 supported |
| Execution Success | 4/4 supported |
| Strict Result Exact Match | 2/4 supported |
| Valid Unsupported Abstention | 1/1 unsupported |
| Supported Noncompletion | 0/4 |
| Unsafe Executions | 0 |

P02 generated the delivered filter on its first attempt, preserved the requested year, distinct-order count, grouping, ordering and top-five limit, and matched reference rows. No repair was invoked in this fresh run, so repair recovery is N/A; bounded repair success and exhaustion are covered by deterministic tests. P05 was answered from the known schema gap before SQL generation or execution, explaining the missing warehouse, supplier and supplier lead-time fields. The returned alternative is product/category snapshot analysis. P03 used local Codex fallback once; its model identity is not captured, so this run is end-to-end SQL Agent evidence, not a single-model comparison. The primary provider was Groq `openai/gpt-oss-20b`; no secondary SQL provider submission occurred.

JEV failed with HTTP 402 in all three attempted selections; raw provider diagnostics were not retained, so the specific cause is unknown and recall@5 is NOT MEASURABLE. Full-schema fallback is not treated as JEV coverage. The new run's initial scorer 2.0.0 output is preserved separately; its 3/4 E2E figure was caused by not reading `preflight_coverage`. The corrected versioned rescore changes no SQL or observations and recognizes the verified date equivalence.

Using Python 3.11.16 from the existing workspace environment, the benchmark package suite passed 40 tests; the full SQL suite passed 513 with 10 skips; inventory suites passed 70 with 3 skips; dashboard clarification API passed 26; SQL assistant endpoint passed 10. These local tests and the fresh live pilot are separate forms of evidence. The five-case development cohort is too small for model superiority, generalization or production-readiness claims.

## Chapter VII — Conclusions and limitations

The clean baseline exposed a delivered-order population omission and a malformed unsupported clarification. Regression tests cover the population contract in generation and repair, the schema-grounded P05 abstention, and scorer date equivalence. The patched five-case run completed all four answerable cases with semantically valid SQL and reference-matching rows; P05 safely abstained. The 40-case cohort is NOT_READY_FOR_40_CASE_GOLD_PREPARATION: B40-007 duplicates P02, B40-031 duplicates P01, B40-021 duplicates P04, and B40-036/B40-037 overlap P05's unsupported scope. Independent reviewers must adjudicate versioned corrections and the remaining ambiguities before gold preparation. READY_FOR_40_CASE_EXECUTION = NO. Keep P01–P05 as development/debug cases. For SQL-model-only comparisons, disable or freeze fallback and record each model identity; evaluate JEV availability separately.

The next evaluation should freeze the 40 candidate questions only after two-person semantic review and reference generation on one verified non-production snapshot. Keep the five pilot cases in the development/debug set. For SQL model comparisons, hold application code, intent interpretation, schema selection, prompts, validators, repair budget, database snapshot and scoring fixed; vary only the SQL-generation model. Evaluate JEV separately and stratify by provider availability.

## Reproducibility references

- Benchmark package: [`artifacts/sql-agent-bussiness/`](.)
- Frozen pilot definitions and oracle rows: [`cases.json`](cases.json)
- Scorer and protocol: [`scorer.py`](scorer.py), [`PROTOCOL.md`](PROTOCOL.md)
- Read-only preflight and reference generation: [`preflight.py`](preflight.py), [`reference_runner.py`](reference_runner.py)
- SQL Agent runner and failure classes: [`runner.py`](runner.py), [`failure_classes.json`](failure_classes.json)
- Clean baseline and scorer 2.0.2 rescore: [`runs/pilot5-main-8e4abbd1-20261121/`](runs/pilot5-main-8e4abbd1-20261121/)
- Patched five-case live run and scorer 2.0.2 rescore: [`runs/pilot5-sqlfix-groq-b86b4d9-20261121T0047Z/experiment/`](runs/pilot5-sqlfix-groq-b86b4d9-20261121T0047Z/experiment/)
- Earlier dirty-worktree run: [`runs/pilot5-origin-main-e6f3b909/`](runs/pilot5-origin-main-e6f3b909/)
- Current summary: [`data.json`](data.json), [`scores.json`](scores.json), [`report.md`](report.md)
- Historical pilot evidence: [`../sql-agent-business-pilot5-2026-11-20/report.md`](../sql-agent-business-pilot5-2026-11-20/report.md)
