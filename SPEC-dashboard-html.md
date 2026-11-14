# Spec: dashboard-html

Objective: produce one responsive, self-contained HTML dashboard from the validated document.

Tiles: one-row KPI, bar/line/donut through existing ChartSpec eligibility, table, and descriptive statistics over explicitly labeled returned observations. Preserve unknown currency, missing values, negative values and partial-result messages. No global totals from sums of overlapping category counts or averages of averages.

Interface: `render_dashboard(document) -> str`. Reusable tile preparation validates requested columns and chart compatibility. Unsupported charts show a table and reason. HTML includes title, timestamps, source scope and expandable query evidence.

Implementation: `src/core/dashboards/render.py`. Use escaped text, controlled HTML/CSS/SVG templates and no external scripts/CDNs. Render the preview inside a sandboxed iframe. Serve exported HTML with a restrictive CSP, no network access and no script execution. No model-authored executable HTML.

Verify: `.venv/Scripts/python.exe -m unittest discover -s tests -p test_dashboard*.py`. Check all tile types, wrong-unit fallback, XSS strings, empty values, numerical grounding and complete HTML structure.

Always escape untrusted content and retain SQL/chart validators. Never evaluate model code or insert raw labels/SQL into HTML markup.
