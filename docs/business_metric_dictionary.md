# VietStyle Inventory Management metric dictionary v1

Implemented on branch `QuocAn`. The user approved the Inventory Management scope and team conventions. The [catalog](../data/semantic/vietstyle_metrics_v1.yaml) is the single source for inventory definitions; existing unrelated analytics remain outside this change. No finance, returns, customer, marketing or website definitions were added. Q6 product sales and Q7 return rates were removed from the scoped evaluation; Q8 lowest fill rates remains.

## Evidence and governance

Read-only inspection of Supabase FA26AI69 verified table columns, types, keys, relationships, nulls, distributions and snapshot coverage. The immutable [inspection evidence](../artifacts/evaluation/vietstyle-metrics-v1/preflight/database-profile.json) includes the original broader preflight; it is preserved, not a proposal to extend this catalog.

Inventory has 60,247 rows and 1,624 observed products over 126 monthly month-end snapshots, July 31, 2012 through December 31, 2022. The latest snapshot contains 424 observed products, 104,235 units on hand and 4,081 recorded units received. There are 2,412 products in the product master. A product absent from a snapshot is unknown, never zero. The primary key is `(snapshot_date, product_id)`; `inventory.product_id` references the unique `products.product_id`.

No inventory-column nulls were observed. Stored flags need cautious interpretation: there are no zero closing-stock rows, yet 40,571 observations carry a stockout flag; stockout and overstock flags overlap on 30,495 observations. They describe recorded indicators, not mutually exclusive inferred states. Only 1,716 of 60,247 recorded monthly inventory movement observations matched the inspected monthly order-unit comparison, so inventory movement is not treated as an order-sales ledger.

The controlled VietStyle Enterprise Operating Policy v1.0 governs historical labeling, evidence, grain, authorization and AI limitations. Evidence identifies its SHA256 `23a10676110a9a5d238947b31dcc884c3b78038b96c4fa85185ec72f8ba409dc`. The Kaggle overview supplied no readable authoritative KPI dictionary. A database column or successfully executed formula is not an official business definition.

Every definition separates provenance (`source_defined`, `team_defined`, `unresolved`), definition status, validation status, team execution acceptance and business approval. The 15 executable entries are team-defined and team-accepted; all have business approval `not_recorded`. The six unresolved candidates have no executable formula and remain unreviewed. No metric is labeled source-defined without source documentation.

## Supported definitions

All metrics use product-snapshot observations. Aggregates operate within one exact snapshot date; a trend returns separate exact-date groups. Product attributes come from the canonical product master through a many-to-one join. Category, segment, product name, size and color are permitted; geography, customer and order dimensions are not inventory dimensions.

| ID | Team convention |
| --- | --- |
| `stock_on_hand` | Sum recorded closing stock across observed products within one snapshot; individual product values may be selected directly. |
| `stored_fill_rate` | Return the stored product value unchanged; rankings compare those stored values. Original fulfillment formula and weights are unknown. |
| `fill_rate` | Unweighted mean of non-null recorded fill rates; explicitly a mean of stored values, not reconstructed aggregate fulfillment. |
| `stockout_rate` | Flagged observed product IDs divided by all observed product IDs in the same snapshot and dimension group. |
| `stockout_days` | Sum recorded product stockout days within one snapshot; unit is product-days, not distinct calendar days. |
| `days_of_supply` | Unweighted mean of recorded days of supply, or individual recorded values. No forecast reconstruction. |
| `sell_through_rate` | Unweighted mean of recorded sell-through rates, or individual values; source denominator is unknown. |
| `units_received` | Sum the stored movement field within one snapshot; not a verified purchase-order receipt ledger. |
| `inventory_units_sold` | Sum the stored inventory movement field within one snapshot; not reconciled order sales or revenue. |
| `overstock_rate` | Share of observed product IDs whose stored overstock flag is true. |
| `reorder_rate` | Share of observed product IDs whose stored reorder flag is true. |
| `stockout_indicator` | Stored product stockout flag. |
| `overstock_indicator` | Stored product overstock flag; no new threshold inferred. |
| `reorder_indicator` | Stored product reorder flag; historical evidence does not authorize ordering. |
| `observed_product_count` | Count distinct observed product IDs within the selected snapshot and dimensions. |

Ratios count the non-null product primary-key component explicitly, preserving source grain through joins. Numerators and denominators use the same eligible observed group. Stored rates and computed ratios remain fractions: 0.25 means 25 percent. No multiplying by 100 in SQL. SUM/AVG ignore null observations and retain NULL for no observations; undefined ratio denominators return NULL through NULLIF. No missing product balance is filled with zero. Currency remains unconfirmed, and inventory valuation is not an executable metric.

The YAML contains bilingual aliases, examples, source columns, canonical formulas, optional stored-value representations, dates, dimensions, null rules, joins, limitations and provenance for every entry. Generic fill-rate rankings select stored product rates; explicit average/mean requests use the team-defined mean. Alias resolution uses normalized Unicode, word boundaries and longest matches. Bare English ?inventory? is context, not an implicit stock-on-hand metric.

## Unresolved business decisions

| Candidate | Required evidence before execution |
| --- | --- |
| Demand-weighted fill rate | Demand/fulfilled-unit numerator and denominator, source weighting method and eligible cohort. |
| Reorder quantity | Approved demand, supplier lead times, safety stock, open POs, backorders and order constraints. |
| Reorder point | Reviewed demand/lead-time rule and replenishment policy. |
| Safety stock | Service-level target, demand variability, lead-time variability and approved method. |
| Inventory accuracy | Physical counts reconciled to system balances at the same grain/date, with tolerance rules. |
| Inventory turnover | Reconciled period COGS, inventory valuation and averaging convention in confirmed units/currency. |

Stored flag thresholds and the original fill-rate, days-of-supply and sell-through formulas remain undocumented. Monthly stored movement windows must not be called authoritative transaction flows. These assumptions require business review; executable historical observations do not resolve them.

## Runtime behavior and boundaries

1. Existing verified `analytics:read` authorization runs first.
2. The existing ontology loads and validates YAML at startup. Missing/invalid catalog data fails explicitly. There is no second registry or Schema Discovery Agent.
3. For inventory requests and requests without a recognized legacy metric, the existing LLM first returns a typed interpretation: catalog metric IDs, product/aggregate representation, dimensions, source-row filters, historical dates and optional ranking. The selector sees compact ID/description/status summaries, not every full definition. English, Vietnamese and mixed wording may map to the same approved IDs. Known unresolved metrics are rejected before any model call. Recognized non-inventory legacy metrics retain the existing path; other generic requests receive a domain interpretation first.
4. Python validates IDs, definition acceptance, compatible source fields/types, dimensions, representation, date structure and ranking limits. Invalid or ambiguous interpretations stop before SQL generation. A model cannot supply SQL or new formulas in this interpretation. Generic inventory context alone does not force a stock metric. Unsupported questions remain unsupported even when the LLM suggests a candidate.
5. Only a valid interpretation reaches SQL generation. The prompt supplies relevant definitions and schema relationships. Product representation uses the catalog's approved stored-value formula, without aggregation. SQL must preserve the mapped dimensions, filters/values, date scope, grouping, selected metrics, ranking and row limit. The inventory/products FK makes their product IDs equivalent. Latest means the unfiltered database MAX(snapshot_date); results always identify snapshot_date. ISO dates, date ranges, explicit years and separately grouped history are supported; named/relative periods may still require explicit ISO dates.
6. Existing SQL AST, approved table/column/function, parameter, safe-join, result-limit and read-only checks still apply. A single JSON code fence may wrap the JSON object, as in other existing agents; extra text/objects, SQL writes and invalid interpretations remain rejected. One SQL repair cannot bypass any check. Mapped queries currently use direct SELECTs; CTE, HAVING and DISTINCT rewrites require clarification rather than speculative acceptance.
7. The unchanged CommerceRepository revalidates and executes approved queries in read-only transactions. Limits remain 200 rows and the existing statement timeout. No records, RLS, migrations, permissions, models or Report section generation changed.
8. SQL/Analytics results retain metric definitions, provenance, limitations, dates and `semantic_interpretation` metadata. Report source collection still retains the existing metric context. The new interpretation normally adds one model call; provider token limits can therefore affect rapid repeated questions.

Structured `metric_error_code` metadata includes `metric_unresolved`, `metric_unapproved`, `metric_unsupported`, `unsupported_dimension`, `incompatible_grain`, `snapshot_required`, `ambiguous_snapshot`, `invalid_date_scope`, `metric_source_mismatch` and `formula_violation`, `metric_ambiguous`, `interpretation_invalid` and `interpretation_mismatch`. Existing payload fields remain compatible. Generic safe non-metric lookups retain the existing path; the dictionary does not make arbitrary natural-language interpretation infallible.

See the [validation report](metric_validation_report.md) for exact tests, paired unchanged-model measurements, remaining limitations and changed-file accountability.
