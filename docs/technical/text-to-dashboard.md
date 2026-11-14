# Saved Text-to-Dashboard workspace

The web app has a separate **Dashboard** tab for analytics roles. Describe a business view, create a saved dashboard, reopen it, edit tile titles/types/fields/order/width, refresh source data, or rebuild from an edited description. HTML can be opened privately or downloaded.

## Data flow

1. Inspect the authorized live SQL schema and up to three date-coverage aggregates using the existing read-only repository.
2. The configured SQL model proposes at most four natural-language data questions and eight tiles. It generates neither executable SQL nor HTML at this stage.
3. Run questions through the shared `SQLAnalyticsAgent`, including Jev, metric definitions, parameterized planning and SQL security. Two source requests can run concurrently under a 180-second build deadline.
4. Bind returned columns to tiles and compose trusted HTML/CSS/SVG. Available tiles: KPI, bar, line, donut, table, and descriptive summary. Failed or empty sources stay explicit. Incompatible charts fall back to source tables.
5. Atomically save the typed definition, returned data and HTML in private SQLite storage. Presentation edits reuse saved results; scope changes rewrite the source questions and rerun SQL. Refresh preserves the existing definition; rebuild creates a new plan within the same saved dashboard.

The legacy single-chart chat route remains a chart preview. Saved dashboards use `/api/dashboards` and are owned by the authenticated subject. Stale edits return HTTP 409. The preview iframe is sandboxed, HTML responses prohibit scripts and network access, and all data text is escaped. No arbitrary model HTML is executed.

## Local startup

From the repository root:

```powershell
.venv\Scripts\python.exe scripts/start_local_web.py
```

Open <http://127.0.0.1:8000> and select **Dashboard** after signing in with an analytics-enabled account. The same FastAPI process serves the web UI and backend; Streamlit is unnecessary. Groq configuration comes from `.env`; the launch script includes the configured third key in the provider's numbered fallback list without logging credentials.

Storage defaults to `artifacts/local/dashboards/dashboards.sqlite3`, outside the static web root and ignored by Git. `DASHBOARD_STORAGE_DIR` overrides its location. Limits: 100 dashboards per owner and 2 MB per saved document plus HTML. Local storage needs a persistent private volume and backup strategy before deployment.

## Verification and limits

The live sales smoke build saved three tiles from two approved queries for July–September 2026: monthly revenue, a descriptive summary and a total-revenue KPI. Refresh, field binding, SVG/summary generation, layout editing, stale-write rejection, reopening and authenticated HTML download were verified. The observed total revenue was 5,733,349.81 in unconfirmed source currency. Local evidence is in `artifacts/local/dashboards/live-smoke.json` and `.html`.

Checks: 25 dashboard tests, seven SQL-flow tests and five existing JavaScript renderer tests pass; both web JavaScript files pass syntax checks. A broader 111-check run passed 110 checks and encountered the existing `test_metric_candidates` import error (`KeyError: source_labels`). That separate import problem remains unresolved; the full repository suite is not claimed green.

A live scope edit to July–August 2026 rewrote both source questions, executed both queries with July 1/August 31 parameters and rendered a total-revenue KPI of 3,643,117.66 alongside the updated trend and summary. The saved sample is left in that edited state for local testing.

The latest SQL change from main, `90c46c0`, was imported as `1588a38`: returned-versus-sold questions now include order-item quantity schema. The shared SQL flow is used by this dashboard builder.

Planning still depends on Groq availability/quota and Jev clarity decisions. Output planning retains the provider's 1,000-token allowance; plans are requested in compact JSON. The current environment produced a quota rejection with a larger allowance and one transient TLS failure before a successful build. This is a focused smoke verification, not a new bilingual reliability benchmark.

Statistics describe returned observations, not an invented full population. Donut composition and unit compatibility retain existing chart safeguards. Static exports are snapshots; filters and edits happen in the app, and downloading HTML exports its visible business data. Browser automation exposed no available browser, so visual interaction review remains unverified.

## Main integration verification

The publication branch starts from current main and imports only the dashboard workspace and required chart/policy helpers. It preserves main's SQL implementation, inventory-dashboard class, report/navigation design, shared dialog and document-processing changes. The saved-dashboard API uses `runtime.analytics_agent.sql_agent`; it does not depend on replacing the legacy inventory agent.

On this checkout, 22 dashboard checks and two legacy inventory checks pass, both JavaScript files pass syntax checks, and a live authenticated build rendered a chart and descriptive summary from approved SQL results. A 65-test existing app/agent/SQL comparison produced identical failure IDs before and after integration: 24 failures and 31 errors, largely stale contracts and missing document fixtures/services. These existing checks are not reported as passing. Comparison logs, live data, benchmark snapshots and credentials are excluded from the published commits.
