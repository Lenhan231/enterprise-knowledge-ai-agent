import collections,hashlib,json,statistics
from decimal import Decimal
from pathlib import Path
OUT=Path(__file__).resolve().parent
def read(name): return json.loads((OUT/name).read_text(encoding='utf-8'))
def main():
 rows=read('results.json'); summary=read('summary.json'); config=read('config.json')
 refs=read('priority_references.json')
 passing=next(r for r in rows if r['execution_id']=='DB-07-en')
 actual=passing['dashboard']['results'][0]['payload']['rows']; expected=refs['DB-20-monthly']['observations']
 assert [Decimal(str(r['revenue'])) for r in actual]==[Decimal(str(r['revenue'])) for r in expected]
 assert [r['month'][:7] for r in actual]==[r['month'][:7] for r in expected]
 audits=[]
 for r in rows:
  passed=r['execution_id']=='DB-07-en'
  note='Line and table reuse one dataset; all three months and exact revenues match the reference.' if passed else r['error_or_clarification']
  if r['case_id']=='DB-24' and r['language']=='en': note='Metric guard refused to invent net profit margin, but the explanation incorrectly says revenue/cost data are unavailable in the inventory catalog. No monthly dashboard or accurate approved-definition limitation.'
  if r['case_id']=='DB-25': note='Stopped at invalid dashboard plan. No private data or source SQL execution, but no explicit authorization refusal; authorization safeguard not exercised.'
  if not note: note='Some requested tiles or datasets unavailable; see tile_status and SQL traces.'
  audits.append(dict(execution_id=r['execution_id'],request_fulfilled=passed,reason=note))
 (OUT/'case_audit.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf-8')
 events=[json.loads(line) for line in (OUT/'events.jsonl').read_text(encoding='utf-8').splitlines()]
 llm=[e for e in events if e['event']=='llm']
 lines=['# Dashboard benchmark — 2026-11-14','',
 '**50 local dashboard executions completed: 1 complete, 3 partial, 46 failed.** The single complete dashboard also passed an exact observation check. This configuration is not reliable for general bilingual Text-to-Dashboard requests.','',
 '| Measure | English | Vietnamese |','|---|---:|---:|']
 for label, values in [
  ('Executions',[25,25]),('Accepted final dashboard plans',[summary[x]['accepted_plans'] for x in ('en','vi')]),
  ('Complete dashboard / strict request pass rate',['1/25 (4%)','0/25 (0%)']),('Partial dashboards',[3,0]),('Failed dashboards',[21,25]),
  ('Mean total latency (seconds)',[f"{summary[x]['latency_mean_seconds']:.2f}" for x in ('en','vi')]),
  ('Median total latency (seconds)',[f"{summary[x]['latency_median_seconds']:.2f}" for x in ('en','vi')]),
  ('P95 total latency (seconds)',[f"{summary[x]['latency_p95_seconds']:.2f}" for x in ('en','vi')])]: lines.append(f'| {label} | {values[0]} | {values[1]} |')
 lines += ['', 'The aggregate strict pass rate is **1/50 (2%)**. A strict pass requires the requested representations, scope, and observations, or a clear and accurate requested fallback/refusal for negative cases. Generic planning failures do not count as successful refusals. DB-24 English held the metric guard but gave an inaccurate source explanation, so it is not a full request pass. DB-25 never reached the authorization decision. These pass rates describe one execution per question and language, not repeated-run reliability.','',
 '## Frozen run configuration','',
 f"- Code: `main` commit `{config['commit']}`; tracked worktree clean before and after. No application fixes made during measurement.",
 '- Primary provider: Cloudflare. User requested `llama-3.1-8b-instruct`; current production code aliases `@cf/meta/llama-3.1-8b-instruct` to **`@cf/meta/llama-3.1-8b-instruct-fast`**.',
 '- Temperature `0`; output limit `1000`; `enable_thinking=false`; provider HTTP timeout 30 seconds; original planner retries, SQL repairs, deadlines, and two-dataset concurrency retained.',
 f"- Production SQL fallback policy retained (Groq `{config['sql_fallback']['model']}`), but **no fallback was used**: all {len(llm)} recorded LLM calls used the same Cloudflare Llama model and none had a provider error.",
 '- Local backend functions: `app.dashboards.build`, production identity construction, persist, and HTML renderer. Identity: `finance_analyst` with analytics read permission. Latency includes build, save, and render; excludes HTTP authentication, network transport to the app, and browser rendering.',
 '- Fixed data: 15 approved commerce tables, **9,933 rows**, exported in one read-only repeatable-read transaction. Local PostgreSQL 17.6 with the recorded image digest. Column grants preserved; inaccessible invoice columns and unrelated schemas excluded. Discoverable tables, columns, keys, joins, and date fields exactly match the source role.',
 '- All 15 table COPY hashes matched after the benchmark. Snapshot artifacts and source archive are retained for future comparisons. No Supabase data was changed. The source reader exposes no primary-key or foreign-key metadata; the clone preserves that visibility.',
 '- Production knowledge metric retriever retained, but it was invoked **zero times**. No changing external knowledge affected this run.',
 '- Production parity boundary: the model was confirmed by the user and backend defaults came from latest main. Deployed server environment variables, hardware, and dependencies were not remotely inspected; do not claim a full deployment replica.',
 '- Exact attachment text preserved. Order: DB-01 through DB-25, English then Vietnamese. Exactly 50 dashboard builds; the seven reference SQL queries and coverage diagnostics are separate read-only checks, not additional agent executions.','',
 '## What failed','',
 '1. **Planning is the dominant blocker:** 38/50 final plans rejected (13 English, all 25 Vietnamese). Responses included extra authority/metric fields, missing top-level fields, undeclared query references, overlong identifiers, and invalid chart/KPI/summary dataset sharing. Raw attempts and validation errors are retained. Four rejected final outputs passed the JSON schema but failed composition rules.',
 '2. **Coverage inspection is broken before the model runs:** `inspect_data` generates MIN/MAX/COUNT queries without a LIMIT. The normal validator rejects them with `The final SELECT needs LIMIT 1..200.` The planner sees coverage unavailable even though data exists. See `coverage_profile_diagnostic.json`.',
 '3. **SQL planning and canonical metric matching still disagree:** seven source results failed canonical formula validation. Examples: DB-02 omitted the requested year grouping and wrapped SUM in CAST; DB-20 used COALESCE(SUM(...),0), while its KPI used a conditional sum without the requested year filter. These need separate treatment: harmless expression normalization must not conceal missing business/date constraints.',
 '4. **Inventory relative scope is unresolved:** latest-snapshot requests returned requests for ISO dates; another inventory interpretation changed the requested period. Source coverage failure contributes context loss, but this benchmark does not establish it as the sole cause.',
 '5. **Clarifications do not always explain the real limitation:** page views returned `monthly page views`; net profit margin was rejected with an inventory-catalog explanation despite revenue and COGS existing in sales.',
 '',
 f"Across the 12 accepted plans: {sum(r['query_count'] for r in rows)} source-query requests, {sum(r['tile_count'] for r in rows)} tiles, and {sum(r['executed_dataset_sql_count'] for r in rows)} actual dataset SQL executions. Source statuses were 4 complete, 7 failed, and 9 clarification required. No SQL execution produced a database error. The three partial dashboards were DB-06-en, DB-10-en, and DB-16-en.",
 '', '## Priority regression cases','',
 '| Case | English | Vietnamese | What this establishes |','|---|---|---|---|',
 '| DB-03 — date binding | Plan rejected: undeclared KPI dataset | Plan schema rejected | Date binding not reached. Reference has 11 observed months and revenue 18,881,151.90; December is absent. |',
 '| DB-11 — distinct orders | Plan rejected: identifiers exceed 32 characters | Plan schema rejected | Distinct-order semantics not reached. Reference category counts: Casual 11, GenZ 63, Outdoor 548, Streetwear 318; category counts can overlap. |',
 '| DB-13 — snapshot grain | Plan rejected: identifier length | Plan schema rejected | Grain safeguard not reached. Reference preserves 12 category/date observations across Sep 30, Oct 31, and Nov 13, 2026. |',
 '| DB-20 — reuse | Correct planned reuse; both SQL results fail metric validation | Plan schema rejected | Line, summary, and table share one query; KPI uses another. Planning-level reuse passes; rendering and data execution fail. Reference quarter total is 5,733,349.81. |',
 '| DB-22 — donut eligibility | Plan accepted; SQL invents sales.product_id and is stopped | Plan schema rejected | Missing-column safeguard holds. No unsafe donut rendered, but no usable table/eligibility explanation either. |',
 '',
 'DB-07 English is the only full pass: line and table share one dataset, with July 1,810,421.90; August 1,832,695.76; September 2,090,232.15. Date labels and all values match the fixed-snapshot reference.',
 '', '## Next fixes to compare against this baseline','',
 '1. Repair coverage queries to satisfy the existing SELECT bounds; use observed dates to resolve latest/last-N snapshot scope deterministically.',
 '2. Make small-model planning contracts compact and enforce server-generated identifiers/references. Keep untrusted authority fields rejected; retain permission checks independently.',
 '3. Strengthen SQL scope/grouping and known metric planning, and normalize only verified equivalent expressions. Preserve checks against missing years, invented columns, fanout, and unauthorized sources.',
 '4. Produce explicit missing-data, unsupported-metric, privacy, and donut-fallback outcomes. Re-run these same 50 prompts on the same snapshot and configuration after changes; report model changes as separate comparisons.',
 '', '## Every execution','',
 '| Execution | Status | Plan accepted | Queries | Tiles | Seconds |','|---|---|---|---:|---:|---:|']
 for r in rows: lines.append(f"| [{r['execution_id']}](executions/{r['execution_id']}.json) | {r['dashboard_status']} | {'yes' if r['planner_output_valid'] else 'no'} | {r['query_count']} | {r['tile_count']} | {r['total_latency_seconds']:.2f} |")
 lines += ['', '## Files and replay','',
 '- `results.json` / `results.jsonl`: all 50 executions, complete SQL payloads, observations, errors, raw planner validity summaries, and tile statuses. `summary.csv` is the compact index.',
 '- `events.jsonl`: prompts, raw model responses, schema validity, accepted plans, source payloads, actual SQL, parameter Python types, observations, and stage latencies.',
 '- `executions/`: one JSON per execution; HTML for every saved document, including failed/partial documents.',
 '- `saved_dashboards/`: SQLite documents and production HTML persistence artifacts.',
 '- `dataset/`: binary COPY snapshot, schema/grants manifest, discoverable-schema parity, and engine digest. Raw approved observations are retained locally; do not publish this folder blindly.',
 '- `config.json`, `environment.redacted.json`, `questions.json`, and `source.tar.gz`: fixed configuration, dependencies, exact inputs, and tracked source. `verification.json` records integrity and secret checks.',
 '- `case_audit.json` and `priority_references.json`: explicit grading and read-only comparison values.',
 '',
 'The local clone remains isolated on `127.0.0.1:55432` in container `dashboard-bench-20261114`. Reader credentials live outside this folder under ignored `artifacts/local`, and are not included in results. For future comparisons, reuse this clone or restore the saved COPY files with `prepare_snapshot.py`; never recapture live data over the manifest. The current runner resumes missing cases and must not overwrite this baseline. Copy the runner to a new comparison subfolder and point it at this snapshot, retaining the configuration and recording the candidate commit. For exact replay, restore `source.tar.gz` and the dependency versions from `config.json`; update the runner source path to that restored checkout.',
 '',
 'No application fixes or deployment were included. Browser behavior and production server environment parity remain untested.'
 ]
 (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print('Wrote REPORT.md and case_audit.json')
if __name__=='__main__': main()
