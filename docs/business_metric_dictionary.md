# VietStyle business metric dictionary: inspection and proposal

Status: pre-implementation proposal, awaiting review. The task's detailed requirements are accepted as the initiative scope. The invoked spec-driven workflow still requires review of the [capability map](../CAPABILITY-MAP-business-metric-dictionary.md) before module specifications and implementation. There is no active YAML catalog or runtime change yet.

## Verified environment and implementation

- Working branch: `QuocAn`, baseline commit `78ddb20`. The pre-existing untracked `artifacts/local/` directory is preserved.
- Model: configured `qwen/qwen3.8-27b`, temperature 0, current reasoning setting, 1,000 output tokens. No model/provider change, fine-tuning or Schema Discovery Agent.
- Python 3.11, Pydantic 2.11.7, sqlglot >=30.19.0, asyncpg >=0.32.0, unittest. PyYAML 6.0.2 is installed and PyYAML is already in the lockfile; its direct runtime dependency declaration needs checking when implementing YAML loading.
- Connected Supabase project: FA26AI69, `ciiztxhbxtkxferpmyet`. Only metadata and aggregate SELECTs were used. No customer-level records, production DML probes, schema/RLS changes or migrations.

Current path:

1. `SQLAnalyticsAgent._authorize` requires a server-verified identity with `analytics:read`.
2. `resolve_metric_names` uses NFC/case normalization, exact word boundaries and longest matching aliases in the in-code `METRIC_ONTOLOGY`.
3. `build_sql_prompt` supplies definitions only for recognized metric names plus the approved schema, functions and joins.
4. The unchanged configured provider returns a JSON query plan; `decode_query_plan` validates SQL, placeholders and date parameters.
5. `validate_metric_definitions` traces expressions through transparent CTEs, matches canonical formulas, checks filters and snapshot scope, and raises `MetricDefinitionError`.
6. The agent permits one repair attempt; only validated plans reach `CommerceRepository.execute_approved_query`.
7. The repository revalidates SQL and executes inside a read-only transaction with a five-second statement timeout. Results are limited by the SQL validator to 200 rows.
8. `AnalyticsAgent` supplies the returned metric definitions/limitations to its summarizer. Report source collection calls the existing SQL/Analytics path and propagates clarification; section generation itself need not change.

Integration points and callers include `metric_ontology.py`, `metric_validation.py`, `text_to_sql.py`, `sql_analytics_agent.py`, `analytics_agent.py`, `prompts/sql.py`, `intent_classifier.py`, `join_validation.py`, report source collection and the SQL/analytics/router/report tests. Legacy financial extraction/candidate modules also import `METRIC_ONTOLOGY` and expect older field names; do not silently repurpose them or manufacture obsolete financial definitions. Runtime packaging must include the catalog because the backend image currently copies application source, not the semantic data directory.

Important current limits:

- `return rates` and `fill rates` are missed by exact singular aliases. `inventory` can instead resolve to stock on hand.
- The validator unions permitted dimensions across requested metrics instead of checking each measure's compatibility independently.
- A stored non-aggregate metric projection is treated as a dimension; valid product fill-rate rows can be rejected.
- Snapshot validation recognizes bound/literal equality or grouping, but not a verified latest-snapshot scalar query.
- Named-metric validation checks formulas but does not verify that a generated year filter matches the question.
- With no recognized metric name, metric validation returns immediately. Unsupported business metrics must not gain an execution path merely by avoiding an alias.
- Current safety checks reject joins involving CTE/derived sources. Any support needed for return-unit or repeat-customer patterns must prove grouped uniqueness and approved source relationships; do not simply relax fanout checks.
- Orchestrated Report source groups currently retain rows/sources but omit enforced metric metadata. A minimal metadata propagation change may be needed in execution/source collection so reports receive the catalog version, definitions and limitations; do not rewrite Report section generation.

## Live inspection evidence

See [database-profile.json](../artifacts/evaluation/vietstyle-metrics-v1/preflight/database-profile.json). Its entries retain SQL, results and source references. Queries are separate read snapshots, not a globally consistent transaction.

| Table | Rows | Grain/key | Date coverage |
| --- | ---: | --- | --- |
| products | 2,412 | product_id | No validity dates |
| geography | 39,948 | zip | No dates |
| customers | 121,930 | customer_id | Signup: 2012-01-17–2022-12-31 |
| orders | 646,945 | order_id | Order: 2012-07-04–2022-12-31 |
| order_items | 714,669 | order_item_id | Order date through orders |
| payments | 646,945 | order_id | No separate payment date |
| shipments | 566,067 | order_id | Ship/delivery dates through 2022-12-31 |
| returns | 39,939 | return_id | Return: 2012-07-11–2022-12-31 |
| reviews | 113,551 | review_id | Review: 2012-07-10–2022-12-31 |
| inventory | 60,247 | snapshot_date + product_id | 126 month ends, 2012-07-31–2022-12-31 |
| sales | 3,833 | date | 2012-07-04–2022-12-31 |
| web_traffic | 3,652 | date + traffic_source | 2013-01-01–2022-12-31; actually one row/date |
| promotions | 50 | promo_id | Windows: 2013-01-31–2022-12-31 |

All Commerce primary/foreign keys were inspected and all foreign keys are validated. There are 94 columns and no column descriptions in the database. The nonzero NULL counts are optional item promotion slots (438,353 primary, 714,463 secondary) and promotion category restrictions (40 campaigns). Other inspected columns contain no NULLs; empty-string validity was not exhaustively audited.

Rechecked checkpoints:

| Measure | Observed total |
| --- | ---: |
| SUM(sales.revenue) | 16,430,476,585.53 |
| SUM(payments.payment_value) | 15,680,869,265.43 |
| SUM(quantity × unit_price − discount_amount) | 15,680,869,265.43 |

Additional findings informing semantics:

- On every one of 3,833 days, source sales revenue equals gross order-item quantity × historical unit price across all statuses. Source COGS matches quantity × current catalog COGS within 0.005 per day. These are empirical relationships, not official accounting definitions.
- Order statuses are delivered (516,716), cancelled (59,462), returned (36,142), shipped (13,773), paid (13,577) and created (7,275). All have recorded payment values. A payment row does not prove cash capture or settlement.
- Joining order payments to items inflates the payment sum to 17,106,421,854.80. This was an aggregate diagnostic SELECT, not an approved metric calculation. There are 16 duplicate order/product line pairs and two repeated return-event pairs; joining those tables on order/product without preaggregation can multiply quantities.
- Returns include 39,939 events for 36,062 orders and 109,586 units, all linked to returned-status orders. All return products were present in their order; return lags are 5–31 days. The cutoff limits mature cohort comparisons.
- Inventory covers 1,624 distinct products historically and 424 on the latest date, with 104,235 closing units. Missing products are not zero stock. The source reorder flag is false for every row. Stored fill-rate values range 0.0667–1; original formula and weighting are not established by this inspection.
- Only 1,716 inventory product/month rows match all-status order-line quantities. Treat inventory movement units and order quantities as separate metrics.
- 477,453 orders precede their linked customer's signup date. Signup counts can be described, but acquisition/retention timelines require review.
- Website data has six channel labels but only one row per date. It cannot establish a complete channel-by-day panel or session-level attribution. Stored bounce rates range 0.0032–0.0058; their percentage convention is unresolved.
- No currency_code exists. No conversion-attribution, advertising-spend, payment-capture, historical-cost, supplier lead-time, warehouse-level stock or live adjustment ledger was found in the 13 Commerce tables.

The Kaggle overview was opened at https://www.kaggle.com/competitions/datathon-2026-round-1/overview but exposed no readable KPI definitions to the browsing tool. Do not label a business definition source_defined without actual supporting source text.

## Controlled policy alignment

The uploaded controlled **VietStyle Enterprise Operating Policy v1.0** is available in active-ready document records with SHA-256 `23a10676110a9a5d238947b31dcc884c3b78038b96c4fa85185ec72f8ba409dc`. Relevant parser excerpts and indices are preserved in the evidence file. A separate inactive simulation-draft record is not substituted for that controlled copy.

Verified requirements include:

- Inventory is historical, dated analytical data, not live availability; missing snapshots are not zero and balances must not be added across dates (chunks 335–345, 361–371).
- Metric definition, period, grain and source must be understood; cross-table comparisons require compatible grains and traceable validation/sign-off (486–497).
- Authentication does not imply authorization to every record; preserve least privilege (500–501).
- AI may query authorized data and recommend; it cannot approve claims, pay, issue POs, adjust stock or grant access through this analytics flow (598–607).
- Ambiguity, missing evidence and conflicts require clarification/escalation (667–677).
- VND approval thresholds do not establish the currency of numeric Commerce values (169, 650).

These controls govern analytics use; they do not officially approve newly executable KPI formulas.

## Proposed catalog conventions for review

Use `data/semantic/vietstyle_metrics_v1.yaml` as the sole editable definition source. Keep existing public ontology helpers where practical; derive their lookup map from this catalog. There is no second registry or new semantic service.

Each entry declares identity/version, bilingual aliases and examples, source columns, formula or approved pattern, grain, dimensions and their source lineage, date semantics, filters, aggregation/null/zero rules, join requirements, units/currency, limits, evidence, provenance, definition status, approval status and validation status.

The three independent classifications are:

1. **Provenance:** source_defined, team_defined, unresolved.
2. **Approval/definition status:** proposed/unreviewed, team-accepted for capstone, business-owner approved, rejected, unresolved or retired as applicable. Team acceptance must never be displayed as official business approval.
3. **Validation status:** not tested, profile reconciled, deterministic fixtures passed, live checks passed, or failed. These record evidence; they never auto-promote approval.

Only reviewed executable definitions may run through metric validation. Unresolved or unreviewed entries remain discoverable for clarification but cannot become executable because the LLM supplies SQL.

### Proposed defaults

| Decision | Proposed team convention |
| --- | --- |
| Net order-item sales value | SUM(quantity × historical unit_price − line discount), all placed-order statuses, order-date cohort; explicitly not cash or statutory net revenue |
| Daily/monthly/yearly net value | Same canonical measure, with date/day, month or year rollup; not three duplicate definitions |
| Product-level value and units | Use order_items with products and orders; net/gross/status choices are explicit. Keep inventory movement units separately named |
| Source revenue, source COGS and source profit | Retain separately named source measures; do not silently switch their bases to net payments or delivered sales |
| Fulfilled measures | Explicitly named status-filtered variants with exact included states; no inference of historical fulfillment from a neighboring table |
| Average order value | Chosen order-item value numerator / distinct eligible orders in the same cohort; zero denominator -> NULL |
| Cancellation rate | Distinct cancelled placed orders / distinct placed orders in the same order-date cohort |
| Stored fill rate | Read the recorded product/snapshot value. It is not a count of fulfilled units |
| Aggregate fill rate | Separate explicitly named unweighted mean of non-NULL stored values within one snapshot, adopted only as a team convention |
| Inventory history | One snapshot at a time or separate output groups per snapshot. Explicit latest means database MAX(snapshot_date), never a hardcoded 2022 date |
| Stockout/overstock/reorder indicators | Describe stored flags at the selected snapshot; no invented source threshold or operational reorder formula |
| Return rates | Distinct order-based and unit-based definitions. Bare return rate asks which. Use an explicit order-date cohort, eligible states and observed return cutoff |
| Duplicate returns | Count distinct orders for order rate; sum return events per order/product and aggregate sold lines per the same pair for unit rate |
| Customers/signups | Counts of stored records or recorded signup dates; retain chronology warnings, do not infer reliable acquisition cohorts |
| Repeat customer share | Requires explicit within-period/lifetime and order-status convention; remains unresolved until that choice is reviewed |
| Acquisition/geography grouping | Treat customer acquisition label and order source as different dimensions. Default order geography uses orders.zip; no causal attribution |
| Website sessions/page views | Add recorded counts over observed rows; disclose incomplete channel-date coverage |
| Unique visitors | Stored daily value is reportable; summing daily values is visitor-days, not unique people over a month/year |
| Bounce rate | Raw stored value can be described; percentage interpretation/true aggregate rate stays unresolved without source units/denominator |
| Session duration | A separately named session-weighted mean is a proposed analytical convention, not an inferred source implementation |
| Promotion usage | Distinct orders carrying either campaign slot, without double-counting stacked items/orders; per-campaign allocation requires an explicit rule |
| Discounts | Sum recorded line discounts once; count discounted items by distinct order_item_id |

Suggested empty-result rules: COUNT returns zero, SUM of no observations remains NULL unless the particular metric explicitly defines zero, and undefined rates return NULL via NULLIF. Never fill an absent inventory row with zero.

### Coverage proposal

All requested categories are represented; dimensions/time rollups reuse a canonical metric rather than creating copies of the same formula.

| Domain | Executable candidates once reviewed | Unresolved/conditional candidates |
| --- | --- | --- |
| Sales/finance | Source daily revenue/COGS/profit/margin; net item value with day/month/year and product/category rollups; ordered units; order count; AOV; line discounts; recorded payment value; separately labeled catalog-cost profit proxies | Actual cash revenue, statutory net revenue, historical-cost profit and unqualified revenue/sales ambiguity |
| Inventory | Dated stock on hand; stored and mean stored fill rate; observed stockout share; stockout days; stored/mean days of supply and sell-through; receipt movement units; recorded reorder/overstock indicators; product snapshot history | Original fill-rate formula/weighting, demand-weighted fulfillment, live availability and operational reorder quantities |
| Orders/customers | Orders by status; cancellation share; customer count; recorded signup count; orders grouped by recorded acquisition/order channel and geography | Repeat-customer semantics until reviewed; causal acquisition/retention analysis |
| Returns/fulfillment | Return events, distinct returned orders, returned quantity, refunds, explicitly scoped order/unit return rates, shipment count and average transit days | Unqualified return rate, unmatured cohort completeness, realized revenue reversal, on-time SLA performance |
| Marketing/website | Sessions, daily visitor values/explicit visitor-days, page views, raw bounce values, proposed session-weighted duration, distinct promotion-using orders, distinct discounted item count | True multi-day distinct visitors, source-unconfirmed bounce percentage, conversion attribution, CAC, ROI and stacked-campaign value allocation |

### Example entry shape (not active)

```yaml
id: net_order_item_sales_value
version: 1.0.0
name: Net ordered merchandise value
description: Order-line value after recorded line discounts; not verified receipts.
aliases:
  en: [net order-item sales value, net ordered merchandise value]
  vi: [giá trị đơn hàng sau giảm giá, giá trị bán hàng thuần theo dòng đơn]
sources:
  commerce.order_items: [order_id, product_id, quantity, unit_price, discount_amount]
  commerce.orders: [order_id, order_date, order_status]
  commerce.products: [product_id, category, segment]
formula: SUM(quantity * unit_price - discount_amount)
grain: order_item
dimensions: [order_date, order_status, product_id, category, segment]
date:
  field: commerce.orders.order_date
  semantics: placed-order cohort; day/month/year rollups
aggregation: sum
unit: currency
currency: dataset_currency_unknown
eligibility:
  statuses: [created, paid, shipped, delivered, returned, cancelled]
  note: All recorded placed orders; no cash-recognition claim.
null_handling: SUM over no observations is NULL; do not invent zero activity.
zero_denominator: not_applicable
joins:
  - commerce.order_items.order_id = commerce.orders.order_id
  - commerce.order_items.product_id = commerce.products.product_id
limitations:
  - Product dimensions require the many-to-one product join.
  - Recorded payment totals reconcile but remain a distinct measure.
  - Neither VAT nor refund recognition is established.
provenance:
  category: team_defined
  evidence: preflight/database-profile.json#checkpoints
definition_status: proposed
approval_status: unreviewed
validation_status: profile_reconciled_only
examples:
  - Show net order-item sales value by product for 2022 across all order statuses.
  - Giá trị đơn hàng sau giảm giá theo tháng năm 2022 là bao nhiêu?
```

Final schema field names and safe AST patterns belong in the reviewed module specification. The example deliberately has no approval date, approver identity or official source-defined claim.

## Benchmark and test baseline

See [metric_validation_report.md](metric_validation_report.md). Existing benchmark artifacts were not overwritten.

The original-model baseline was captured before implementation. Four of eight cases executed, three requested clarification and Q8 was rejected by metric validation. These are transport/planning outcomes, not eight semantic correctness scores. The after run must use the identical frozen questions, model and generation settings and evaluate formulas, scopes, results and clarification quality separately.

The current-generation Q7 clarification correctly distinguishes orders versus units. Q6 asks about a dimension/source conflict and incorrectly suggests inventory movement as a substitute for transaction sales. Q8 attempts a stored product fill-rate query on the latest snapshot and is rejected. Unsupported website conversion is clarified, but asking the user for an arbitrary formula must not authorize unsupported attribution.

## Remaining review items

1. Approve or adjust the three capability boundaries/build order.
2. Confirm the all-placed-status net-order-value convention and how generic revenue aliases should clarify rather than change source silently.
3. Confirm a distinct team-defined unweighted stored-fill-rate average; leave fulfillment weighting unresolved.
4. Choose eligibility and within-period/lifetime scope for repeat customer share, or keep it unresolved.
5. Review explicit order/unit return-rate cohorts and denominators; do not conflate event counts with orders or a return-date period with an order cohort.
6. Determine source currency, bounce-rate units and cross-day visitor identity from authoritative source documentation if available. Until then, those claims remain unresolved.

No implementation improvement or after-benchmark result is claimed at this stage.
