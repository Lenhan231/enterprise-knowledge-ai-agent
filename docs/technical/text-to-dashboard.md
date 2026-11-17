# Saved dashboard workspace

The Dashboard tab starts with a chat-style request and a separate optional scope. Clarification stays in the composer; the workspace opens after usable outputs are available. Users can edit layouts, refresh data, rebuild requirements and download private HTML.

## Query and output flow

1. The API uses the shared SQL engine, supporting either a raw runtime or a wrapper exposing `sql_agent`.
2. A server-owned dashboard context asks the existing SQL call to return an `outputs` manifest alongside one query or a bundle of at most three independent queries. Each output binds a supported kind, query index, dimension and returned measures. IDs are assigned by the server.
3. Validate SQL, parameters, approved sources, canonical metrics, period, output references and grain before executing data queries. Overall KPIs need an overall aggregate query. Chart rows are never summed into a KPI.
4. Render declared line/bar/donut/table/KPI/summary outputs and check them against the returned observations before saving. Invalid output plans receive one repair attempt, then fail without executing; a generation failure does not ask the user to clarify. Inventory output repair preserves the validated interpretation and compiled SQL. Incompatible charts, KPIs and summaries stay in chat with usable alternatives.

Chart output grouping may repeat its single dimension; the validator normalizes that redundant metadata before rendering. Additional chart dimensions and grouped KPI/descriptive statistics remain unsupported. SQL date-scope and aggregation checks still apply independently.
5. Save the definition, observations and escaped HTML atomically. A source failure can produce a visibly partial dashboard when another query succeeds. Empty results remain unknown rather than becoming zero.

Each new build permits at most three queries, eight outputs and two explicitly mapped charts per dataset, within the 180-second build budget. Existing legacy documents retain their saved query capacity. Multiple charts and summaries can share one result, with source observations shown once per dataset.

Descriptive summaries cover returned aggregate observations only. They follow SQL column lineage through CTEs, subqueries and aliases, exclude raw identifiers/window calculations, preserve NULLs and can bind measures without a chart. Statistics within each month/group, unsupported chart types, cross-result calculations and broader cross-domain interpretation remain deferred. Unsupported requirements must be clarified rather than silently converted into another output.

## Clarification and scope

Drafts use the existing ConversationStore with owner/permission isolation, expiry, bounded capacity and at most three replies. Clients send a message and opaque conversation ID; history and target dashboard identity remain server-owned. No clarification or wholly failed source result creates a saved dashboard.

When SQL succeeds but a representation is incompatible, the private draft retains the
retrieved document within the existing conversation size/expiry limits. A recognized
representation-only reply changes the selected tile on that same document: no model or
analytics query runs, measures/rows/scope stay fixed, and other tiles retain their choices.
New measures, sources, filters, grouping or time constraints use the query workflow.
Overrides apply to declared output manifests as well as inferred tiles. Cached results
retain owner/permission binding and target revision checks. Oversized results return a
clear request to start a new dashboard with an explicit table representation instead of
silently dropping the draft or requerying during a display-only change.

The original description and shared scope survive clarification. Recognized conflicting periods are rejected. Keep frequently edited dates in the scope field. Refresh reruns saved questions and preserves edited tile definitions; Rebuild selects new outputs for the revised description. Old dashboards need Rebuild to add newly requested outputs. Clarification continuations retain revision checks and preserve the saved dashboard until a successful replacement.

Model interpretation remains responsible for translating prose into requirements. Manifest validation proves consistency with SQL and rendering; it does not guarantee perfect interpretation of arbitrary language.

## Model cost and upstream compatibility

There is no separate dashboard planner, requirement-extraction model or narrative call. Inventory outputs are declared alongside its existing typed interpretation and compiled without an additional model call. Other new builds use SQL generation for the manifest, including requests that previously used only a deterministic compiler. A valid plan with up to three queries can come from one generation response. Repair/failover can still add attempts. Format normalization lifts per-query output bindings and applies the existing server row cap to a missing final LIMIT; read-only, schema, function, parameter and join checks still run before execution. Explicitly requested representations cannot be silently omitted. A scalar summary query may be replaced by a renderer summary only when source fields and filter populations provably match the chart observations.

The canonical SQL runtime, shared metric mapping and SQL prompts are kept identical to main. The one authorized shared-validator change normalizes standard calendar month abbreviations before date-scope parsing, so abbreviated ranges retain their starting month and exact dates retain their day. `core/dashboards/sql_runtime.py` supplies request-local dashboard extensions around that runtime: count contracts, bounded inventory/output repair and accurate failure classification. Non-dashboard SQL callers retain main's behavior and provider instance. Dashboard calls use an explicit bounded JSON response contract on the same configured Groq model, with a 2048 output-token cap and the existing low reasoning setting. Provider key rotation remains shared. Concurrent dataset refreshes do not share repair state.

Refresh generates saved queries separately when required. Main's deterministic annual-revenue compiler is preserved, including its source-completeness limitation, so eligible annual KPI refreshes need no SQL-generation call. Auto orchestration and final response synthesis remain unchanged by the dashboard integration.

The local launcher selects Groq and includes the third configured key in its numbered key list. Rate/quota limits rotate configured keys without changing the model. Groq exhaustion returns a failure instead of falling back to Cloudflare. Credentials stay outside source and logs.

## UI and security

The UI reuses the application's authentication, API client and General Chat patterns. Enter sends; Shift+Enter inserts a newline. New clears request drafts, account changes clear private state, and late responses cannot restore another account's dashboard. The original scope cannot be replaced by generated content.

Saved documents are owner-scoped and revision-checked. Write routes enforce same origin. Preview HTML is sandboxed, escapes all data, prohibits scripts/network access and never inserts model HTML into the privileged app. The SQL engine retains schema/function/parameter/read-only limits and server-verified analytics permissions.

## Run locally

```powershell
.venv/Scripts/python.exe scripts/start_local_web.py
```

Open http://127.0.0.1:8000/ and sign in with an analytics-enabled account. The same FastAPI process serves the UI and API. Configure the existing database/provider environment variables; main's schema selector uses OpenRouter/Jev when configured and falls back to its schema heuristics otherwise. This can add an upstream model call; dashboard extensions do not replace or disable it.

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

SQL defaults to Groq in both the server and local launcher. With no SQL_GROQ_MODEL override, Groq uses GROQ_MODEL (default qwen/qwen3.8-27b). The example environment now leaves SQL_GROQ_MODEL empty instead of selecting another model. Explicit deployment overrides remain authoritative; source code does not rewrite a running server's environment. For exact local/hosted parity, configure SQL_LLM_PROVIDER=groq and SQL_GROQ_MODEL=openai/gpt-oss-20b in both environments (the current hosted selection). The model used by a hosted server cannot be inferred from its Git branch or from a validation error alone.

Dashboard builds and refreshes reject upstream unverified SQL/metric fallbacks. General SQL chat retains those upstream capabilities.

When a combined chart cannot render but its measures form two valid compatible groups, presentation separates
them into charts of the same type using the existing result. This adds no SQL or model call, preserves the
two-chart-per-dataset and eight-tile limits, and leaves explicit single-chart requests for clarification.
If separation cannot fit, clarification also lists supported separate-chart alternatives.

Inventory interpretation and repair include the full dashboard clarification history and recognized requested
metrics. For latest-snapshot requests within an explicit date range, the dashboard resolves the latest recorded
snapshot inside that range using a parameterized, authorized MAX query, independently of category/metric filters.
It passes the resolved date through the unchanged SQL runtime and retains the original range and chosen date in
result metadata. An empty period is unsupported, not another request to clarify already supplied requirements.

Independent fact sources and different requested grains use separate datasets, while outputs sharing a
source set, grain and filters reuse one. The dashboard adapter validates all three plans through main's
existing per-query guards before any dataset executes. Initial bundles retain sequential execution;
refresh permits at most two concurrent queries. Cross-result calculations remain unsupported.
The dashboard prompt removes conflicting single-result CTE advice and supplies explicit inclusive/exclusive
date bounds from the existing scope parser. It does not rewrite model-generated date filters.

Validation failures report their actual bounded cause and preserve the original request, rather than asking
the user to clarify already supplied requirements. This adds no explanatory model call. Genuine business
clarifications still use the interactive draft flow. Redundant chart styles chosen automatically can be
consolidated before rendering; explicit user chart choices and saved layout edits are preserved.
