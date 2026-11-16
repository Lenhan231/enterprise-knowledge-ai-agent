---
contract_id: commerce_schema_metric_contract
contract_version: 1.0.0
status: approved_schema_unreviewed_business_metrics
language: vi
scope: commerce analytics SQL and retrieval
source_of_truth:
  - supabase/migrations/20261003055344_datathon_commerce_schema.sql
  - supabase/migrations/20261107054431_invoice_sql_projection.sql
  - src/core/analytics/sql_validation.py (APPROVED_COLUMNS, APPROVED_JOINS)
  - src/core/analytics/join_validation.py (PRIMARY_KEYS)
---

# Commerce schema and metric contract v1.0.0

## 1. Authority and safe use

This contract describes the 15 tables currently exposed to the Commerce SQL validator: 13 synthetic Commerce tables and 2 reviewed invoice-projection tables. It records schema facts separately from business metric decisions. **A table/column being present does not mean every metric or business interpretation is approved.** Use the `APPROVED_COLUMNS`, `APPROVED_JOINS`, and read-only SQL checks in the running application as the execution boundary; this document is semantic context for retrieval and generation, not permission to bypass those checks.

Status meanings:

- `schema_fact`: supported by the listed migration/validator metadata.
- `defined_metric`: an existing metric ontology definition; apply its documented formula and filters.
- `unresolved`: the schema permits a query but the business formula, unit, or interpretation is not established. Ask for clarification when the difference changes the result; otherwise return the SQL result with the uncertainty stated.
- `not_available`: required evidence is absent. Never fabricate it or substitute a nearby column silently.

The Commerce sales dataset is synthetic competition/demo data, not evidence of a real company. Invoice projections are only published approved snapshots. Do not combine them with synthetic Commerce sales unless the user explicitly asks and a valid reconciliation key, currency policy, and non-overlapping scope are established.

## 2. Canonical table catalog

`PK` is the declared primary key. `FK` references the indicated table. Numeric values have no implied currency unless the source row or an approved metric says otherwise. `NULL` means unknown/not supplied, not zero, false, or “not applicable”.

### `commerce.products` — product catalog

- Grain / PK: one row per `product_id`.
- Columns: `product_id INTEGER PK`; `product_name TEXT NOT NULL`; `category TEXT NOT NULL`; `segment TEXT NULL`; `size TEXT NULL`; `color TEXT NULL`; `price NUMERIC NOT NULL >= 0`; `cogs NUMERIC NOT NULL >= 0`.
- Semantics: current/catalog attributes; no effective-dated history. Joining to product facts by `product_id` is many-to-one. Historical category/name/price changes cannot be reconstructed.
- Edge cases: do not treat catalog `price` as the transaction price; use `order_items.unit_price` for order-line calculations. `cogs` is a product-level catalog value, not a dated realized cost ledger.

### `commerce.geography` — postal geography lookup

- Grain / PK: one row per `zip`.
- Columns: `zip TEXT PK`; `city TEXT NOT NULL`; `region TEXT NULL`; `district TEXT NULL`.
- Semantics: lookup key is ZIP/postal code. Join `orders.zip` or `customers.zip` to `geography.zip`; both source ZIPs may be NULL.
- Edge cases: NULL/unmatched ZIP must remain unknown or be reported as unmatched; do not infer a region from city text. Customer ZIP and order ZIP represent different contexts and are not interchangeable.

### `commerce.customers` — customer attributes

- Grain / PK: one row per `customer_id`.
- Columns: `customer_id INTEGER PK`; `zip TEXT NULL FK geography.zip`; `city TEXT NULL`; `signup_date DATE NOT NULL`; `gender TEXT NULL`; `age_group TEXT NULL`; `acquisition_channel TEXT NULL`.
- Semantics: one customer can have many orders and reviews. Customer geography is profile geography, not necessarily order destination.
- Edge cases: use `COUNT(DISTINCT customer_id)` for customer counts after joins that may multiply rows. Avoid exposing or grouping sensitive attributes unless requested and authorized. No customer lifetime value formula is established by this table alone.

### `commerce.promotions` — promotion definitions

- Grain / PK: one row per `promo_id`.
- Columns: `promo_id TEXT PK`; `promo_name TEXT NOT NULL`; `promo_type TEXT NOT NULL` in `percentage|fixed`; `discount_value NUMERIC NOT NULL >= 0`; `start_date DATE NOT NULL`; `end_date DATE NOT NULL >= start_date`; `applicable_category TEXT NULL`; `promo_channel TEXT NULL`; `stackable_flag BOOLEAN NOT NULL`; `min_order_value NUMERIC NULL`; `min_order_value` has no declared nonnegative constraint.
- Semantics: a definition, not proof that a promotion was actually applied or caused a sale. `order_items.promo_id` and `promo_id_2` are separate attribution slots.
- Edge cases: an item can reference two promotions; a category may be NULL/incompatible; order date may be outside a promotion window; minimum order value is an order-level threshold; `stackable_flag` describes the definition but does not prove the applied discount calculation. A line tagged to two promotions can be counted twice in per-promotion descriptive views. No campaign spend, randomized holdout, causal lift, or ROI is present.

### `commerce.orders` — order headers

- Grain / PK: one row per `order_id`.
- Columns: `order_id INTEGER PK`; `order_date DATE NOT NULL`; `customer_id INTEGER NOT NULL FK customers.customer_id`; `zip TEXT NULL FK geography.zip`; `order_status TEXT NOT NULL`; `payment_method TEXT NULL`; `device_type TEXT NULL`; `order_source TEXT NULL`.
- Semantics: order header; one-to-many to `order_items`, `returns`, and `reviews`; one-to-zero/one to `payments` and `shipments` by current PK/FK definitions.
- Edge cases: status vocabulary/terminal states have no CHECK constraint. Do not invent a delivered/cancelled/refunded filter unless the selected approved metric requires it. Check NULL dates are structurally prevented here, but data completeness and full-period coverage are not guaranteed. Use `orders.zip` for delivery geography.

### `commerce.order_items` — purchased lines

- Grain / PK: one row per `order_item_id`.
- Columns: `order_item_id BIGINT PK`; `order_id INTEGER NOT NULL FK orders.order_id`; `product_id INTEGER NOT NULL FK products.product_id`; `quantity INTEGER NOT NULL > 0`; `unit_price NUMERIC NOT NULL >= 0`; `discount_amount NUMERIC NOT NULL >= 0`; `promo_id TEXT NULL FK promotions.promo_id`; `promo_id_2 TEXT NULL FK promotions.promo_id`.
- Semantics: line-level transaction facts. Existing item-sales expression is `quantity * unit_price - discount_amount` only where the selected metric defines it. This value can be negative because no constraint bounds discount by gross line value.
- Edge cases: do not multiply `discount_amount` by quantity without an approved definition; no declared rule says whether it is per-unit or per-line. A line may have no promotion or two promotion IDs. Summing order-header measures after joining lines duplicates them. Aggregate to the target grain before joining other one-to-many facts.

### `commerce.payments` — order-level payment record

- Grain / PK: one row per `order_id`; `order_id INTEGER NOT NULL FK orders.order_id`.
- Columns: `payment_method TEXT NOT NULL`; `payment_value NUMERIC NOT NULL >= 0`; `installments INTEGER NULL >= 0`.
- Semantics: current schema allows at most one row per order, not multiple installments/payment events. `installments` is a count/plan field, not a payment row count.
- Edge cases: missing payment row is not necessarily zero paid; payment amount can differ from item sales/refunds. Do not add payments to line sales as if they are separate revenue. Future schema changes to payment grain require revisiting join/fanout rules.

### `commerce.shipments` — order shipment dates and fee

- Grain / PK: one row per `order_id`; `order_id INTEGER NOT NULL FK orders.order_id`.
- Columns: `ship_date DATE NULL`; `delivery_date DATE NULL`; `shipping_fee NUMERIC NULL >= 0`; when both dates exist, `delivery_date >= ship_date`.
- Semantics: shipment duration in calendar days is `delivery_date - ship_date` for rows with both dates. Current schema has no carrier, origin warehouse, promised SLA, or service type.
- Edge cases: exclude/report missing date pairs explicitly; do not convert missing durations to 0. Negative duration violates the database CHECK when both dates exist. Mean duration can be skewed; answer the requested statistic and state eligible/missing counts when useful. Regional attribution uses `orders.zip -> geography`, not shipment origin.

### `commerce.returns` — returned order items

- Grain / PK: one row per `return_id`; no uniqueness constraint on `(order_id, product_id)`.
- Columns: `return_id TEXT PK`; `order_id INTEGER NOT NULL FK orders.order_id`; `product_id INTEGER NOT NULL FK products.product_id`; `return_date DATE NOT NULL`; `return_reason TEXT NULL`; `return_quantity INTEGER NOT NULL > 0`; `refund_amount NUMERIC NOT NULL >= 0`.
- Semantics: multiple return rows can exist for one order/product. Aggregate returns to the target line/order/product grain before joining to order items. `refund_amount` is observed refund, not automatically equal to returned quantity times price.
- Edge cases: return quantity may exceed sold quantity; no constraint prevents it. Returns may be dated after the order period. Return count, returned-unit rate, refund rate, and net revenue are distinct metrics and require distinct formulas/denominators. Never subtract return quantity/refunds twice.

### `commerce.reviews` — order/product ratings

- Grain / PK: one row per `review_id`; `order_id`, `product_id`, `customer_id` are required FKs.
- Columns: `review_id TEXT PK`; `order_id INTEGER NOT NULL FK orders.order_id`; `product_id INTEGER NOT NULL FK products.product_id`; `customer_id INTEGER NOT NULL FK customers.customer_id`; `review_date DATE NOT NULL`; `rating INTEGER NOT NULL BETWEEN 1 AND 5`; `review_title TEXT NULL`.
- Semantics: multiple reviews per order/product/customer are allowed; no text body is stored, only title.
- Edge cases: use review rows as the denominator for average rating unless another approved definition says otherwise. Joining reviews to order items can multiply both sides; aggregate separately. Do not infer sentiment from title alone or claim survey representativeness.

### `commerce.inventory` — historical product snapshots

- Grain / PK: one row per `(snapshot_date, product_id)`; `product_id INTEGER NOT NULL FK products.product_id`.
- Columns: `snapshot_date DATE NOT NULL`; `product_id INTEGER NOT NULL`; `stock_on_hand INTEGER NOT NULL >= 0`; `units_received INTEGER NOT NULL >= 0`; `units_sold INTEGER NOT NULL >= 0`; `stockout_days INTEGER NOT NULL >= 0`; `days_of_supply NUMERIC NULL`; `fill_rate NUMERIC NULL`; `stockout_flag BOOLEAN NOT NULL`; `overstock_flag BOOLEAN NOT NULL`; `reorder_flag BOOLEAN NOT NULL`; `sell_through_rate NUMERIC NULL`; `product_name TEXT NULL`; `category TEXT NULL`; `segment TEXT NULL`; `year INTEGER NULL`; `month INTEGER NULL`.
- Semantics: repeated historical snapshots, not daily transactions. Point-in-time stock metrics must select and state an exact snapshot date. Sum/average across snapshot dates is not a period movement/balance. Use `(snapshot_date, product_id)` as fact grain; product join is many-to-one.
- Edge cases: absent product snapshot is not zero inventory; observed-product denominators cover only rows present. Snapshot copies of product labels may be NULL or disagree with current `products`; use the source requested and disclose. `year`/`month` can disagree with `snapshot_date`; derive time buckets from the date unless an approved metric explicitly uses stored fields. Rates can be NULL, out of expected range, or based on unknown formulas. `days_of_supply` values are flagged as anomalously high in current domain guidance; do not use for decisions without validation. Boolean flags can overlap and are not disjoint populations. No warehouse/location, supplier, purchase orders, backorders, forecast demand, or lead time exists.

### `commerce.web_traffic` — daily traffic by source

- Grain / PK: one row per `(date, traffic_source)`.
- Columns: `date DATE NOT NULL`; `sessions INTEGER NOT NULL >= 0`; `unique_visitors INTEGER NOT NULL >= 0`; `page_views INTEGER NOT NULL >= 0`; `bounce_rate NUMERIC NULL`; `avg_session_duration_sec NUMERIC NULL`; `traffic_source TEXT NOT NULL`.
- Semantics: aggregate traffic, not user-level events. `unique_visitors` may not be additive across sources or days; do not sum it as a distinct-period visitor count unless source methodology confirms additivity.
- Edge cases: no campaign ID or order/customer attribution key. Cannot establish conversion, attributed revenue, or causal marketing effect by joining on date/source. Rates/durations may be NULL or outside expected range; retain or validate rather than silently clamp.

### `commerce.sales` — company-level daily sales aggregate

- Grain / PK: one row per `date`.
- Columns: `date DATE PK`; `revenue NUMERIC NOT NULL`; `cogs NUMERIC NOT NULL`.
- Semantics: existing ontology defines `SUM(revenue)`, `SUM(cogs)`, and gross profit as `SUM(revenue) - SUM(cogs)`, at daily/company level. Currency is unknown. No region, category, product, order, or customer dimensions.
- Edge cases: do not join to line/order tables to invent lower-grain attribution. Do not assume full-year source completeness; distinguish “sum of matching records” from a complete year. Never assume USD/VND. Revenue may not reconcile to order-item sales because sources and definitions can differ.

### `commerce.invoices` — approved invoice header projection

- Grain / PK: one published approved invoice per `invoice_id`; FK to `public.invoice_extractions.invoice_id` with cascade deletion.
- DB columns: `invoice_id TEXT PK`; `source_filename TEXT NOT NULL`; `source_sha256 TEXT NOT NULL UNIQUE`; `invoice_no TEXT NULL`; `invoice_date DATE NULL`; `buyer TEXT NULL`; `seller TEXT NULL`; `subtotal NUMERIC NULL >= 0 and finite`; `tax_amount NUMERIC NULL >= 0 and finite`; `total_amount NUMERIC NULL >= 0 and finite`; `currency TEXT NULL`, when present matching three uppercase letters.
- SQL allowlist: `invoice_id, source_filename, invoice_no, invoice_date, buyer, seller, subtotal, tax_amount, total_amount, currency`. `source_sha256` exists in the DB migration but is not approved for generated SQL.
- Semantics: only approved projections are visible here. Reprocessing/editing the source extraction deletes the published projection until approved again. Header values may be NULL; a syntactically valid ISO currency code does not prove conversion compatibility across invoices.
- Edge cases: do not sum mixed currencies. Do not assume header total equals subtotal + tax (rounding, fees, extraction differences); compare only as an explicit data-quality check and report gaps. Duplicate invoice numbers may occur; `invoice_id` is the key. Exclude or separately report NULL dates/amounts for time/value metrics. Invoice data is separate from synthetic orders/sales.

### `commerce.invoice_items` — approved invoice line projection

- Grain / PK: one row per `(invoice_id, line_no)`; `invoice_id` FK invoices with cascade deletion.
- Columns: `invoice_id TEXT NOT NULL`; `line_no INTEGER NOT NULL > 0`; `description TEXT NULL`; `unit TEXT NULL`; `quantity NUMERIC NULL >= 0 and finite`; `unit_price NUMERIC NULL >= 0 and finite`; `amount NUMERIC NULL >= 0 and finite`.
- Semantics: projection from the approved invoice snapshot; each line is not guaranteed to have quantity, unit price, and amount. SQL allowlist includes all listed columns.
- Edge cases: NULL amount is unknown, not zero. Do not derive amount as `quantity * unit_price` unless explicitly requested as an audit comparison; discounts/taxes/rounding may explain differences. Units may differ across invoices; do not aggregate quantities across units. Join to headers at invoice grain only after aggregating lines when mixing header and line measures.

## 3. Approved relationship graph and cardinality

Only these key relationships are currently approved by the SQL validator:

| Relationship | Cardinality / safe use |
| --- | --- |
| invoices.invoice_id = invoice_items.invoice_id | Header 1 → N lines; aggregate lines to invoice before combining with header amounts. |
| customers.customer_id = orders.customer_id | Customer 1 → N orders. |
| customers.zip = geography.zip | Geography 1 → N customer profiles; ZIP may be NULL. |
| orders.zip = geography.zip | Geography 1 → N orders; use for order destination region. |
| orders.order_id = order_items.order_id | Order 1 → N lines. |
| orders.order_id = payments.order_id | Current schema 1 → 0/1 payment row. |
| orders.order_id = shipments.order_id | Current schema 1 → 0/1 shipment row. |
| order_items.product_id = products.product_id | Product 1 → N lines. |
| order_items.promo_id = promotions.promo_id | Promotion 1 → N tagged lines (slot 1). |
| order_items.promo_id_2 = promotions.promo_id | Promotion 1 → N tagged lines (slot 2); keep slot identity explicit. |
| inventory.product_id = products.product_id | Product 1 → N dated snapshots. |
| returns.order_id = orders.order_id | Order 1 → N return records. |
| returns.product_id = products.product_id | Product 1 → N return records. |
| reviews.order_id = orders.order_id | Order 1 → N reviews. |
| reviews.product_id = products.product_id | Product 1 → N reviews. |

Do not infer any unlisted join (including customers-to-reviews on customer_id, sales-to-orders by date, web_traffic-to-orders by date, or promotions-to-traffic). A valid key equality alone does not prove a requested business relationship.

### Fanout and aggregation rules

1. Identify the fact grain before joining. Pre-aggregate every independent one-to-many fact to the common key (e.g. returns by order/product; lines by order; reviews by product) before joining it to another fact.
2. Do not sum order-level payment/shipping/header amounts after joining to multiple order lines, returns, or reviews without first reducing to one row per order.
3. `COUNT(*)` counts joined rows; use a distinct entity key only when that is the metric definition. `SUM(DISTINCT amount)` is not a general fanout repair because equal valid amounts collapse.
4. Keep unmatched rows visible when required by the question (LEFT JOIN); inner joins silently exclude missing dimension keys. Report unknown/unmatched groups where material.
5. Do not use both `promo_id` slots through one undifferentiated join if attribution must avoid double counting. Preserve which slot matched and disclose multi-promotion attribution.

## 4. Metric contracts: current definitions and open definitions

### Existing ontology definitions

These are existing application definitions and should be preferred when their wording matches the request. Apply the listed grain and filters; do not silently swap to a similarly named source.

| Metric | Formula / grain | Conditions and limitations |
| --- | --- | --- |
| Company revenue | `SUM(sales.revenue)`, daily rows | `commerce.sales`; currency unknown; company-level only; matching rows do not prove complete time coverage. |
| Company COGS | `SUM(sales.cogs)`, daily rows | `commerce.sales`; company-level only. |
| Company gross profit | `SUM(sales.revenue) - SUM(sales.cogs)` | `commerce.sales`; currency unknown. |
| Product / regional order-line revenue | `SUM(quantity * unit_price - discount_amount)`, order-item grain | Join order_items → orders and optionally products/geography. Existing ontology requires `orders.order_status = 'delivered'`. Result may not reconcile to `commerce.sales.revenue`. |
| Order count | `COUNT(DISTINCT order_id)` | Filter by `order_date`, status, customer, or order geography only as requested/defined. |
| Average order value | item-sales sum / `COUNT(DISTINCT order_id)` | Aggregate at order population; state delivered-status scope when using the existing product revenue definition. Denominator zero → NULL/undefined, never infinity or invented 0. |
| Return rate | Existing ontology uses distinct returned orders / distinct orders | This is an order incidence rate, not returned units or refund value. Use the exact ontology definition and denominator scope. |
| Inventory point-in-time metrics | product-snapshot grain | Select an exact snapshot date; state it. Never add stock balances across dates. |
| Shipment duration | `delivery_date - ship_date`, order grain | Only when both dates exist; this is observed elapsed calendar days, not SLA/lead-time performance or causal diagnosis. |
| Return rate | `COUNT(DISTINCT returns.order_id) / NULLIF(COUNT(DISTINCT orders.order_id), 0)` | Existing ontology means returned-order incidence, not returned units or refund value. Use requested `return_date`/region/product scope consistently. |
| Returned order count | `COUNT(DISTINCT returns.order_id)` | Count orders with a return record, not return rows or returned units. |
| Average rating | `AVG(reviews.rating)`, review grain | No representativeness claim; missing reviews are not zero ratings. |
| Sessions | `SUM(web_traffic.sessions)` | Additive across daily/source rows as stored; does not count unique people or conversions. |
| Bounce rate | `AVG(web_traffic.bounce_rate)` | Existing ontology uses an unweighted mean. Do not replace with a session-weighted mean without an approved denominator/definition. |
| Delivery time | `AVG(shipments.delivery_date - shipments.ship_date)` | Exclude rows missing either date; calendar days, grouped by shipment date/region only when requested. |
| Promotion discount | `SUM(order_items.discount_amount)` | Existing ontology names the source promotions + order_items, but formula sums line discount values; do not assume promo IDs prove full amount attribution or multiply per-item. |
| Invoice count | `COUNT(DISTINCT invoices.invoice_id)` | Exclude no rows unless scope requests dates/buyer/seller/currency. |
| Invoice total / tax | `SUM(invoices.total_amount)` / `SUM(invoices.tax_amount)` | Group or filter by currency; NULL amount is missing, not zero. |
| Invoice line amount | `SUM(invoice_items.amount)` | Join to invoice headers only after line aggregation if mixing grains; respect currency. |

Inventory metric aliases/formulas are maintained in `data/semantic/vietstyle_metrics_v1.yaml`; apply them only within a single selected snapshot unless the metric definition says otherwise. In particular, rates/flags are not additive across dates, count denominators include observed product rows only, and existing unresolved catalog entries have no executable formula.

### Unresolved until approved

The following are not interchangeable. If the user’s wording does not select one and the choice materially changes the answer, ask a focused clarification. If one SQL interpretation is still useful, run it only when safe and label the metric as a proxy/unresolved definition.

- “Best-selling” may mean units sold, order count, revenue, or net revenue after returns. Do not choose one based on a keyword alone.
- Product gross profit/margin from catalog `products.cogs` is a proxy unless the cost timing and return-cost treatment are approved. Revenue, net revenue, contribution profit, and gross margin are different metrics.
- Returns: order incidence, returned-unit rate, refund rate, and net sales after refunds need separate denominators and date scopes.
- Promotion effectiveness/ROI/ROAS/incrementality cannot be established without spend and counterfactual evidence; tagged sales are descriptive attribution only.
- Customer lifetime value, conversion, repeat purchase, churn, inventory demand, reorder point, and forecast metrics require approved cohort/window/formula and data-quality criteria.
- `fill_rate`, `sell_through_rate`, `days_of_supply`, and stored inventory flags may have source-defined formulas that are not present in the schema. Return stored values as stored; do not reverse-engineer or recompute them as canonical without approval.
- Cross-currency invoice aggregation requires consistent currency or an approved exchange-rate policy. Duplicate invoice number/credit-note treatment is unresolved; the current projection has no explicit document type, exchange rate, or credit-note field.

## 5. Time, null, units, and scope policies

- Use half-open date windows `[start_date, end_date)` when constructing timestamp boundaries; for DATE columns use explicit inclusive/exclusive boundaries consistently. State the interpreted timezone only if timestamps enter the query; current business dates are DATE values and no timezone is encoded.
- A year request means calendar year unless the user asks for fiscal year. Do not call the latest available year “this year” without comparing it to the current date and data coverage.
- “Latest”, “last month”, or “recent” should use the relevant fact’s max date, not the server clock, when the task means latest observed data. State the selected date/window and distinguish an incomplete period from a complete one.
- Missing data is not zero. Empty result means no matching observations in the selected scope, not proof that the real-world quantity is zero.
- Use `NULLIF(denominator, 0)` for ratios; report undefined/NULL when no eligible denominator. Do not silently COALESCE NULL rates or missing facts to zero unless the metric contract explicitly requires it.
- Preserve source numeric precision for computation; round only for presentation and state the rounding convention when material.
- Currency is unknown for synthetic sales/order metrics. Invoice `currency` is per invoice and can be NULL; aggregate only within one known currency or return separate currency groups. Never assume USD, VND, or perform implicit FX conversion.
- Distinguish calendar days from business days. No holiday/workday calendar is supplied.
- The validator caps query output at 200 rows. A truncated/top-N result must not be described as an exhaustive list.

## 6. Safe response requirements for SQL/Auto

Every answer should:

1. Name the selected metric in plain language and cite the actual table source.
2. State the time window and exact snapshot date when applicable.
3. State required metric filters (including delivered status for the existing order-line revenue definition) and disclose material missing/unmatched/null rows.
4. Separate observed facts from proxies, assumptions, and unresolved definitions. Do not invent a filter, unit, currency, complete-period claim, causal effect, or business recommendation unsupported by these tables.
5. If metric mapping is unresolved, retrieve this contract and relevant metric knowledge first. When still unresolved, keep the SQL findings and explain which metric could not be identified; ask only the clarification needed to select a definition. Do not discard valid query evidence just because a semantic metric label is unresolved.
6. If SQL validation rejects a query, report the specific validation reason and keep the rejected query visible for debugging; do not present rejected SQL as executed evidence.

## 7. Provenance and maintenance

This v1.0.0 contract is derived from the migrations and runtime SQL allowlist named in the front matter. It is not a live introspection dump. Update the version and re-review the table catalog, join cardinalities, metric definitions, and edge cases whenever a migration, `APPROVED_COLUMNS`, `APPROVED_JOINS`, `PRIMARY_KEYS`, or metric ontology changes. Business metric changes require an explicit owner/approval; RAG retrieval alone does not approve a formula.
