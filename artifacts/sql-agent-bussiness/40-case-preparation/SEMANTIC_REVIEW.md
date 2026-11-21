# Semantic review memo

**Status:** author-side memo for independent review. No reviewer approval has been claimed.

## Live contract evidence

- Frozen analytics snapshot fingerprint: `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`; captured `2026-11-21T05:51:51.334549+00:00`; read-only role verified.
- 15 Commerce tables are visible; inventory has 47 snapshots from 2023-01-31 through 2026-11-13. `commerce.orders.order_date` is PostgreSQL `DATE`.
- `stock_on_hand` is NOT NULL in the approved schema contract. `days_of_supply` is all NULL at 2025-10-31; do not coerce those values to zero.
- Geography has only region `East`; 2025 shipment/return rows used in city cases had no unmapped order ZIPs in preflight.
- 2024 daily sales rows: 20 satisfy `cogs > revenue` and 346 satisfy `revenue > cogs`; B40-007 is nonempty without changing its predicate.
- At 2025-10-31, observed inventory categories are Casual, GenZ, Outdoor and Streetwear; Outdoor `units_sold` sums to 113. `Home & Kitchen` is absent.
- Latest 2026-11-13 `units_received` by segment is observed across eight segments; the draft’s top five is nondegenerate.
- Delivered 2025 orders with no order item row: 0; product catalog COGS is complete for 97/97 products.
- Information schema exposes no PK/FK declarations; approved migration relationship and key contracts remain authoritative.

## Required semantic decisions

1. **Dates:** treat year and range questions as half-open calendar intervals on the declared DATE column. For inventory, each exact snapshot remains separate.
2. **AOV (B40-004):** denominator is distinct delivered orders with at least one item row; numerator is item quantity × unit price − discount amount. The question now uses 2025 consistently. Reviewer must confirm this is the intended AOV policy.
3. **Sales revenue/COGS:** `commerce.sales` is the approved company-level source. B40-007’s daily population condition is part of the question, not a post-aggregation condition.
4. **Returns/payments:** return cases filter by `return_date`; payments are only recorded payment rows linked to orders filtered by `order_date`. No missing record is imputed to zero.
5. **Current category:** B40-015 and B40-018 use current `commerce.products.category`, not a historical category snapshot. B40-009/B40-021/B40-025 use the category stored on the inventory snapshot row.
6. **Geography:** customer ZIP in B40-006 is profile geography; order ZIP in B40-014/B40-016/B40-020 is destination geography. The two meanings must not be conflated.
7. **NULLs:** preserve NULL groups/measurements. B40-025 intentionally returns NULL averages with explicit NULL counts; B40-022 reports per-snapshot NULL and non-NULL counts.
8. **Inventory comparison:** B40-023 is after minus before and includes only products observed on both exact dates. B40-024 groups each snapshot and never sums balances across dates.
9. **Follow-ups:** B40-026–030 use frozen typed-context injection from a seed user question; no model-generated assistant answer or result is injected. The current benchmark runner does not replay conversation context, so this is a specified study adapter requirement, not verified live multi-turn behavior. Reviewers must approve the context and adapter before evaluation.
10. **Unsupported/clarify:** unsupported warehouse, supplier lead-time, campaign spend/attribution, employee commission, carrier/promise-date and customer contact/VIP fields are absent from the approved schema. The expected outcomes are explicit clarification or abstention without business SQL.

## Gold draft review boundary

The 30 SQL statements are independently authored from the question, live approved schema and semantic contract. Structural validation confirms read-only SQL, approved sources/joins, selected output names, bound parameters and declared date predicates. It does not establish semantic correctness or reviewer approval. Reference rows, if present, are provisional synthetic snapshot outputs and remain blocked from oracle/freeze status until two independent reviewers approve the question, SQL, rows and tolerances.


## Deterministic audit hashes and checks

- V2 case-set SHA-256: `a759615f58dbb843296ce3d54642be3576374309a3bf4451546f771ebc2641a4`. Gold SQL definition SHA-256: `484a2dcd77b4352eec1dee30e56b0dd79690f74b829c1b0ed516832b25ba9fe6`.
- Gold SQL validator checks parameterized date predicates against the declared date column, `ORDER BY` fields/directions against the ranking contract, and literal `TOP-N` against the requested limit.
- Provisional output validator checks case/gold/snapshot alignment, row schemas and hashes, held-out Agent call count, and row ordering against the ranking contract. Results remain provisional until human review.
