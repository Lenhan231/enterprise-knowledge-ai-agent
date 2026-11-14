# Query and chart groundwork — 2026-11-14

These changes improve the existing single-chart path and can be reused as tiles in the forthcoming [Text-to-Dashboard capability map](../../CAPABILITY-MAP-text-to-dashboard.md). They do not implement saved dashboards or multi-tile HTML documents.

- Metric aliases accept common space/underscore/hyphen variants and count plurals, without turning order-item counts into order counts. A team-defined review_count metric counts distinct recorded review IDs; average rating and review count support product-category grouping with different units.
- Plain monthly recorded-revenue series with an explicit calendar period can compile to parameterized, checked SQL. Extra filters, discrete-month selections and unsupported wording fall back to the existing planner. Jev and the independent SQL/security/metric checks still apply.
- Malformed or mismatched inventory interpretations receive at most one repair attempt within the existing deadlines. Unsupported or unapproved business definitions are not relaxed.
- Inventory mappings can use conditional_counts for independent true counts of stockout, overstock and reorder indicators. Shared category/product filters remain separate. Counts use the approved distinct-observed-product measure, keep snapshot grain, and verify the formula bound to each output alias. Shared intersections and alias swapping are rejected.
- Donuts accept disjoint calendar buckets over a supported source date while retaining the existing completeness, additive-measure, unit, positivity, no-join and truncation checks. Incompatible rating/count units still return a table.
- Policy context filters rule source lists to the active schema scope; policy approval does not approve metric formulas.

Verification: 202 focused Python tests passed; an additional recorded-column alias regression passed with the four conditional-count tests. Five Node renderer tests, syntax and whitespace checks passed. The broad suite ran 966 tests with 51 failures, 88 errors and 31 skips; it remains non-green and was not a clean before/after comparison. Logs are local at `%TEMP%/dashboard-representations-full-tests.log`.

Three live Groq/Jev/SQL/chart checks succeeded, with read-only database access and clear probabilities .98, .99 and .91:

| Request | Result |
|---|---|
| Monthly recorded revenue, July–September 2026 | Donut: 1,810,421.90; 1,832,695.76; 2,090,232.15 |
| Independent flag counts at 2026-05-31 | Bar: stockout_count 15, overstock_count 73 |
| Average review rating and review count by category, 2026 | Query executed; table retained because score and review-count units differ |

Evidence is in [live-smoke.json](../../artifacts/evaluation/dashboard-representations-2026-11-14/live-smoke.json). This is a small live smoke check, not a new 50-question benchmark or browser visual review. No global clarity threshold or database permission was changed. The running backend has not yet been restarted for this groundwork; the live checks used a separate local agent process.
