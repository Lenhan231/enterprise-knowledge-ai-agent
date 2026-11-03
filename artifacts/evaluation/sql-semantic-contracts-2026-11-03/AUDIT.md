# Semantic follow-up audit

Reviewed `origin/QuocAn` at `8bb2437`; frozen inputs remain in `../agent-benchmarks-2026-11-02/`. No references, catalog formulas, approved base joins, permissions, or database objects were changed.

| Case | Diagnosis | Resolution |
|---|---|---|
| S04 | Model invented top 10 where no count was requested. Snapshot date is additional provenance at the same single-date category grain. | Normalize unspecified inventory rankings to 200; retain dated provenance. |
| S10 | Latest run asked for a definition already present in the catalog: `fill_rate` did not match space-separated aliases before schema pruning. Full-month observations versus reference month-end is a legitimate temporal policy difference when additional snapshots exist. | Recognize catalog IDs and space/underscore alias variants. Preserve full-month scope and exact snapshot groups. |
| S11 | Invented top 10 truncates a reference bounded at 200. Product scalar values must not become summed calendar days. | Fix default ranking count; retain scalar product/snapshot grain, NULLS LAST and stable ordering. Month versus closing-snapshot distinction remains explicit. |
| S20 | Reference subtracts COALESCE(discount_amount,0), generated SQL subtracts discount_amount. The migration declares this field NUMERIC NOT NULL. DATE_PART/year bounds are equivalent for this year. | Legitimate alternative on approved data; no formula or schema change. |
| S28 | Counting duplicate groups differs from excess rows. Two groups can contain three excess rows and five participating rows. Existing PK means production data cannot expose this error. | Default to excess rows, validate both key dimensions and formula, test a nonempty synthetic fixture. Preserve explicit requests for groups/participants. |
| S23 | Explicit returned-unit/ordered-unit ratio was unnecessarily rejected as an undefined canonical KPI. It differs from order-based return_rate. | Independently aggregate each dated source by product, validate NUMERIC/NULLIF ratio and each period, then allow complete grouped keys with approved product-key lineage. |
| S26 | Mixed inventory/order request previously enters inventory-only interpretation; a raw detail join would multiply observations. Latest run was quota-blocked, not a demonstrated SQL failure. | Shared SQL path with a narrow stockout/order EXISTS contract; approved correlated keys, both date scopes, snapshot provenance and requested flag predicate remain mandatory. |
| S27 | Independent category movement aggregates are safe; raw inventory/order joins are not. Latest run was quota-blocked. Inventory movement is not interchangeable with orders. | Validate explicit period SUM of recorded units_sold and independent SUM(order_items.quantity), FULL JOIN complete category keys with COALESCE labels, preserve missing values as NULL. This is an explicit observation rollup, not a balance KPI. |
| S21 | DATE_TRUNC on an untyped parameter fails PostgreSQL overload resolution. Grouping only product_name can merge distinct products. | Cast date-function parameters to DATE and require product_id for product-level named results. Real read-only typed-date probe passed. |
| S07 | First follow-up run selected a scalar boolean indicator for “most flagged products,” then asked for clarification about its aggregate grain. This is an interpretation error, not a missing business definition. | Normalize explicit flagged-product counts to the existing approved observed_product_count with the requested boolean filter; rank the count. No new metric formula. |

## Clarifications before this follow-up

Latest completed cohort has three clarifications: **S10 unnecessary** (known inventory field), **S23 unnecessary** (explicit unit operands, grain and year), **S30 necessary** (no supplier identity/attribution in the full approved schema). S30 correctly offers historical product/category inventory instead; shipments alone cannot establish supplier lateness. Quota failures are unavailable outcomes, not clarifications or valid refusals. Later results are classified separately, without relabeling old attempts.

## Boundaries and review

Derived joins require independent GROUP BY keys, complete key equalities, transparent dimension lineage, no operand LIMIT, and no raw fact-to-fact relationship expansion. EXISTS requires an approved correlated equality and rejects disjunctive key bypasses. Aggregate fanout checks still run. The requested cross-domain sources cannot silently disappear. RBAC executes before any provider/database call; repository SQL revalidation and read-only transactions remain unchanged.

Period movement comparison is deliberately narrow: category, recorded units_sold, ordered quantity and one explicit common historical period. Other inventory combinations retain safe refusal. Missing measures and zero denominators remain NULL. An explicit sum of movement observations does not certify the upstream movement-window definition or business approval.

Self-review covered lineage, complete grouping keys, query bounds, alias isolation, correlation, source retention, date-function typing and empty evidence. No new dependency, schema migration, architecture layer, or live-server configuration was introduced.

## Evaluation protocol

One new SQL cohort (S01–S30), unchanged frozen questions/references/judge/scorers. Six Report cases declared before generation: R01, R06, R16, R17, R20, R28. R16 and R28 previously failed; the others cover inventory summary, trends, a returns ratio and data-quality limitations. First response only; no implicit supported-scope/template confirmation. Stop scheduling on exhausted provider keys rather than record repeated known outages. No historical result is overwritten.

The inherited numerical scorer gives nonexecuted supported cases zero before testing numerical applicability. Report both its original denominator and a fixed numerical-eligibility supplement where useful. No claim that a generated SQL alternative is wrong solely because the semantic judge disagrees. Latency is descriptive, sequential and includes request-local retries; pacing between requests is excluded.

The initial 24089a2 cohort at this directory root stopped after S10 on all-key daily quota exhaustion. Judge calls also hit a usage limit. Its attempts are preserved; the final revision uses the separate `final/` directory. Do not combine those generations into a single revision's performance result.
