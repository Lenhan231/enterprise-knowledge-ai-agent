# SQL-backed dashboard agent

Dashboard is an explicit agent mode that produces one line, bar, or donut chart from the existing SQL agent's approved Supabase sources. It is available in the web app and Streamlit. Auto remains scoped to Knowledge and SQL.

## Run and try

Use the repository virtual environment. Configure the existing backend credentials, including `ANALYTICS_DATABASE_URL`, `GROQ_API_KEY`, and `OPENROUTER_API_KEY`. The SQL agent requires OpenRouter's Jev ambiguity check before querying; a missing key returns a failed response without executing SQL. Do not disable the check to get a chart.

From PowerShell at the repository root:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
.venv/Scripts/python.exe -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
.venv/Scripts/python.exe -m streamlit run src/core/agents/streamlit_ui.py --server.address 127.0.0.1 --server.port 8501
```

Open http://127.0.0.1:8501, sign in with an account allowed to read analytics, select **Dashboard**, and try:

- `Show a line chart of monthly revenue during 2022.`
- `Show a bar chart of stockout count by category at 2022-12-31.`
- `Show a donut chart of session share by traffic source during 2022.`

Explicit line/bar/donut wording determines the requested type. Pie is rendered as donut. Without an explicit type, date series use line and category comparisons use bar; explicit share/composition requests use donut. Incompatible data returns a table and a reason instead of a misleading chart. When a choice of measure or grouping is ambiguous, restate the request with one dimension and compatible measures.

## Data flow and response

`agent_mode=dashboard -> DashboardAgent -> SQLAnalyticsAgent.run_payload -> validated rows -> ChartSpec -> Web/Streamlit`

Both backend entrypoints inject the same SQL agent used by Analytics. Dashboard borrows that agent and does not close its repository or provider. SQL authorization, allowlists, parameterization, metric validation, read-only transactions, row caps, and timeouts remain in the existing SQL workflow.

Existing `metadata.category` requests retain length/type validation and forward the category as explicit question context to the SQL agent; the dashboard never interpolates it into SQL. New clients should express filters in their question.

Requests and endpoints retain their current shape. Successful results preserve `rows`, `sql`, `parameters`, `query_status`, evidence, and limitations. `data.visualization` supplies:

```json
{
  "type": "bar",
  "title": "Sessions by source during 2022",
  "categories": ["direct", "organic_search"],
  "series": [{"name": "Sessions", "values": [10, 20]}],
  "unit": "sessions",
  "x_label": "Traffic source",
  "y_label": "sessions",
  "temporal": false,
  "scope": {"sources": ["commerce.web_traffic"]}
}
```

The example numbers above illustrate the wire shape, not actual observations. Series are aligned with categories; nulls remain gaps. The specification permits at most 200 categories and four comparable series. A date axis is chronologically sorted, and temporal line positions reflect actual date intervals. Source rows retain their original order and values.

`metadata.chart_status` is `rendered`, `table_only`, or `unavailable`. `table_only` includes `chart_reason`; the SQL query succeeded but its result is unsuitable for a supported chart. SQL clarification, failure, or empty results produce no visualization. The removed `data.dashboard` inventory outline is superseded by `data.visualization`.

The router uses a separate dashboard conversation store with the existing user/permission isolation and expiry. Clarification replies include the pending chart question. Inventory follow-ups reuse the SQL agent's semantic scope; non-inventory follow-up changes should restate their full scope because the SQL agent's accepted-scope memory is inventory-specific. No prior result rows are reused as evidence.

## Chart constraints

- Numeric values come from executed SQL, never a chart-generation model call. Labels are escaped in the web renderer. Both clients show source tables and a data table.
- Line charts require a temporal dimension and at least two observed values. Bar charts allow negative values and grouped comparable measures. No chart combines incompatible units.
- Donut charts accept only simple single-table, complete category groups with one nonnegative additive measure and a positive total. Supported sums cover sales revenue/COGS, traffic sessions/page views, and inventory stock/movement units; simple row counts are also eligible. Joins, CTEs, filtered aggregates, HAVING, OFFSET, distinct counts, and potentially truncated results remain table-only. Extend this only with an independent completeness/provenance check.
- Inventory stockout and overstock flags overlap and must not become exclusive donut slices. Stock balances must remain scoped to individual snapshots.
- Preserve actual historical coverage: inspected commerce data ends in 2022. Monetary labels do not assume USD/VND. Invoice monetary charts require one non-null currency group; current inspected invoice rows have no currency.
- Arbitrary uploads, public extraction tables, saved charts, multiple charts per request, and database schema changes are outside this implementation. `SQL_INVENTORY_ONLY=true` still restricts accessible sources.

## Verification

### Reliability follow-up (2026-11-13)

Jev now reuses an OpenAI SDK client with SDK retries disabled. The application permits two attempts, eight seconds each, within a twenty-second gate budget and the existing request deadline. Connection failures and HTTP 429/502/503/504 can retry once when the retry window and next attempt fit. Auth failures and invalid responses fail immediately; no query runs when the gate fails. The threshold remains 0.8. Existing approved metric definitions and source descriptions are included in the decision context.

Failure metadata uses `jev_auth_failed`, `jev_timeout`, `jev_unavailable`, or `jev_invalid_response`, plus `retryable`, `jev_attempts`, `jev_elapsed_ms`, and `jev_http_status` when available. Successful decision metadata includes attempts and elapsed time. Both clients distinguish clarity-service failure from a clarification request. A genuine low-confidence decision asks for source, metric, grouping, and period.

Ranking parsing now preserves “10 inventory products”, English number words, and Vietnamese one-to-ten words; conflicting limits and values outside 1–200 are rejected. Page-view wording selects web traffic; imperative “Return the month” does not select merchandise returns. Compact/hyphenated bar/line chart wording is recognized. Product-ID categories avoid duplicate display-name ambiguity, with names retained in the table.

See the [implementation checklist](../../tasks/dashboard-agent-improvements.md) and [comparison report](../../artifacts/evaluation/dashboard-bilingual-2026-11-13/COMPARISON.md) for verification and remaining limitations. The original baseline remains unchanged.

Final follow-up verification: 84 focused Python tests and five renderer tests pass. The alternate-key live rerun scores 36/50 against fresh control 29/50; the additional chart set scores 9/12 strict, with all six positive chart cases passing. Neither alternate-key cohort encountered provider failures. The SQL interpreter still mistakes two independent stockout/overstock counts for an intersection count in both supplemental languages; its donut is rejected but its table is wrong. One English mixed-unit prompt stops at Jev clear probability 0.79. These are retained acceptance failures, not claimed fixes. Backend and Streamlit were restarted and their health checks passed; browser visual review remains outstanding.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_inventory_dashboard.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_sql_followups.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_streamlit_ui.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_bounded_execution.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_jev_sql_gate.py -v
node --test tests/test_dashboard_renderer.cjs
node --check src/app/static/app.js
```

Tests cover mapping, aligned/finite values, nulls, negative scales, chart eligibility, escaping, unequal date intervals, API serialization, shared runtime injection, permission denial, clarification isolation, timeouts, and Streamlit's actual chat/rendering path. Streamlit runtime checks mock HTTP responses; they do not bypass the deployed ambiguity gate.

Read-only live-repository checks on 2026-11-13 verified 12 monthly revenue observations, four stockout categories, and six traffic-source totals. After configuring `OPENROUTER_API_KEY`, the stockout request was also verified through the live Jev/model/SQL/chart flow, including a pending clarification that repeats the snapshot date. It returned Casual 31, GenZ 25, Outdoor 95, and Streetwear 134 for 2022-12-31. Browser visual and keyboard verification and broader live prompt coverage remain outstanding; renderer tests and Streamlit AppTest are not a substitute for that review.

Follow-up fix: date validation now deduplicates repeated mentions of the same ISO snapshot date. Previously, the previous question and clarification reply could both mention 2022-12-31, causing a correct single-snapshot query to be rejected as a mismatched range. The regression test failed before the fix; 40 focused snapshot, temporal, dashboard, and SQL follow-up tests passed afterward. Wrong dates and genuinely distinct date scopes remain rejected.

Local verification: 58 focused Python tests and five Node renderer tests passed, as did JavaScript syntax and diff whitespace checks. A full-suite run during implementation executed 879 tests, with 58 failures, 97 errors, and 31 skips. Untouched HEAD executed 857 tests, with 56 failures, 90 errors, and 31 skips. Removing the obsolete document-dashboard imports exposed eight retained repository tests with stale APIs/assertions; their methods were not changed. The remaining retrieval-search-count difference also reproduces on untouched HEAD when the local environment is loaded. The full repository suite is not green; these unrelated failures were not repaired as part of the dashboard revamp. The final legacy-category regression was verified separately after that full-suite run.
