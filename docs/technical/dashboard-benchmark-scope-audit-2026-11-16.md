# Dashboard benchmark: 25-question scope and data audit

Date: 2026-11-16 (Asia/Saigon). Input: the user's pasted DB-01–DB-25 benchmark.
Assessment uses current local source, metric catalog, schema discovery and read-only
database aggregates. This is **not** an end-to-end pass rate from running all 25 prompts.
English/Vietnamese model equivalence has not been benchmarked.

## Data actually available

| Source | First / last observation | Important consequence |
|---|---|---|
| sales | 2025-11-14 / 2026-11-13 | 2026 has January–November observations; December is absent and November partial |
| web_traffic | 2025-11-14 / 2026-11-13 | Same coverage; total sessions is SUM(sessions), not COUNT(rows) |
| inventory | 2025-11-30 / 2026-11-13 | Latest three snapshots: 2026-11-13, 2026-10-31, 2026-09-30 |
| orders | 2025-11-14 / 2026-11-13 | Order count uses distinct order_id when counting orders |
| returns | 2025-12-07 / 2026-10-17 | No later return observations; distinguish return records from returned orders |
| shipments | 2025-11-15 / 2026-11-12 | Recorded rows can be counted; do not infer unrecorded delivery events |

Latest inventory: 97 rows, 97 distinct non-NULL product IDs, 97 known stockout/overstock
flags. Products: 97 rows / 97 distinct IDs. Payments: 1,000 rows / 1,000 distinct order IDs;
shipments: 996 / 996; returns: 44 / 44 distinct return IDs. These observed equalities do
not establish future uniqueness constraints. Payments has no payment event date.
Sales has date/revenue/cogs but no category. Product revenue has a separate reviewed
delivered-order-item formula and may differ from sales revenue. There are no employee
salary/bank fields in the configured analytics schema and no sales observations in 2035.

## Question-by-question assessment

“Within scope” means data/operations/representations are available, not that every model
generation will succeed. The current limit remains two independent datasets, eight
outputs, and two charts per dataset. Statistical summaries describe returned aggregates.

| ID | Current assessment | Database / metric / workflow finding |
|---|---|---|
| DB-01 | Within scope | July–September revenue exists. Two queries: monthly revenue for line/summary, independent overall SUM for KPI. |
| DB-02 | Within scope | Yearly SUM plus bar/summary is supported. Available 2025 and 2026 observations cover partial calendar years; disclose that. |
| DB-03 | Within scope, partial observations | Line/KPI/summary is supported; use actual Jan–Nov 2026 rows, no December fabrication. |
| DB-04 | Within scope | Total SUM(sessions) plus monthly SUM at two grains. Earlier GPT failed date retention while Qwen passed; model success is not guaranteed. |
| DB-05 | Within scope after local count changes | One count query supplies three distinct-SKU counters and three KPIs. Both models passed the exact EN prompt against references. `expect` requests a table absent from the question. |
| DB-06 | Within scope | Revenue and COGS exist in sales, with compatible but unconfirmed currency units. One monthly dataset can supply two charts and descriptive summaries. |
| DB-07 | Within scope | One monthly dataset supplies line and table; redundant chart grouping and grouping columns in tables have local fixes. |
| DB-08 | Within scope | Accepted stockout-rate definition, category grouping and latest snapshot exist. One result can supply bar/table. Model mapping/manifest errors remain possible. |
| DB-09 | Needs business clarification | Recorded indicators are boolean product values. Ask whether the desired category output is flagged SKU counts, rates, or product-level statuses. Data exists; do not silently SUM booleans. |
| DB-10 | Within scope | One monthly traffic dataset supports sessions/page-views charts and summaries of returned months. Do not fill absent months with zero. |
| DB-11 | Partial: caveat gap | Approved orders→order_items→products path supports COUNT(DISTINCT orders.order_id) by category. Overlapping category membership is real; the dashboard does not deterministically attach the requested overlap caveat. |
| DB-12 | Within scope | Products has product_id/category. Single-source distinct counts can supply bar/table without needing a date scope. |
| DB-13 | Workflow/representation gap | Data contains three latest snapshots. Typed inventory time supports latest/snapshot/range/history, not latest-N; snapshot×category comparisons may need pivot/series support beyond one chart dimension. |
| DB-14 | Within scope | Returns has return_date and return_id. Monthly recorded-return counts and summaries are possible through existing SQL; do not substitute distinct returned-order counts. |
| DB-15 | Within scope | Shipments has ship_date/order_id; monthly recorded row counts support line/table. Record counts are not proof of unique shipment events. |
| DB-16 | Outside current scope | Revenue, traffic and inventory data exists for Jul–Sep, but this naturally needs three independent grains/datasets. Current cap is two; broader cross-domain composition remains deferred. |
| DB-17 | Period-parser/calculation gap | Data exists, with Jul–Dec only observed through Nov 13. Current period parser reads Jan–Jun from the two-period prose; independent-query date validation then rejects the second period. Also define whether differences mean paired months or period totals. |
| DB-18 | Partial: exception-table gap | Stockout/overstock rates and category summaries are supported. “Exceptions” needs its row grain and OR/AND criterion specified; product/detail or separately filtered exception tables need inventory multi-plan support not established by the current typed path. |
| DB-19 | Needs cohort clarification | Orders/payments/shipments exist. Payments has no payment timestamp, so “payments during 2026” cannot mean payment-event dates. Define order-cohort versus shipment-date scope, and counts of records versus distinct orders; preaggregate to avoid item/payment/shipment fanout. |
| DB-20 | Within scope | Two reusable datasets: monthly revenue for line/summary/table; scalar total for KPI. Jul–Sep data exists. |
| DB-21 | Within scope | Two independent monthly queries/charts preserve currency and sessions separately. No causal narrative or combined ratio is needed. |
| DB-22 | Partial: metric choice and fallback gap | sales revenue has no category; reviewed product revenue is a different delivered-order-item measure. Even for that definition, donut proof currently rejects joins/CTEs. Renderer can offer a table, but the current flow asks for representation selection instead of automatically honoring the conditional fallback. |
| DB-23 | Within scope as empty handling | Database has zero 2035 sales rows. Correct behavior is an explicit empty result, with no fabricated monthly rows or values. |
| DB-24 | Metric/data safety gap | No approved net-profit-margin metric or required expense/tax data. Gross profit from revenue−COGS is not net profit. An offline validator probe accepted an unregistered `net_profit_margin` label with no matched definitions: refusal currently depends too much on model behavior. No such query was executed. |
| DB-25 | Basic denial available; fine-grained RBAC gap | analytics:read and source/column allowlists protect missing salaries/bank fields. Do not claim full private-finance isolation: invoice queries currently share access across analytics readers and lack complete document/row-level financial RBAC. |

## Coverage interpretation

| Engineering assessment | Questions | Share |
|---|---:|---:|
| Within present capability scope, including explicit empty handling | 15/25 | 60% |
| Needs business clarification before defining a correct answer | 2/25 (09, 19) | 8% |
| Beyond declared current scope | 2/25 (13, 16) | 8% |
| Partial behavior / concrete remaining gaps | 6/25 (11, 17, 18, 22, 24, 25) | 24% |

These are scope categories, **not a measured 60% model pass rate**. Count correctness
coverage is separately reported in `dashboard-count-coverage-2026-11-16.md`.
No assertion is made that all 15 supported questions pass repeatedly on GPT-OSS.

## Benchmark corrections before automated grading

- DB-05: explicitly request a table if required. VI should name three separate counts;
  its current “stockout hoặc overstock” wording can be read as a union count.
- DB-09: specify counts/rates/raw flags; allow an actionable clarification as a correct first response.
- DB-11: score overlap disclosure separately from SQL/count correctness.
- DB-13: treat latest-N snapshot support as an explicit feature, not an easy wording variation.
- DB-17: EN requests “differences” but VI omits that requirement. Specify comparison pairing and observed-month policy in both languages.
- DB-18: specify exception-table grain and the flag predicate; distinguish summaries across categories from statistics within groups.
- DB-19: choose order-cohort scope or event dates. Payment-event dates cannot be reconstructed from this schema.
- DB-22: name the approved revenue definition and define whether safe refusal, a table, or an extra representation-selection turn passes.
- DB-23/24/25: correct empty/limitation/denial is success; a generated chart is not required.
- Fix current schema/data snapshot and role, and grade canonical formulas/date coverage/duplicate safety separately from output tile count. Repeat EN and VI trials per model; preserve repair counts and token use.

Suggested next priorities: close the unknown-financial-metric acceptance gap; retain
the two-dataset cap until broader composition is specified; then add safe period
comparisons and latest-N snapshots. Do not expand scope by silently loosening validators.
