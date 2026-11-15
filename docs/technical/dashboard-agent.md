# Dashboard agent

Saved dashboards use the SQL runtime directly, then render validated chart/KPI/table/summary outputs in Python. There is no separate dashboard planning or narrative model call. See [the workspace guide](text-to-dashboard.md) for architecture, limits and validation.

The legacy single-chart agent remains available for chart previews. The saved Dashboard tab supports chat clarification, private saved documents, editing, refresh and rebuild.

The SQL runtime is compatible with both a raw SQL agent and an analytics wrapper exposing `sql_agent`. It retains the main branch's SQL validation, annual-revenue compiler and Auto orchestration. Jev/OpenRouter is not required for this workflow.
