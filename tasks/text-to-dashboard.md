# Text-to-Dashboard implementation plan

The user accepted the capability map and added a separate web Dashboard tab, requesting local app/backend startup rather than Streamlit. Specs: [build](../SPEC-dashboard-build.md), [HTML](../SPEC-dashboard-html.md), [store](../SPEC-dashboard-store.md), [workspace](../SPEC-dashboard-workspace.md).

1. Add typed bounded documents, plans and tile edits. Test SQL-backed composition, invalid plans, permission denial and source failures.
2. Add controlled HTML rendering and descriptive summaries. Test grounding, chart fallbacks and escaping.
3. Add atomic private artifact persistence and authenticated APIs. Test owner isolation and revision conflicts.
4. Add the web Dashboard tab, saved library, editor and sandboxed HTML preview. Verify syntax, HTTP behavior and available browser surfaces.
5. Run focused checks, perform a small live build/refresh verification, preserve previous work, restart the local web app/backend and report remaining limits.

The existing chart agent remains a reusable preview compatibility path. The new dashboard builder consumes the same SQL agent; it does not replace SQL validation or create an unrestricted HTML/SQL execution path.

Implemented: typed composition, trusted rendering, private SQLite persistence, authenticated APIs, separate web tab and editor. Focused tests cover authorization, bounded plans, source failures, alias binding, scope rewrites, escaping, chart fallbacks, ownership and optimistic revisions. Live build/refresh/edit/open/download checks succeeded. No browser surface was available for visual QA. See [implementation and limits](../docs/technical/text-to-dashboard.md).

Imported the newer SQL main change `90c46c0` as `1588a38` without importing unrelated invoice/UI changes. Local web startup uses `scripts/start_local_web.py` on port 8000; earlier Streamlit was stopped.
