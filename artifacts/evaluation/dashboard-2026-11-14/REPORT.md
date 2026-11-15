# Dashboard benchmark — 2026-11-14

**50 local dashboard executions completed: 1 complete, 3 partial, 46 failed.** The single complete dashboard also passed an exact observation check. This configuration is not reliable for general bilingual Text-to-Dashboard requests.

| Measure | English | Vietnamese |
|---|---:|---:|
| Executions | 25 | 25 |
| Accepted final dashboard plans | 12 | 0 |
| Complete dashboard / strict request pass rate | 1/25 (4%) | 0/25 (0%) |
| Partial dashboards | 3 | 0 |
| Failed dashboards | 21 | 25 |
| Mean total latency (seconds) | 8.72 | 9.79 |
| Median total latency (seconds) | 7.55 | 9.37 |
| P95 total latency (seconds) | 14.66 | 13.02 |

The aggregate strict pass rate is **1/50 (2%)**. A strict pass requires the requested representations, scope, and observations, or a clear and accurate requested fallback/refusal for negative cases. Generic planning failures do not count as successful refusals. DB-24 English held the metric guard but gave an inaccurate source explanation, so it is not a full request pass. DB-25 never reached the authorization decision. These pass rates describe one execution per question and language, not repeated-run reliability.

## Frozen run configuration

- Code: `main` commit `bac3d96dedef3187fde3755a5ce0eaf74609a106`; tracked worktree clean before and after. No application fixes made during measurement.
- Primary provider: Cloudflare. User requested `llama-3.1-8b-instruct`; current production code aliases `@cf/meta/llama-3.1-8b-instruct` to **`@cf/meta/llama-3.1-8b-instruct-fast`**.
- Temperature `0`; output limit `1000`; `enable_thinking=false`; provider HTTP timeout 30 seconds; original planner retries, SQL repairs, deadlines, and two-dataset concurrency retained.
- Production SQL fallback policy retained (Groq `qwen/qwen3.8-27b`), but **no fallback was used**: all 118 recorded LLM calls used the same Cloudflare Llama model and none had a provider error.
- Local backend functions: `app.dashboards.build`, production identity construction, persist, and HTML renderer. Identity: `finance_analyst` with analytics read permission. Latency includes build, save, and render; excludes HTTP authentication, network transport to the app, and browser rendering.
- Fixed data: 15 approved commerce tables, **9,933 rows**, exported in one read-only repeatable-read transaction. Local PostgreSQL 17.6 with the recorded image digest. Column grants preserved; inaccessible invoice columns and unrelated schemas excluded. Discoverable tables, columns, keys, joins, and date fields exactly match the source role.
- All 15 table COPY hashes matched after the benchmark. Snapshot artifacts and source archive are retained for future comparisons. No Supabase data was changed. The source reader exposes no primary-key or foreign-key metadata; the clone preserves that visibility.
- Production knowledge metric retriever retained, but it was invoked **zero times**. No changing external knowledge affected this run.
- Production parity boundary: the model was confirmed by the user and backend defaults came from latest main. Deployed server environment variables, hardware, and dependencies were not remotely inspected; do not claim a full deployment replica.
- Exact attachment text preserved. Order: DB-01 through DB-25, English then Vietnamese. Exactly 50 dashboard builds; the seven reference SQL queries and coverage diagnostics are separate read-only checks, not additional agent executions.

## What failed

1. **Planning is the dominant blocker:** 38/50 final plans rejected (13 English, all 25 Vietnamese). Responses included extra authority/metric fields, missing top-level fields, undeclared query references, overlong identifiers, and invalid chart/KPI/summary dataset sharing. Raw attempts and validation errors are retained. Four rejected final outputs passed the JSON schema but failed composition rules.
2. **Coverage inspection is broken before the model runs:** `inspect_data` generates MIN/MAX/COUNT queries without a LIMIT. The normal validator rejects them with `The final SELECT needs LIMIT 1..200.` The planner sees coverage unavailable even though data exists. See `coverage_profile_diagnostic.json`.
3. **SQL planning and canonical metric matching still disagree:** seven source results failed canonical formula validation. Examples: DB-02 omitted the requested year grouping and wrapped SUM in CAST; DB-20 used COALESCE(SUM(...),0), while its KPI used a conditional sum without the requested year filter. These need separate treatment: harmless expression normalization must not conceal missing business/date constraints.
4. **Inventory relative scope is unresolved:** latest-snapshot requests returned requests for ISO dates; another inventory interpretation changed the requested period. Source coverage failure contributes context loss, but this benchmark does not establish it as the sole cause.
5. **Clarifications do not always explain the real limitation:** page views returned `monthly page views`; net profit margin was rejected with an inventory-catalog explanation despite revenue and COGS existing in sales.

Across the 12 accepted plans: 20 source-query requests, 38 tiles, and 4 actual dataset SQL executions. Source statuses were 4 complete, 7 failed, and 9 clarification required. No SQL execution produced a database error. The three partial dashboards were DB-06-en, DB-10-en, and DB-16-en.

## Priority regression cases

| Case | English | Vietnamese | What this establishes |
|---|---|---|---|
| DB-03 — date binding | Plan rejected: undeclared KPI dataset | Plan schema rejected | Date binding not reached. Reference has 11 observed months and revenue 18,881,151.90; December is absent. |
| DB-11 — distinct orders | Plan rejected: identifiers exceed 32 characters | Plan schema rejected | Distinct-order semantics not reached. Reference category counts: Casual 11, GenZ 63, Outdoor 548, Streetwear 318; category counts can overlap. |
| DB-13 — snapshot grain | Plan rejected: identifier length | Plan schema rejected | Grain safeguard not reached. Reference preserves 12 category/date observations across Sep 30, Oct 31, and Nov 13, 2026. |
| DB-20 — reuse | Correct planned reuse; both SQL results fail metric validation | Plan schema rejected | Line, summary, and table share one query; KPI uses another. Planning-level reuse passes; rendering and data execution fail. Reference quarter total is 5,733,349.81. |
| DB-22 — donut eligibility | Plan accepted; SQL invents sales.product_id and is stopped | Plan schema rejected | Missing-column safeguard holds. No unsafe donut rendered, but no usable table/eligibility explanation either. |

DB-07 English is the only full pass: line and table share one dataset, with July 1,810,421.90; August 1,832,695.76; September 2,090,232.15. Date labels and all values match the fixed-snapshot reference.

## Next fixes to compare against this baseline

1. Repair coverage queries to satisfy the existing SELECT bounds; use observed dates to resolve latest/last-N snapshot scope deterministically.
2. Make small-model planning contracts compact and enforce server-generated identifiers/references. Keep untrusted authority fields rejected; retain permission checks independently.
3. Strengthen SQL scope/grouping and known metric planning, and normalize only verified equivalent expressions. Preserve checks against missing years, invented columns, fanout, and unauthorized sources.
4. Produce explicit missing-data, unsupported-metric, privacy, and donut-fallback outcomes. Re-run these same 50 prompts on the same snapshot and configuration after changes; report model changes as separate comparisons.

## Every execution

| Execution | Status | Plan accepted | Queries | Tiles | Seconds |
|---|---|---|---:|---:|---:|
| [DB-01-en](executions/DB-01-en.json) | failed | no | 0 | 0 | 13.61 |
| [DB-01-vi](executions/DB-01-vi.json) | failed | no | 0 | 0 | 10.26 |
| [DB-02-en](executions/DB-02-en.json) | failed | yes | 1 | 2 | 5.90 |
| [DB-02-vi](executions/DB-02-vi.json) | failed | no | 0 | 0 | 7.82 |
| [DB-03-en](executions/DB-03-en.json) | failed | no | 0 | 0 | 16.64 |
| [DB-03-vi](executions/DB-03-vi.json) | failed | no | 0 | 0 | 8.62 |
| [DB-04-en](executions/DB-04-en.json) | failed | no | 0 | 0 | 10.76 |
| [DB-04-vi](executions/DB-04-vi.json) | failed | no | 0 | 0 | 8.95 |
| [DB-05-en](executions/DB-05-en.json) | failed | no | 0 | 0 | 6.31 |
| [DB-05-vi](executions/DB-05-vi.json) | failed | no | 0 | 0 | 11.10 |
| [DB-06-en](executions/DB-06-en.json) | partial | yes | 3 | 4 | 7.16 |
| [DB-06-vi](executions/DB-06-vi.json) | failed | no | 0 | 0 | 8.27 |
| [DB-07-en](executions/DB-07-en.json) | complete | yes | 1 | 2 | 14.66 |
| [DB-07-vi](executions/DB-07-vi.json) | failed | no | 0 | 0 | 5.60 |
| [DB-08-en](executions/DB-08-en.json) | failed | yes | 2 | 2 | 7.22 |
| [DB-08-vi](executions/DB-08-vi.json) | failed | no | 0 | 0 | 11.00 |
| [DB-09-en](executions/DB-09-en.json) | failed | yes | 1 | 6 | 6.26 |
| [DB-09-vi](executions/DB-09-vi.json) | failed | no | 0 | 0 | 9.79 |
| [DB-10-en](executions/DB-10-en.json) | partial | yes | 2 | 3 | 6.59 |
| [DB-10-vi](executions/DB-10-vi.json) | failed | no | 0 | 0 | 10.26 |
| [DB-11-en](executions/DB-11-en.json) | failed | no | 0 | 0 | 10.48 |
| [DB-11-vi](executions/DB-11-vi.json) | failed | no | 0 | 0 | 15.10 |
| [DB-12-en](executions/DB-12-en.json) | failed | no | 0 | 0 | 5.83 |
| [DB-12-vi](executions/DB-12-vi.json) | failed | no | 0 | 0 | 12.30 |
| [DB-13-en](executions/DB-13-en.json) | failed | no | 0 | 0 | 11.53 |
| [DB-13-vi](executions/DB-13-vi.json) | failed | no | 0 | 0 | 9.17 |
| [DB-14-en](executions/DB-14-en.json) | failed | no | 0 | 0 | 12.51 |
| [DB-14-vi](executions/DB-14-vi.json) | failed | no | 0 | 0 | 10.22 |
| [DB-15-en](executions/DB-15-en.json) | failed | no | 0 | 0 | 3.75 |
| [DB-15-vi](executions/DB-15-vi.json) | failed | no | 0 | 0 | 12.05 |
| [DB-16-en](executions/DB-16-en.json) | partial | yes | 3 | 5 | 7.01 |
| [DB-16-vi](executions/DB-16-vi.json) | failed | no | 0 | 0 | 12.82 |
| [DB-17-en](executions/DB-17-en.json) | failed | no | 0 | 0 | 7.56 |
| [DB-17-vi](executions/DB-17-vi.json) | failed | no | 0 | 0 | 6.34 |
| [DB-18-en](executions/DB-18-en.json) | failed | yes | 2 | 3 | 4.73 |
| [DB-18-vi](executions/DB-18-vi.json) | failed | no | 0 | 0 | 10.55 |
| [DB-19-en](executions/DB-19-en.json) | failed | no | 0 | 0 | 7.55 |
| [DB-19-vi](executions/DB-19-vi.json) | failed | no | 0 | 0 | 13.02 |
| [DB-20-en](executions/DB-20-en.json) | failed | yes | 2 | 4 | 13.18 |
| [DB-20-vi](executions/DB-20-vi.json) | failed | no | 0 | 0 | 8.61 |
| [DB-21-en](executions/DB-21-en.json) | failed | no | 0 | 0 | 7.20 |
| [DB-21-vi](executions/DB-21-vi.json) | failed | no | 0 | 0 | 7.63 |
| [DB-22-en](executions/DB-22-en.json) | failed | yes | 1 | 3 | 8.85 |
| [DB-22-vi](executions/DB-22-vi.json) | failed | no | 0 | 0 | 9.37 |
| [DB-23-en](executions/DB-23-en.json) | failed | yes | 1 | 2 | 9.43 |
| [DB-23-vi](executions/DB-23-vi.json) | failed | no | 0 | 0 | 9.01 |
| [DB-24-en](executions/DB-24-en.json) | failed | yes | 1 | 2 | 8.34 |
| [DB-24-vi](executions/DB-24-vi.json) | failed | no | 0 | 0 | 8.51 |
| [DB-25-en](executions/DB-25-en.json) | failed | no | 0 | 0 | 4.94 |
| [DB-25-vi](executions/DB-25-vi.json) | failed | no | 0 | 0 | 8.25 |

## Files and replay

- `results.json` / `results.jsonl`: all 50 executions, complete SQL payloads, observations, errors, raw planner validity summaries, and tile statuses. `summary.csv` is the compact index.
- `events.jsonl`: prompts, raw model responses, schema validity, accepted plans, source payloads, actual SQL, parameter Python types, observations, and stage latencies.
- `executions/`: one JSON per execution; HTML for every saved document, including failed/partial documents.
- `saved_dashboards/`: SQLite documents and production HTML persistence artifacts.
- `dataset/`: binary COPY snapshot, schema/grants manifest, discoverable-schema parity, and engine digest. Raw approved observations are retained locally; do not publish this folder blindly.
- `config.json`, `environment.redacted.json`, `questions.json`, and `source.tar.gz`: fixed configuration, dependencies, exact inputs, and tracked source. `verification.json` records integrity and secret checks.
- `case_audit.json` and `priority_references.json`: explicit grading and read-only comparison values.

The local clone remains isolated on `127.0.0.1:55432` in container `dashboard-bench-20261114`. Reader credentials live outside this folder under ignored `artifacts/local`, and are not included in results. For future comparisons, reuse this clone or restore the saved COPY files with `prepare_snapshot.py`; never recapture live data over the manifest. The current runner resumes missing cases and must not overwrite this baseline. Copy the runner to a new comparison subfolder and point it at this snapshot, retaining the configuration and recording the candidate commit. For exact replay, restore `source.tar.gz` and the dependency versions from `config.json`; update the runner source path to that restored checkout.

No application fixes or deployment were included. Browser behavior and production server environment parity remain untested.
