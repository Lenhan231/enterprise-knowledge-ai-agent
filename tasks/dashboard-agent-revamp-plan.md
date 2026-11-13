# Dashboard agent revamp proposal

Date: 2026-11-13. Status: implemented locally. See [implementation and verification](../docs/technical/dashboard-agent.md). The stockout chart is verified through the live model/SQL flow after key configuration and the repeated-date fix; broader live coverage and browser visual review remain outstanding.

## Objective and assumptions

Replace the fixed Inventory Control response with a question-driven chart built from validated SQL results. The SQL agent owns query interpretation, generation, validation, and execution; the dashboard agent owns the chart specification. Deliver one useful chart per request, a data table, sources, time scope, and limitations.

Assume “provided data” means the approved Supabase commerce sources already available to SQLAnalyticsAgent. Arbitrary uploaded CSVs, raw document tables, and public-schema extraction records are not currently approved SQL sources; supporting those requires a separate ingestion/authorization design. Keep Dashboard as an explicit mode; preserve Auto's existing Knowledge/SQL scope.

## Inspection findings

- `src/core/agents/dashboard_agent.py`: InventoryDashboardAgent executes five fixed queries against commerce.inventory. The question does not determine the metric, grouping, or date. SQLAnalyticsAgent is used only for authorization.
- `src/core/agents/sql_analytics_agent.py`: already returns bounded rows, SQL, parameters, query status, column/metric metadata, evidence, and limitations. It includes ambiguity checks, semantic validation, and failure handling. Reuse `run_payload`; do not create another SQL generator.
- `src/core/database/commerce_repository.py`: revalidates approved SELECTs, checks the reader role, executes read-only transactions, and enforces a 7.5-second database timeout. The SQL validator caps results at 200 rows. Preserve these controls.
- Wiring exists in both `src/app/agents.py` and `src/core/agents/main.py`. Both currently inject the repository directly into Dashboard rather than the existing SQL agent.
- `src/app/static/app.js`: renderDashboardVisualization consumes `data.visualization`, accepts only line charts, and assumes fiscal-year labels and a nonnegative scale. The fixed dashboard instead emits `data.dashboard`, so it does not reach this renderer.
- `src/core/agents/streamlit_ui.py`: recognizes the fixed inventory outline and renders KPI cards, bar charts, and exception rows. Rate formatting checks also need coverage: mean_fill_rate matches the generic rate branch before its fractional-rate branch.
- `src/core/agents/router.py`: explicit SQL mode has conversation-state and timeout handling; Dashboard does not use that path. Shared SQL ownership must also avoid closing the same repository/provider twice.
- `evaluation/agent_benchmarks/dashboard_static_outlines.json` defines older fixed outlines; update its applicable contract when replacing this behavior.

## Live Supabase evidence

Inspected project FA26AI69 (`ciiztxhbxtkxferpmyet`) using read-only schema and aggregate queries. These are exact profile counts from 2026-11-13, not freshness guarantees.

| Source | Rows | Date coverage | Useful dimensions |
|---|---:|---|---|
| commerce.inventory | 60,247 | 2012-07-31 to 2022-12-31; 126 snapshots | Four categories, products, flags |
| commerce.sales | 3,833 | 2012-07-04 to 2022-12-31 | Date, revenue, COGS |
| commerce.web_traffic | 3,652 | 2013-01-01 to 2022-12-31 | Six traffic sources, sessions |
| commerce.invoices | 17 | 2026-08-13 to 2026-10-28 | Buyer, seller, dates; all currency values NULL |

The database supplies chartable data; it does not prescribe exactly three app chart types. Recommend these three for the revamped app:

| Type | Verified example | Eligibility |
|---|---|---|
| Line | Monthly revenue in 2022: 12 returned observations | Ordered date axis plus numeric measure; at least two observed dates |
| Bar | Stockout count by category on 2022-12-31: Casual 31, GenZ 25, Outdoor 95, Streetwear 134 | Categorical dimension plus numeric measure; grouped bars for multiple comparable series |
| Donut | Session share by traffic source in 2022: six sources, all positive totals | One additive, nonnegative measure over mutually exclusive categories, with a positive complete total |

Donut examples returned direct 695,578; email_campaign 1,246,661; organic_search 3,569,310; paid_search 2,623,117; referral 841,332; social_media 2,087,660 sessions. This represents recorded session share, not unique-person share or causal marketing impact.

Inventory stockout/overstock flags overlap (including 109 overlapping observations in Streetwear at the latest snapshot). Never turn those flags into exclusive donut slices. Do not sum stock balances across snapshots. Do not label commerce amounts USD/VND: currency is unverified; invoice currency is currently missing.

## Proposed flow and contract

`Explicit dashboard request -> existing SQLAnalyticsAgent.run_payload -> validated rows -> validated chart mapping -> data.visualization -> Web/Streamlit renderer`

1. Preserve the original request, verified identity, question, filters, conversation scope, and server-owned SQL context. Reject requests without analytics:read through the existing SQL path.
2. Execute the existing SQL workflow once. If it requests clarification, fails validation, times out, or returns no rows, propagate that state without constructing a chart or falling back to unrelated inventory data.
3. Select a chart from the user's explicit type and the returned column/metric metadata. Automatic rules: time series -> line; categorical comparison -> bar; explicit composition request -> donut only when eligibility is established. Ask when multiple fields/units create a material ambiguity. A chart keyword alone must not satisfy the SQL ambiguity gate; the actual metric and required scope must remain clear.
4. Retain the existing visualization shape (`type`, `title`, `categories`, `series`, `unit`) where practical, adding axis labels and period/coverage information. Allow only `line`, `bar`, `donut`; series values must come directly from the validated result columns. Define this small schema beside the existing agent models using Pydantic. Do not accept model-generated HTML, JavaScript, SQL in chart metadata, or invented values.
5. Keep raw rows, evidence, SQL, parameters, query status, and limitations in AgentResult. Represent SQL failure and chart-ineligible results distinctly. A successful query may still produce only a table with a clear reason.
6. Render the same chart contract in both clients. Include readable axes/legend, tooltips, an accessible data table, responsive layout, and source/date captions. Correct negative-value scales and remove fiscal-year assumptions. Preserve null gaps rather than turning missing observations into zero.

Chart limits: keep the SQL row cap; use readable category counts and request SQL aggregation/coarser grain when necessary. Never silently truncate a donut denominator. Display an explicit top-N subset as such; only include an Other slice when its value is supplied by validated SQL. Do not combine incompatible units or currencies into one series group.

## Ordered implementation and checkpoints

| Slice | Main files / reach | Acceptance and verification |
|---|---|---|
| 1. Chart contract and mapping | core/models/agents.py, core/agents/dashboard_agent.py, tests/test_inventory_dashboard.py | Mock SQL result rows; cover line/bar/donut mappings, ambiguous columns, nulls, invalid numbers, negative values, overlapping flags, and table-only results. No repository query logic in Dashboard. |
| 2. Runtime delegation | app/agents.py, core/agents/main.py, core/agents/router.py, tests/test_app_chat.py, tests/test_sql_followups.py | Inject the existing SQL agent into both runtimes; preserve permissions, deadlines, SQL scope and clarification replies. Reuse the SQL conversation machinery with a dashboard-specific namespace; keep selected_route=dashboard and isolate users. Dashboard borrows the SQL agent and does not own its close lifecycle. |
| 3. Web charts | app/static/app.js, app/static/index.html, app/static/styles.css, tests/test_app_request_models.py, new focused renderer check if needed | All three chart types render from data.visualization; escaping, negative axes, long labels, gaps, sources, and accessible tables verified. Rename Inventory agent entry to Dashboard and replace the fixed launch prompt with supported examples. Use existing SVG approach before adding a dependency. |
| 4. Streamlit charts | core/agents/streamlit_ui.py, tests/test_streamlit_ui.py | Same payload and failure states as Web; replace the inventory-only controls with request-driven charts. Use installed native chart support; check installed capabilities before choosing donut rendering. |
| 5. Retire obsolete contracts and document | tests/test_document_dashboard.py, evaluation/agent_benchmarks/dashboard_static_outlines.json, docs/technical/dashboard-agent.md | Replace obsolete DashboardAgent/_financial_time_series assumptions with current commerce contracts; update benchmark expectations and supported examples. Remove obsolete code only after both clients consume the new shape. |

All five implementation slices are complete locally, including focused tests. No DB schema changes, chart persistence, generic dashboard builder, or Auto routing expansion were introduced. Live model acceptance and browser visual review remain outstanding.

## Verification commands and success criteria

Run with the repository virtual environment from PowerShell:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_inventory_dashboard.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_document_dashboard.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_sql_followups.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_app_chat.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_streamlit_ui.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_app_request_models.py -v
node --check src/app/static/app.js
```

Also run the relevant SQL safety/metric suites after any SQL changes. Verify all three examples end to end under a verified analyst identity in both clients. Compare displayed values with independent read-only SQL; verify unauthorized requests execute no query, ambiguous requests request clarification, SQL_INVENTORY_ONLY=true cannot access sales/traffic, empty/failing sources produce no misleading chart, and filters persist correctly across clarification replies. Check narrow-screen rendering and keyboard/data-table access.

Baseline observed: current inventory-dashboard suite passes (2 tests). Old document-dashboard suite fails at import because DashboardAgent and _financial_time_series no longer exist. System Python also lacks sqlglot; use .venv. No full suite or live model-to-chart test was run during planning.

Always preserve SQL safety, permissions, provenance, null semantics, historical dates, and existing API agent_mode=dashboard. New schema changes, dependencies, or arbitrary upload support require an explicit scope decision. Never expose database secrets or synthesize chart numbers.
