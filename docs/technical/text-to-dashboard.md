# Saved dashboard workspace

The Dashboard tab starts with a chat-style request and a separate optional scope. Clarification stays in the composer; the workspace opens after usable outputs are available. Users can edit layouts, refresh data, rebuild requirements and download private HTML.

## Query and output flow

1. The API uses the shared SQL engine, supporting either a raw runtime or a wrapper exposing `sql_agent`.
2. A server-owned dashboard context asks the existing SQL call to return an `outputs` manifest alongside one query or a bundle of at most two independent queries. Each output binds a supported kind, query index, dimension and returned measures. IDs are assigned by the server.
3. Validate SQL, parameters, approved sources, canonical metrics, period, output references and grain before executing data queries. Overall KPIs need an overall aggregate query. Chart rows are never summed into a KPI.
4. Render declared line/bar/donut/table/KPI/summary outputs and check them against the returned observations before saving. Invalid output plans receive the SQL runtime's bounded repair attempt, then clarify without executing. Incompatible charts, KPIs and summaries stay in chat with usable alternatives.
5. Save the definition, observations and escaped HTML atomically. A source failure can produce a visibly partial dashboard when another query succeeds. Empty results remain unknown rather than becoming zero.

Each new build permits at most two queries, eight outputs and two explicitly mapped charts per dataset, within the 180-second build budget. Existing legacy documents retain their saved query capacity. Multiple charts and summaries can share one result, with source observations shown once per dataset.

Descriptive summaries cover returned aggregate observations only. They follow SQL column lineage through CTEs, subqueries and aliases, exclude raw identifiers/window calculations, preserve NULLs and can bind measures without a chart. Statistics within each month/group, unsupported chart types, cross-result calculations and broader cross-domain interpretation remain deferred. Unsupported requirements must be clarified rather than silently converted into another output.

## Clarification and scope

Drafts use the existing ConversationStore with owner/permission isolation, expiry, bounded capacity and at most three replies. Clients send a message and opaque conversation ID; history and target dashboard identity remain server-owned. No clarification or wholly failed source result creates a saved dashboard.

The original description and shared scope survive clarification. Recognized conflicting periods are rejected. Keep frequently edited dates in the scope field. Refresh reruns saved questions and preserves edited tile definitions; Rebuild selects new outputs for the revised description. Old dashboards need Rebuild to add newly requested outputs. Clarification continuations retain revision checks and preserve the saved dashboard until a successful replacement.

Model interpretation remains responsible for translating prose into requirements. Manifest validation proves consistency with SQL and rendering; it does not guarantee perfect interpretation of arbitrary language.

## Model cost and upstream compatibility

There is no separate dashboard planner, requirement-extraction model or narrative call. Inventory outputs are declared alongside its existing typed interpretation and compiled without an additional model call. Other new builds use SQL generation for the manifest, including requests that previously used only a deterministic compiler. A valid two-query plan can come from one generation response. Repair/failover can still add attempts.

Refresh generates saved queries separately when required. Main's deterministic annual-revenue compiler is preserved, including its source-completeness limitation, so eligible annual KPI refreshes need no SQL-generation call. Auto orchestration and final response synthesis remain unchanged by the dashboard integration.

The local launcher selects Groq and includes the third configured key in its numbered key list. Rate/quota limits rotate configured keys without changing the model. Groq exhaustion returns a failure instead of falling back to Cloudflare. Credentials stay outside source and logs.

## UI and security

The UI reuses the application's authentication, API client and General Chat patterns. Enter sends; Shift+Enter inserts a newline. New clears request drafts, account changes clear private state, and late responses cannot restore another account's dashboard. The original scope cannot be replaced by generated content.

Saved documents are owner-scoped and revision-checked. Write routes enforce same origin. Preview HTML is sandboxed, escapes all data, prohibits scripts/network access and never inserts model HTML into the privileged app. The SQL engine retains schema/function/parameter/read-only limits and server-verified analytics permissions.

## Run locally

```powershell
.venv/Scripts/python.exe scripts/start_local_web.py
```

Open http://127.0.0.1:8000/ and sign in with an analytics-enabled account. The same FastAPI process serves the UI and API. Configure the existing database/provider environment variables; no OpenRouter/Jev credential is required.

Storage defaults to `artifacts/local/dashboards/dashboards.sqlite3`; `DASHBOARD_STORAGE_DIR` can override it. Limits are 100 dashboards per owner and 2 MB for each document plus HTML. Production storage needs a private persistent volume and backups.

## Verification

Tests cover raw/wrapped runtimes, clarification isolation, query/output bounds, pre-execution rejection, two-query trend/KPI/summary plans, CTE lineage, NULLs, partial sources, persistence, optimistic revisions, refresh and scoped data. Provider/database transports are mocked in these tests.

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -p 'test_dashboard*.py'
python -m unittest discover -s tests/sql
node --test tests/test_dashboard_scope.cjs tests/test_dashboard_workspace.cjs
node --check src/app/static/dashboard.js
```

The integration is based on main rather than an older branch snapshot, preserving newer SQL/Auto and web UI changes. Full-suite failures are compared with a clean-main baseline; a passing focused suite is not a claim that the entire repository is green. Visual-browser and live-provider testing are separate from mocked regression checks.

## Table fields and environment consistency

Tables may explicitly select grouping columns (dates, categories, IDs) alongside their measures; those fields remain forbidden as numeric chart/KPI/summary measures. The table grouping metadata does not request client-side aggregation: the SQL result still supplies the observations. This distinction prevents valid chart-plus-table requests from being rejected depending on which equivalent table mapping the model returns.

SQL defaults to Groq in both the server and local launcher. With no SQL_GROQ_MODEL override, Groq uses GROQ_MODEL (default qwen/qwen3.8-27b). The example environment now leaves SQL_GROQ_MODEL empty instead of selecting another model. Explicit deployment overrides remain authoritative; source code does not rewrite a running server's environment. For exact local/hosted parity, configure SQL_LLM_PROVIDER=groq and SQL_GROQ_MODEL=qwen/qwen3.8-27b in both environments. The model used by a hosted server cannot be inferred from its Git branch or from a validation error alone.
