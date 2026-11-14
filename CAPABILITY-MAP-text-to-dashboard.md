# Capability map: Text-to-Dashboard

Requested outcome: a plain-language business description produces a saved, editable dashboard rendered as HTML, containing relevant tiles and statistical summaries backed by executed SQL.

The current DashboardAgent produces one chart from one SQL result. The target is a dashboard document and workspace. Existing chart builders, SQL validation and policy/metric context remain reusable components.

## Proposed boundaries

| Module ID | Responsibility | Depends on |
|---|---|---|
| dashboard-build | Inspect authorized schema and available date coverage; turn the description into a bounded tile/query plan; ask the shared SQL agent to generate and execute queries; assemble KPI, chart, table and statistical-summary tiles with source evidence and explicit partial failures. | Existing SQL agent, metric catalog, policy ontology |
| dashboard-html | Render the validated dashboard document as a complete HTML page with layout, CSS, charts, KPIs, summaries, dates and sources. Derive displayed numbers from executed results. Escape data and use controlled templates; keep generated content isolated from app privileges. | dashboard-build document |
| dashboard-store | Save the structured document and rendered HTML privately for its owner; list, load, version and update it. Keep enough query provenance to refresh safely. | dashboard-html and dashboard-build document |
| dashboard-workspace | Create from text; open saved dashboards; edit tile titles, order, size, supported visualization and data scope; save changes; explicitly refresh data; preview/open/download the HTML. Integrate with the existing app and Streamlit. | dashboard-build, dashboard-store |

Build order: dashboard-build → dashboard-html → dashboard-store → dashboard-workspace.

## Assumptions for review

- Dashboard output is a coherent multi-tile HTML page, rather than a collection of separate chart chat messages.
- The dashboard agent chooses relevant tiles and coordinates SQL questions. The shared SQL agent owns SQL generation, metric interpretation, validation and execution. The renderer consumes the resulting datasets; it does not execute model-authored HTML or SQL.
- The first tile set is KPI/value, bar, line, donut, data table and statistical summary. More chart types can be added after this complete path works.
- Statistical summaries use their declared data scope. Overall business totals/averages come from suitable SQL aggregates; the renderer must not treat an average of grouped averages as an overall average or extrapolate from truncated rows.
- Editing means dashboard controls and a revised business description: titles, tile ordering/layout, valid chart type and scoped filters. Data-scope changes regenerate or revalidate SQL before execution. A raw HTML/SQL code editor is not part of this first scope.
- Save both a structured dashboard definition/results snapshot and HTML. Reopening shows the saved snapshot and its data timestamp; refreshing is explicit. The HTML is the presentation artifact, while the structured document makes editing reliable.
- Saved dashboards require signed-in analytics access and owner isolation. Saving a dashboard never grants access to additional sources, other users' dashboards or credentials.
- Start with at most eight tiles and four source queries, reuse datasets across tiles, and enforce a bounded build deadline. Show failed/unavailable tiles explicitly instead of inventing results or silently changing the requested period.
- Reuse existing application storage conventions where suitable; otherwise begin with configured persistent backend storage without adding a graph database or an analytics-schema migration. Confirm durable deployment storage before calling saved dashboards production-ready.
- Existing single-chart behavior may be retained as a compatible tile/preview path during migration, but the completed Dashboard mode creates a saved dashboard with an open/edit identity.

## Acceptance targets for the subsequent module specs

1. A description such as “May 2026 sales overview: revenue, order count, category comparison and a monthly trend” produces one dashboard with several query-backed tiles.
2. Every tile traces to SQL, parameters, source tables, period, units and observed results; unavailable data and partial failures are visible.
3. The generated HTML opens as one responsive dashboard, with safe rendering of untrusted labels and content.
4. The owner can close the chat/app, reopen the saved dashboard, edit it and save a new revision.
5. An unrelated user cannot list, read, modify, refresh or fetch the HTML of another owner's dashboard.
6. Refreshes and data-scope edits retain the shared SQL/security boundary. A clarity decision cannot authorize unsafe SQL.

## Review status

Proposed capability map for user review. Module specs, implementation plan and implementation follow after the boundaries and editing scope are reviewed. The preceding query/chart improvements are preserved; they are not the complete Text-to-Dashboard feature.
