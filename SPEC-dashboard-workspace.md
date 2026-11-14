# Spec: dashboard-workspace

Objective: add a separate Dashboard tab to the local web app. The current user explicitly chose the app rather than Streamlit for this workspace.

Workflow: describe a dashboard → build and save → preview one HTML document → reopen from saved list → edit title/tile titles, layout order/span and supported chart type/columns → save a revision. Shared data-scope filters trigger SQL refresh. Rebuilding an edited description replans the document; refreshing an unchanged definition reruns its data questions. Open/download HTML and delete owned dashboards are available.

UI: reuse the existing sidebar, role visibility, API client, authentication lifecycle and design tokens. Responsive library/editor/preview layout, labeled controls, keyboard-accessible actions and explicit busy/error/partial states. Clear private state and ignore late responses after account/session changes. Use an iframe sandbox; no HTML in the privileged app DOM.

Implementation: `src/app/static/dashboard.js`, `dashboard.css`, small `index.html` and `app.js` integration. APIs are `/api/dashboards` and owner-scoped item/refresh/html routes. Both app and backend are served by the existing local FastAPI process at port 8000. Stop the earlier owned Streamlit process; do not launch another Streamlit instance.

Verify: `node --check src/app/static/dashboard.js`, `.venv/Scripts/python.exe -m unittest discover -s tests -p test_dashboard*.py`, HTTP health/authenticated CRUD smoke checks, and browser UI review if a browser surface is available. No frontend framework or dependency is added.
