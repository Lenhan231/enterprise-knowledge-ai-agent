# Dashboard readability and live overview (#60)

Issue: https://github.com/Lenhan231/enterprise-knowledge-ai-agent/issues/60

Dashboard tables, KPI values, chart axes, tooltips and totals use Vietnamese grouping. Counts and monetary values round to integers; percentages use at most one decimal. Original observations remain unchanged. Timestamps use `dd/MM/yyyy HH:mm` in `Asia/Ho_Chi_Minh`; monthly and daily chart labels use `MM/yyyy` and `dd/MM`. SQL provenance keeps exact parameter values.

Currency symbols require a unique currency value projected transparently from the approved invoice currency column. A SQL literal or a currency guess cannot establish currency. Unconfirmed revenue has no symbol.

The standalone homepage opens after login or session restoration and fetches `/api/dashboards/overview`, independently of saved dashboard actions. Returning home reuses the rendered overview for five minutes within the current browser session; concurrent visits share an in-flight request. Refresh always bypasses this temporary cache. Logout, account/session changes and loss of analytics access discard it. Failed overviews are not cached. The sidebar logo returns home; no overview tab is added. Dashboard, Reports and General Chat remain separate tabs, and opening Dashboard loads only the saved-dashboard workspace. Accounts without analytics access see a homepage access message without querying analytics. The homepage does not create a saved artifact or call an LLM. The three fixed datasets are:

- Product stock composition at the latest observed inventory snapshot, with five products and all remaining products grouped as Other products. Missing or negative balances make composition unavailable.
- The ten largest categories by delivered order-item quantity across available order history.
- Company revenue for the latest twelve observed calendar months, displayed chronologically. Missing months are not invented.

Each query uses existing authorization, SQL validation, deployed source allowlists and the read-only repository. Individual source failures leave other charts and saved dashboards available. No shared result cache is introduced. Latest-response guards prevent account changes or slower previous refreshes from replacing current content. The shared HTML/SVG renderer stacks chart tiles on narrow screens.

Tests cover formatting, source currency provenance, exact parameters, endpoint RBAC, no persistence/model calls, source failures, deployment allowlists, refresh/account lifecycle, snapshot selection and top-five/Other aggregation. Opt-in PostgreSQL tests use read-only VALUES fixtures via `DASHBOARD_OVERVIEW_TEST_URL`; they never modify source tables. Local verification also compared all three live datasets with direct queries through the application read-only connection.

Verification logs and the live comparison are under `artifacts/local/issue-60/`. Visual browser/mobile inspection was unavailable in this session. Source completeness and currency remain explicitly unconfirmed when the source does not establish them.

Local results: dashboard discovery ran 172 tests with 163 passing and 9 opt-in skips; all 14 focused tests passed with PostgreSQL enabled, including both read-only SQL fixture tests; all 13 browser unit tests passed. All three live source comparisons matched. The restarted local app returned HTTP 200 for health and the new formatting asset, and OpenAPI included the overview route.

Homepage follow-up: all 19 browser checks passed, including standalone home navigation, one overview fetch per login, slow login metadata, keyboard access, logout/account isolation and separate dashboard/report flows. The focused Python regression suite passed 18 tests with 2 opt-in PostgreSQL skips. The local page and new homepage asset returned HTTP 200.
