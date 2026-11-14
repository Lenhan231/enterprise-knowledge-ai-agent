# Spec: dashboard-build

Objective: translate a business description into a saved-dashboard document with several useful tiles, using the existing SQL agent for every data request.

Inputs: server-verified analytics identity, description (2,000 characters), optional shared scope (600 characters). Inspect the authorized schema and up to three relevant date-coverages. A bounded model plan contains up to four complete query questions and eight KPI, chart, table or summary tiles. Queries can feed multiple tiles.

Output: typed dashboard document with query results, SQL/parameters, policy/metric metadata, observed dates, tile configuration, status and timestamps. Each SQL request retains Jev and the existing security boundary. Two queries may run concurrently under a 180-second overall build budget. Partial failures remain visible. No invented values or source-level claims derived from truncated result rows.

Implementation: `src/core/dashboards/models.py`, `agent.py`. Reuse `core.sql_agent.agent`, runtime deadlines and chart mapping. SQL agent generates SQL; the dashboard agent plans and composes the document. Retain the legacy chart-preview route for compatibility.

Style: strict Pydantic models; `await sql_agent.run_payload(scoped_request)`; never interpolate model/user text into executable SQL.

Verify: `.venv/Scripts/python.exe -m unittest discover -s tests -p test_dashboard*.py`. Test multi-tile reuse, permissions, partial/empty results and bounded planning. No external model calls in unit tests.

Always enforce identity, query limits, deadlines and result provenance. Never grant database access from a dashboard plan. No new external provider or analytics-schema migration.
