# Dashboard Bilingual Baseline

Run date: 2026-11-13. Completed 50/50 prompts. One first attempt per unchanged prompt; no clarification replies supplied.

**Verdict: provisional, availability-constrained baseline.** All 25 supplied English/Vietnamese pairs were tested unchanged. The 30% overall pass rate primarily reflects Jev dependency failures and must not be interpreted as a clean measure of model accuracy or a reliable English/Vietnamese comparison.

## Results

| Language | Prompts | Baseline passes | SQL executed | Value matches | Charts | Median seconds |
|---|---:|---:|---:|---:|---:|---:|
| All | 50 | 15 | 16 | 15 | 6 | 12.00 |
| english | 25 | 6 | 7 | 6 | 3 | 12.01 |
| vietnamese | 25 | 9 | 9 | 9 | 3 | 12.00 |

Baseline pass requires the requested behavior and matching reference rows for executable questions. Clarification and unavailable-data cases use their supplied behavior criteria.

Failure phases: {"ambiguity_decision": 4, "ambiguity_service": 29, "result_mismatch": 1, "planning_clarification": 1}.

## Findings

- **15/50 overall passes (30%).** English: 6/25; Vietnamese: 9/25. Among the 16 executed queries, 15 matched the independent reference results (93.75%). The 29 service-failed attempts remain in the overall denominator.
- **29 Jev service failures:** 27 timeouts and two URL errors prevented SQL generation. Advanced/expert questions and both clarification/current-data controls were largely unevaluated beyond this dependency; their failures do not establish that their SQL answers would be wrong.
- **Four confidence-gate blocks:** B02 in both languages, B04-English, and B07-English were classified with clear probabilities of 0.57, 0.60, 0.66, and 0.70, below the configured 0.80 threshold, despite the returned choice being `clear`.
- **One confirmed numerical/output defect:** B12-English requested the lowest 10 products. The model interpretation contained `limit: 10`, but compiled SQL used `LIMIT 200`, returning 200 rows. B12-Vietnamese correctly returned 10 rows. The English result was not accepted merely because its first 10 rows were correct.
- **One schema-selection defect:** B14-English asks about page views, but its SQL-generation prompt omitted `commerce.web_traffic`. The model therefore requested clarification instead of querying the available source.
- **Six grounded chart specifications:** two line and four bar charts, all backed by SQL rows that also matched the reference values. Ten queries returned tables; scalar answers are intentionally not chart failures. No donut was produced, so donut behavior remains unmeasured by this run.
- **No application tuning during the run:** 162 application/configuration source files matched the frozen baseline afterward. Input questions, oracle SQL/results, generation traces, scores, model settings, and source are retained. All supplied numerical verified answers matched the live oracle.

The database pool also timed out during shutdown after all 50 attempts had been checkpointed. No prompt results were lost; scoring was completed separately. See [verification](verification.json).

Recommended next step: restore stable Jev connectivity, then rerun the entire unchanged set into a new baseline directory. Keep this run intact. Address the rank-limit and page-view schema-selection defects only after preserving these baseline results; add explicit chart-type cases separately for renderer coverage.

## Per-question results

| ID | EN | VI | EN chart | VI chart |
|---|---|---|---|---|
| B01 | PASS | PASS | - | - |
| B02 | clarification_required | clarification_required | - | - |
| B03 | PASS | PASS | - | - |
| B04 | clarification_required | PASS | - | - |
| B05 | PASS | PASS | - | - |
| B06 | PASS | PASS | line | line |
| B07 | clarification_required | PASS | - | - |
| B08 | TimeoutError | PASS | - | bar |
| B09 | TimeoutError | TimeoutError | - | - |
| B10 | TimeoutError | TimeoutError | - | - |
| B11 | PASS | TimeoutError | bar | - |
| B12 | Result mismatch: row_count | PASS | - | - |
| B13 | PASS | PASS | bar | bar |
| B14 | clarification_required | TimeoutError | - | - |
| B15 | TimeoutError | TimeoutError | - | - |
| B16 | URLError | TimeoutError | - | - |
| B17 | TimeoutError | TimeoutError | - | - |
| B18 | TimeoutError | TimeoutError | - | - |
| B19 | TimeoutError | TimeoutError | - | - |
| B20 | TimeoutError | TimeoutError | - | - |
| B21 | URLError | TimeoutError | - | - |
| B22 | TimeoutError | TimeoutError | - | - |
| B23 | TimeoutError | TimeoutError | - | - |
| B24 | TimeoutError | TimeoutError | - | - |
| B25 | TimeoutError | TimeoutError | - | - |

## Method and limits

- Exact supplied wording and both languages were used through explicit Dashboard routing; each prompt starts without conversation history.
- Measured latency includes the in-process agent/router flow, Jev, model generation, SQL and chart mapping; it excludes authentication/HTTP, browser rendering, setup, reference queries and pacing.
- Frozen application source, input questions, model settings, reference SQL/results, generated SQL/results, clarity decisions, latency and generation usage are retained alongside this report.
- Reference values are independently queried; they are not supplied to the models. Read-only database access is used throughout.
- References are captured before generation; the live database is not held in a single snapshot for the entire run. Supplied non-null numerical answers were checked against the captured data.
- Value matching ignores aliases but preserves row associations and required ordering. It normalizes monthly date formatting and known extra provenance fields. This is numerical/result equivalence, not a formal proof of SQL semantic equivalence.
- SQL-oriented scalar questions can legitimately return tables. No prompts were rewritten to demand a chart; chart yield is descriptive and this set does not fully cover explicit donut selection.
- Chart grounding checks consistency with returned SQL rows, not browser appearance. Incorrect SQL can still produce a grounded but incorrect chart.
- Generation token usage excludes Jev and any failed provider calls with unreported usage. No provider cost is inferred.
- This single pass does not measure repeatability, clarification recovery, concurrency, or visual accessibility. Failures remain included; production code was not tuned during the run.

Detailed evidence: [scores](scores.json), [CSV scores](scores.csv), [summary](summary.json), [references](references.json), [raw generations](generations.jsonl), [configuration](manifest.json), [verification](verification.json).
