# Dashboard implementation status

Implemented:

- Chat-style request and bounded clarification before opening the workspace.
- Shared SQL runtime with raw/wrapped compatibility and no separate dashboard planner.
- At most two independently validated queries and eight declared outputs per new build.
- Charts, overall KPIs, tables and aggregate summaries bound to actual returned fields.
- Pre-execution requirement validation and post-execution representation checks.
- CTE/subquery aggregate lineage, NULL handling and shared source observations.
- Private atomic persistence, scoped queries, revision checks and preserved refresh layouts.
- Groq key rotation with no Groq-to-Cloudflare fallback.

Specifications: [build](../SPEC-dashboard-build.md), [workspace](../SPEC-dashboard-workspace.md). Runtime guide: [saved dashboards](../docs/technical/text-to-dashboard.md).

Deferred: grouped descriptive statistics, cross-result arithmetic, presets and expanded cross-domain interpretation. Unsupported requirements must be clarified rather than silently dropped.
