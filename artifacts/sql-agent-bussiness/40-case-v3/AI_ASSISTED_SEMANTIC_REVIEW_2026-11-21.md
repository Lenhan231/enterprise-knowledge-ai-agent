# SQL Benchmark v3 — AI-assisted semantic audit (2026-11-21)

> **Not a completed human review.** This record is an AI-assisted technical review for the user. The two independent human reviewer slots and adjudication remain PENDING; nothing here is authorization to mark `FROZEN` or invent signatures.

- Case-set SHA-256: `56ef0dd5ec0d2fc15539665b91a230a923e1836cc4a18cf5c6fe8fcd795146c6`
- Source: `cases_v3_draft.json`, `gold_sql_v3_draft.json`, `gold_results_v3_provisional.json`, `REVIEW_CHECKLIST.md`.
- Scope: questions, business meanings, Gold SQL, Gold Results, clarify/abstain labels, discriminative power. No SQL Agent source-code audit.
- Verification evidence: 30/30 queries returned the stored 404 rows exactly in earlier independent read-only Supabase re-execution; current population checks are consistent. Matching a generated answer alone is not independent semantic approval.
- Proposal: **34 PROPOSE_APPROVE**, **6 REVISE**, **0 REJECT**; **0 human approvals**.
- Case-level metadata is preserved without modifications. Gold SQL and stored results remain provisional.

## Blocking corrections

1. **B40-002:** request or allow `completed_shipment_count` explicitly.
2. **B40-006:** fix stale metric/intent text to city `Hai Phong` and age group `25-34`, not region and non-NULL.
3. **B40-017:** remove incorrect 'by return-date year' grouping description; years are filters, not grouping.
4. **B40-021:** request or allow `observed_product_count` explicitly.
5. **B40-024:** request or allow `observed_products` explicitly.
6. **B40-029:** change metric/intent from TOP 3 to TOP 2; document all-return-reason tie.

## Known observational limitations

- B40-008: dropping `return_reason IS NOT NULL` has no effect on the selected dataset.
- B40-020: `shipping_fee` is always non-NULL in the 2025 population.
- B40-023: both chosen snapshots have identical 97 product memberships.
- B40-029: all three 2024 reasons total 13 returned units; reversing numeric ranking is equivalent.
- The benchmark's ordered output and aliases policies may penalize alternative but valid presentation; assess independently before freezing.

## Case-by-case proposed decisions

| ID | Behavior | Proposed decision | Review reason |
|---|---|---|---|
| B40-001 | execute | **PROPOSE_APPROVE** | Month × traffic_source SUM(sessions) uses the correct date grain. 48 rows. |
| B40-002 | execute | **REVISE** | REVISE wording or output contract: Gold adds completed_shipment_count (the average denominator), while the question explicitly requests mean duration and missing delivery-date count. This extra column must be explicitly requested or explicitly allowed. |
| B40-003 | execute | **PROPOSE_APPROVE** | Only months containing return records are required. 11 rows, correct count(DISTINCT return_id). |
| B40-004 | execute | **PROPOSE_APPROVE** | AOV = SUM(quantity*unit_price-discount_amount)/COUNT(DISTINCT delivered order_id); uses 2025 order_date. Confirm this declared business AOV policy as part of human sign-off. |
| B40-005 | execute | **PROPOSE_APPROVE** | Largest monthly sum(refund_amount) in Jan-Jun 2024 with earlier-month tie-break. Gold May 2024, 35611.25. |
| B40-006 | execute | **REVISE** | REVISE stale required_metric_or_intent: says 'profile region and non-NULL age_group', but v3 question and SQL correctly filter profile ZIP city='Hai Phong' AND age_group='25-34'. Gold count 17. |
| B40-007 | execute | **PROPOSE_APPROVE** | The cogs>revenue test is applied per daily sales row BEFORE summation, not to yearly totals. 20 qualifying 2024 rows. |
| B40-008 | execute | **PROPOSE_APPROVE** | Gold sums refund by non-NULL reason correctly, but removal of IS NOT NULL is observationally equivalent in 2024; the limitation must be disclosed. |
| B40-009 | execute | **PROPOSE_APPROVE** | Inventory units_sold at exact 2025-10-31 Outdoor snapshot, not transaction quantities. Gold 113. |
| B40-010 | execute | **PROPOSE_APPROVE** | Both paid_search and mobile filters apply to 2025 orders. Gold 20. |
| B40-011 | execute | **PROPOSE_APPROVE** | Catalog products.cogs ranking, not realized transaction-level COGS; 5 products, deterministic product_id tie-break. |
| B40-012 | execute | **PROPOSE_APPROVE** | All order statuses included; ranks order_source by distinct count, deterministic tie-break. |
| B40-013 | execute | **PROPOSE_APPROVE** | Snapshot-stored segment, sum units_received on 2026-11-13, TOP 5. |
| B40-014 | execute | **PROPOSE_APPROVE** | Delivered orders in 2024, destination ZIP -> geography.city, COUNT(DISTINCT customer_id), TOP 5. |
| B40-015 | execute | **PROPOSE_APPROVE** | Delivered 2025 item net amount after discount, current product category, TOP 3 among four categories. |
| B40-016 | execute | **PROPOSE_APPROVE** | Returns filtered by return_date in 2025, joined returns->orders->geography using order destination ZIP. 14 cities. |
| B40-017 | execute | **REVISE** | REVISE stale required_metric_or_intent text ('by product and return-date year'): SQL groups only by product_id, as the question requests, across 2023–2025. Fix metadata; Gold 60 product groups. |
| B40-018 | execute | **PROPOSE_APPROVE** | AVG(rating) over all review history, joined to current category, as requested. |
| B40-019 | execute | **PROPOSE_APPROVE** | Join recorded payments to orders, filter by 2025 order_date, use payments.payment_method, not orders.payment_method. |
| B40-020 | execute | **PROPOSE_APPROVE** | AVG(shipping_fee) by destination city, 2025 ship_date, COUNT(non-NULL fees); all 728 source fees are non-NULL, so NULL-fee sensitivity not exercised. |
| B40-021 | execute | **REVISE** | REVISE mismatch: Gold returns observed_product_count alongside stockout_product_count, but question does not request observed-product denominator. Add it to wording or explicitly allow it in output policy. |
| B40-022 | execute | **PROPOSE_APPROVE** | Per snapshot counts of non-NULL and NULL days_of_supply across 47 snapshots; NULL is not coerced to zero. |
| B40-023 | execute | **PROPOSE_APPROVE** | Both-date membership enforced; stock_delta is after-before. All 97 products exist on both snapshots, so omitting membership HAVING is observationally equivalent. |
| B40-024 | execute | **REVISE** | REVISE mismatch: Gold also returns observed_products alongside requested per-snapshot stock total; update question or output policy. Never sum stock across dates. |
| B40-025 | execute | **PROPOSE_APPROVE** | AVG(days_of_supply) remains NULL for all four categories at 2025-10-31, with observed/NULL counts; correct NULL semantics. |
| B40-026 | execute | **PROPOSE_APPROVE** | Uses approved frozen prior-question context: company COGS in 2024, grouped by month. This tests context-conditioned SQL only, not full conversation memory. |
| B40-027 | execute | **PROPOSE_APPROVE** | Uses inherited year 2025, preserves order_source grouping, filters delivered. Counts 719 delivered of 733 orders; omission of delivered is detectable. |
| B40-028 | execute | **PROPOSE_APPROVE** | Pairs 2023 and 2024 same calendar month, computes SUM(revenue)-SUM(cogs) and year-to-year difference; 12 monthly output rows, correct. |
| B40-029 | execute | **REVISE** | REVISE stale required_metric_or_intent: 'top three' conflicts with requested TOP 2 and SQL LIMIT 2. Correct metadata. All three return reasons tie at 13 units, so numerical ranking direction is not distinguishable here. |
| B40-030 | execute | **PROPOSE_APPROVE** | Inherits 2025-10-31 inventory snapshot, ranks stockout_days DESC with product_id ASC tie-break. Context-conditioned SQL only. |
| B40-031 | clarify | **PROPOSE_APPROVE** | CLARIFY is correct: comparison periods and definition/source of revenue are unresolved. |
| B40-032 | clarify | **PROPOSE_APPROVE** | CLARIFY is correct: 'best customer' requires metric and date period. |
| B40-033 | clarify | **PROPOSE_APPROVE** | CLARIFY is correct: product identifier, historical snapshot date, and real-time versus historical scope are missing. |
| B40-034 | clarify | **PROPOSE_APPROVE** | CLARIFY is defensible: no approved customer-level profit/realized COGS attribution contract. |
| B40-035 | clarify | **PROPOSE_APPROVE** | CLARIFY is correct: Tet date window, baseline and revenue definition are not fixed. |
| B40-036 | abstain_without_query | **PROPOSE_APPROVE** | ABSTAIN without business SQL: no campaign spend or approved attributed revenue/ROAS data. |
| B40-037 | abstain_without_query | **PROPOSE_APPROVE** | ABSTAIN without business SQL: employee and commission facts are absent. |
| B40-038 | abstain_without_query | **PROPOSE_APPROVE** | ABSTAIN without business SQL: no carrier key or promised delivery SLA date. |
| B40-039 | abstain_without_query | **PROPOSE_APPROVE** | ABSTAIN without business SQL: destructive DELETE is forbidden by read-only analysis boundary. |
| B40-040 | abstain_without_query | **PROPOSE_APPROVE** | ABSTAIN without business SQL: approved schema lacks email, phone and VIP classification; do not infer personally identifying details. |

## Gold SQL and result evidence for execute cases

### B40-001: Tổng số sessions theo từng tháng và traffic_source trong năm 2024.

**Proposed decision:** PROPOSE_APPROVE. Month × traffic_source SUM(sessions) uses the correct date grain. 48 rows.

```sql
SELECT DATE_TRUNC('month', w.date)::date AS month, w.traffic_source, SUM(w.sessions) AS sessions FROM commerce.web_traffic AS w WHERE w.date >= $1 AND w.date < $2 GROUP BY DATE_TRUNC('month', w.date)::date, w.traffic_source ORDER BY month ASC, w.traffic_source ASC LIMIT 200
```

Parameters: `["2024-01-01","2025-01-01"]`. Stored rows: 48. Sample:

```json
[
  {
    "month": "2024-01-01",
    "traffic_source": "email_campaign",
    "sessions": 86955
  },
  {
    "month": "2024-01-01",
    "traffic_source": "organic_search",
    "sessions": 93062
  }
]
```

### B40-002: Thời gian giao hàng trung bình theo tháng gửi trong năm 2025, chỉ tính shipment đã có delivery_date; cho biết thêm số shipment thiếu delivery_date theo từng tháng.

**Proposed decision:** REVISE. REVISE wording or output contract: Gold adds completed_shipment_count (the average denominator), while the question explicitly requests mean duration and missing delivery-date count. This extra column must be explicitly requested or explicitly allowed.

```sql
SELECT DATE_TRUNC('month', s.ship_date)::date AS month, AVG(s.delivery_date - s.ship_date) FILTER (WHERE s.delivery_date IS NOT NULL) AS average_delivery_days, COUNT(s.delivery_date) AS completed_shipment_count, COUNT(*) FILTER (WHERE s.delivery_date IS NULL) AS missing_delivery_date_count FROM commerce.shipments AS s WHERE s.ship_date >= $1 AND s.ship_date < $2 GROUP BY DATE_TRUNC('month', s.ship_date)::date ORDER BY month ASC LIMIT 200
```

Parameters: `["2025-01-01","2026-01-01"]`. Stored rows: 12. Sample:

```json
[
  {
    "month": "2025-01-01",
    "average_delivery_days": "2.9491525423728814",
    "completed_shipment_count": 59,
    "missing_delivery_date_count": 0
  },
  {
    "month": "2025-02-01",
    "average_delivery_days": "3.0727272727272727",
    "completed_shipment_count": 55,
    "missing_delivery_date_count": 0
  }
]
```

### B40-003: Trong các tháng có return record, có bao nhiêu return record mỗi tháng năm 2025, tính theo return_date?

**Proposed decision:** PROPOSE_APPROVE. Only months containing return records are required. 11 rows, correct count(DISTINCT return_id).

```sql
SELECT DATE_TRUNC('month', r.return_date)::date AS month, COUNT(DISTINCT r.return_id) AS return_count FROM commerce.returns AS r WHERE r.return_date >= $1 AND r.return_date < $2 GROUP BY DATE_TRUNC('month', r.return_date)::date ORDER BY month ASC LIMIT 12
```

Parameters: `["2025-01-01","2026-01-01"]`. Stored rows: 11. Sample:

```json
[
  {
    "month": "2025-01-01",
    "return_count": 4
  },
  {
    "month": "2025-02-01",
    "return_count": 2
  }
]
```

### B40-004: Giá trị đơn hàng trung bình theo tháng trong năm 2025, chỉ tính đơn đã giao.

**Proposed decision:** PROPOSE_APPROVE. AOV = SUM(quantity*unit_price-discount_amount)/COUNT(DISTINCT delivered order_id); uses 2025 order_date. Confirm this declared business AOV policy as part of human sign-off.

```sql
SELECT DATE_TRUNC('month', o.order_date)::date AS month, SUM(oi.quantity * oi.unit_price - oi.discount_amount) / NULLIF(COUNT(DISTINCT o.order_id), 0) AS average_order_value FROM commerce.orders AS o JOIN commerce.order_items AS oi ON oi.order_id = o.order_id WHERE o.order_status = $1 AND o.order_date >= $2 AND o.order_date < $3 GROUP BY DATE_TRUNC('month', o.order_date)::date ORDER BY month ASC LIMIT 12
```

Parameters: `["delivered","2025-01-01","2026-01-01"]`. Stored rows: 12. Sample:

```json
[
  {
    "month": "2025-01-01",
    "average_order_value": "15358.450333333333"
  },
  {
    "month": "2025-02-01",
    "average_order_value": "12301.875000000000"
  }
]
```

### B40-005: Tháng nào có tổng refund_amount cao nhất trong 6 tháng đầu năm 2024? Nếu bằng nhau, chọn tháng sớm hơn.

**Proposed decision:** PROPOSE_APPROVE. Largest monthly sum(refund_amount) in Jan-Jun 2024 with earlier-month tie-break. Gold May 2024, 35611.25.

```sql
SELECT DATE_TRUNC('month', r.return_date)::date AS month, SUM(r.refund_amount) AS refund_amount FROM commerce.returns AS r WHERE r.return_date >= $1 AND r.return_date < $2 GROUP BY DATE_TRUNC('month', r.return_date)::date ORDER BY refund_amount DESC, month ASC LIMIT 1
```

Parameters: `["2024-01-01","2024-07-01"]`. Stored rows: 1. Sample:

```json
[
  {
    "month": "2024-05-01",
    "refund_amount": "35611.25"
  }
]
```

### B40-006: Trong năm 2024, có bao nhiêu khách hàng đăng ký có profile ZIP ánh xạ đến thành phố Hai Phong và age_group là 25-34?

**Proposed decision:** REVISE. REVISE stale required_metric_or_intent: says 'profile region and non-NULL age_group', but v3 question and SQL correctly filter profile ZIP city='Hai Phong' AND age_group='25-34'. Gold count 17.

```sql
SELECT COUNT(DISTINCT c.customer_id) AS customer_count FROM commerce.customers AS c JOIN commerce.geography AS g ON g.zip = c.zip WHERE g.city = $1 AND c.age_group = $2 AND c.signup_date >= $3 AND c.signup_date < $4 LIMIT 1
```

Parameters: `["Hai Phong","25-34","2024-01-01","2025-01-01"]`. Stored rows: 1. Sample:

```json
[
  {
    "customer_count": 17
  }
]
```

### B40-007: Trong năm 2024, tổng revenue và COGS của những ngày có COGS lớn hơn revenue là bao nhiêu?

**Proposed decision:** PROPOSE_APPROVE. The cogs>revenue test is applied per daily sales row BEFORE summation, not to yearly totals. 20 qualifying 2024 rows.

```sql
SELECT SUM(s.revenue) AS revenue, SUM(s.cogs) AS cogs FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 AND s.cogs > s.revenue LIMIT 1
```

Parameters: `["2024-01-01","2025-01-01"]`. Stored rows: 1. Sample:

```json
[
  {
    "revenue": "371200.82",
    "cogs": "382742.90"
  }
]
```

### B40-008: Tổng refund_amount theo từng return_reason trong năm 2024, chỉ tính return_reason không NULL.

**Proposed decision:** PROPOSE_APPROVE. Gold sums refund by non-NULL reason correctly, but removal of IS NOT NULL is observationally equivalent in 2024; the limitation must be disclosed.

```sql
SELECT r.return_reason, SUM(r.refund_amount) AS refund_amount FROM commerce.returns AS r WHERE r.return_date >= $1 AND r.return_date < $2 AND r.return_reason IS NOT NULL GROUP BY r.return_reason ORDER BY refund_amount DESC, r.return_reason ASC LIMIT 200
```

Parameters: `["2024-01-01","2025-01-01"]`. Stored rows: 3. Sample:

```json
[
  {
    "return_reason": "Size exchange",
    "refund_amount": "92064.49"
  },
  {
    "return_reason": "Changed mind",
    "refund_amount": "62837.92"
  }
]
```

### B40-009: Tổng inventory.units_sold cho category Outdoor tại snapshot 2025-10-31.

**Proposed decision:** PROPOSE_APPROVE. Inventory units_sold at exact 2025-10-31 Outdoor snapshot, not transaction quantities. Gold 113.

```sql
SELECT SUM(i.units_sold) AS units_sold FROM commerce.inventory AS i WHERE i.snapshot_date = $1 AND i.category = $2 LIMIT 1
```

Parameters: `["2025-10-31","Outdoor"]`. Stored rows: 1. Sample:

```json
[
  {
    "units_sold": 113
  }
]
```

### B40-010: Trong năm 2025, có bao nhiêu đơn từ paid_search được đặt trên thiết bị mobile?

**Proposed decision:** PROPOSE_APPROVE. Both paid_search and mobile filters apply to 2025 orders. Gold 20.

```sql
SELECT COUNT(DISTINCT o.order_id) AS order_count FROM commerce.orders AS o WHERE o.order_date >= $1 AND o.order_date < $2 AND o.order_source = $3 AND o.device_type = $4 LIMIT 1
```

Parameters: `["2025-01-01","2026-01-01","paid_search","mobile"]`. Stored rows: 1. Sample:

```json
[
  {
    "order_count": 20
  }
]
```

### B40-011: Rank the five products with the highest catalog COGS; return product_id and catalog cogs, ties by product_id ascending.

**Proposed decision:** PROPOSE_APPROVE. Catalog products.cogs ranking, not realized transaction-level COGS; 5 products, deterministic product_id tie-break.

```sql
SELECT p.product_id, p.cogs AS catalog_cogs FROM commerce.products AS p ORDER BY catalog_cogs DESC, p.product_id ASC LIMIT 5
```

Parameters: `[]`. Stored rows: 5. Sample:

```json
[
  {
    "product_id": 506,
    "catalog_cogs": "14463.03045555477"
  },
  {
    "product_id": 494,
    "catalog_cogs": "13062.185815573772"
  }
]
```

### B40-012: Xếp hạng order_source theo số đơn hàng trong năm 2024, tính mọi trạng thái; nếu bằng nhau sắp order_source tăng dần.

**Proposed decision:** PROPOSE_APPROVE. All order statuses included; ranks order_source by distinct count, deterministic tie-break.

```sql
SELECT o.order_source, COUNT(DISTINCT o.order_id) AS order_count FROM commerce.orders AS o WHERE o.order_date >= $1 AND o.order_date < $2 GROUP BY o.order_source ORDER BY order_count DESC, o.order_source ASC NULLS LAST LIMIT 200
```

Parameters: `["2024-01-01","2025-01-01"]`. Stored rows: 6. Sample:

```json
[
  {
    "order_source": "email_campaign",
    "order_count": 120
  },
  {
    "order_source": "organic_search",
    "order_count": 119
  }
]
```

### B40-013: Tại snapshot 2026-11-13, top 5 segment theo tổng units_received; nếu bằng nhau sắp segment tăng dần.

**Proposed decision:** PROPOSE_APPROVE. Snapshot-stored segment, sum units_received on 2026-11-13, TOP 5.

```sql
SELECT i.segment, SUM(i.units_received) AS units_received FROM commerce.inventory AS i WHERE i.snapshot_date = $1 GROUP BY i.segment ORDER BY units_received DESC, i.segment ASC NULLS LAST LIMIT 5
```

Parameters: `["2026-11-13"]`. Stored rows: 5. Sample:

```json
[
  {
    "segment": "Activewear",
    "units_received": 497
  },
  {
    "segment": "Everyday",
    "units_received": 129
  }
]
```

### B40-014: Which destination cities had the most distinct customers with a delivered order in 2024? Return the top 5, ties by city ascending.

**Proposed decision:** PROPOSE_APPROVE. Delivered orders in 2024, destination ZIP -> geography.city, COUNT(DISTINCT customer_id), TOP 5.

```sql
SELECT g.city, COUNT(DISTINCT o.customer_id) AS customer_count FROM commerce.orders AS o JOIN commerce.geography AS g ON g.zip = o.zip WHERE o.order_status = $1 AND o.order_date >= $2 AND o.order_date < $3 GROUP BY g.city ORDER BY customer_count DESC, g.city ASC LIMIT 5
```

Parameters: `["delivered","2024-01-01","2025-01-01"]`. Stored rows: 5. Sample:

```json
[
  {
    "city": "Phu Ly",
    "customer_count": 96
  },
  {
    "city": "Hai Phong",
    "customer_count": 79
  }
]
```

### B40-015: Top 3 danh mục theo doanh thu dòng hàng sau discount_amount của các đơn đã giao trong năm 2025.

**Proposed decision:** PROPOSE_APPROVE. Delivered 2025 item net amount after discount, current product category, TOP 3 among four categories.

```sql
SELECT p.category, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS net_revenue FROM commerce.orders AS o JOIN commerce.order_items AS oi ON oi.order_id = o.order_id JOIN commerce.products AS p ON p.product_id = oi.product_id WHERE o.order_status = $1 AND o.order_date >= $2 AND o.order_date < $3 GROUP BY p.category ORDER BY net_revenue DESC, p.category ASC LIMIT 3
```

Parameters: `["delivered","2025-01-01","2026-01-01"]`. Stored rows: 3. Sample:

```json
[
  {
    "category": "Streetwear",
    "net_revenue": "8685863.04"
  },
  {
    "category": "Outdoor",
    "net_revenue": "3533291.45"
  }
]
```

### B40-016: Tổng return_quantity theo thành phố giao của đơn trong năm 2025, tính theo return_date.

**Proposed decision:** PROPOSE_APPROVE. Returns filtered by return_date in 2025, joined returns->orders->geography using order destination ZIP. 14 cities.

```sql
SELECT g.city, SUM(r.return_quantity) AS returned_units FROM commerce.returns AS r JOIN commerce.orders AS o ON o.order_id = r.order_id JOIN commerce.geography AS g ON g.zip = o.zip WHERE r.return_date >= $1 AND r.return_date < $2 GROUP BY g.city ORDER BY returned_units DESC, g.city ASC LIMIT 200
```

Parameters: `["2025-01-01","2026-01-01"]`. Stored rows: 14. Sample:

```json
[
  {
    "city": "Hai Phong",
    "returned_units": 7
  },
  {
    "city": "Phu Ly",
    "returned_units": 7
  }
]
```

### B40-017: Tổng số lượng hàng trả theo product_id từ năm 2023 đến hết năm 2025, tính theo return_date.

**Proposed decision:** REVISE. REVISE stale required_metric_or_intent text ('by product and return-date year'): SQL groups only by product_id, as the question requests, across 2023–2025. Fix metadata; Gold 60 product groups.

```sql
SELECT r.product_id, SUM(r.return_quantity) AS returned_units FROM commerce.returns AS r WHERE r.return_date >= $1 AND r.return_date < $2 GROUP BY r.product_id ORDER BY returned_units DESC, r.product_id ASC LIMIT 200
```

Parameters: `["2023-01-01","2026-01-01"]`. Stored rows: 60. Sample:

```json
[
  {
    "product_id": 1958,
    "returned_units": 4
  },
  {
    "product_id": 136,
    "returned_units": 3
  }
]
```

### B40-018: Điểm đánh giá trung bình theo category hiện tại của sản phẩm, dùng toàn bộ review history.

**Proposed decision:** PROPOSE_APPROVE. AVG(rating) over all review history, joined to current category, as requested.

```sql
SELECT p.category, AVG(r.rating) AS avg_rating FROM commerce.reviews AS r JOIN commerce.products AS p ON p.product_id = r.product_id GROUP BY p.category ORDER BY avg_rating DESC, p.category ASC LIMIT 200
```

Parameters: `[]`. Stored rows: 4. Sample:

```json
[
  {
    "category": "GenZ",
    "avg_rating": "4.0909090909090909"
  },
  {
    "category": "Outdoor",
    "avg_rating": "4.0500000000000000"
  }
]
```

### B40-019: Tổng payment_value đã ghi nhận theo payment_method cho các đơn có order_date trong năm 2025.

**Proposed decision:** PROPOSE_APPROVE. Join recorded payments to orders, filter by 2025 order_date, use payments.payment_method, not orders.payment_method.

```sql
SELECT p.payment_method, SUM(p.payment_value) AS payment_value FROM commerce.orders AS o JOIN commerce.payments AS p ON p.order_id = o.order_id WHERE o.order_date >= $1 AND o.order_date < $2 GROUP BY p.payment_method ORDER BY payment_value DESC, p.payment_method ASC LIMIT 200
```

Parameters: `["2025-01-01","2026-01-01"]`. Stored rows: 5. Sample:

```json
[
  {
    "payment_method": "credit_card",
    "payment_value": "4041768.40"
  },
  {
    "payment_method": "paypal",
    "payment_value": "2704772.54"
  }
]
```

### B40-020: Phí shipping trung bình theo thành phố giao hàng, cho các shipment có ship_date trong năm 2025; báo thêm số phí không NULL.

**Proposed decision:** PROPOSE_APPROVE. AVG(shipping_fee) by destination city, 2025 ship_date, COUNT(non-NULL fees); all 728 source fees are non-NULL, so NULL-fee sensitivity not exercised.

```sql
SELECT g.city, AVG(s.shipping_fee) AS average_shipping_fee, COUNT(s.shipping_fee) AS fee_observation_count FROM commerce.shipments AS s JOIN commerce.orders AS o ON o.order_id = s.order_id JOIN commerce.geography AS g ON g.zip = o.zip WHERE s.ship_date >= $1 AND s.ship_date < $2 GROUP BY g.city ORDER BY average_shipping_fee DESC NULLS LAST, g.city ASC LIMIT 200
```

Parameters: `["2025-01-01","2026-01-01"]`. Stored rows: 14. Sample:

```json
[
  {
    "city": "Bac Giang",
    "average_shipping_fee": "14047.935714285714",
    "fee_observation_count": 49
  },
  {
    "city": "Bac Ninh",
    "average_shipping_fee": "13860.696981132075",
    "fee_observation_count": 53
  }
]
```

### B40-021: Tại snapshot 2026-11-13, đếm số sản phẩm có stockout_flag = TRUE theo từng category.

**Proposed decision:** REVISE. REVISE mismatch: Gold returns observed_product_count alongside stockout_product_count, but question does not request observed-product denominator. Add it to wording or explicitly allow it in output policy.

```sql
SELECT i.category, COUNT(*) FILTER (WHERE i.stockout_flag = TRUE) AS stockout_product_count, COUNT(DISTINCT i.product_id) AS observed_product_count FROM commerce.inventory AS i WHERE i.snapshot_date = $1 GROUP BY i.category ORDER BY stockout_product_count DESC, i.category ASC NULLS LAST LIMIT 200
```

Parameters: `["2026-11-13"]`. Stored rows: 4. Sample:

```json
[
  {
    "category": "Outdoor",
    "stockout_product_count": 10,
    "observed_product_count": 57
  },
  {
    "category": "Streetwear",
    "stockout_product_count": 5,
    "observed_product_count": 33
  }
]
```

### B40-022: Theo từng snapshot tồn kho từ 2023-01-31 đến 2026-11-13, đếm số product có và không có days_of_supply; giữ NULL riêng, không thay bằng 0.

**Proposed decision:** PROPOSE_APPROVE. Per snapshot counts of non-NULL and NULL days_of_supply across 47 snapshots; NULL is not coerced to zero.

```sql
SELECT i.snapshot_date, COUNT(i.days_of_supply) AS products_with_days_of_supply, COUNT(*) FILTER (WHERE i.days_of_supply IS NULL) AS products_without_days_of_supply FROM commerce.inventory AS i WHERE i.snapshot_date >= $1 AND i.snapshot_date <= $2 GROUP BY i.snapshot_date ORDER BY i.snapshot_date ASC LIMIT 100
```

Parameters: `["2023-01-31","2026-11-13"]`. Stored rows: 47. Sample:

```json
[
  {
    "snapshot_date": "2023-01-31",
    "products_with_days_of_supply": 0,
    "products_without_days_of_supply": 97
  },
  {
    "snapshot_date": "2023-02-28",
    "products_with_days_of_supply": 0,
    "products_without_days_of_supply": 97
  }
]
```

### B40-023: So sánh stock_on_hand của các product_id xuất hiện ở cả snapshot 2025-09-30 và 2025-10-31; trả về before, after và after trừ before.

**Proposed decision:** PROPOSE_APPROVE. Both-date membership enforced; stock_delta is after-before. All 97 products exist on both snapshots, so omitting membership HAVING is observationally equivalent.

```sql
SELECT i.product_id, MAX(i.stock_on_hand) FILTER (WHERE i.snapshot_date = $1) AS stock_before, MAX(i.stock_on_hand) FILTER (WHERE i.snapshot_date = $2) AS stock_after, MAX(i.stock_on_hand) FILTER (WHERE i.snapshot_date = $2) - MAX(i.stock_on_hand) FILTER (WHERE i.snapshot_date = $1) AS stock_delta FROM commerce.inventory AS i WHERE i.snapshot_date = $1 OR i.snapshot_date = $2 GROUP BY i.product_id HAVING COUNT(DISTINCT i.snapshot_date) = 2 ORDER BY stock_delta DESC, i.product_id ASC LIMIT 200
```

Parameters: `["2025-09-30","2025-10-31"]`. Stored rows: 97. Sample:

```json
[
  {
    "product_id": 1974,
    "stock_before": 8,
    "stock_after": 24,
    "stock_delta": 16
  },
  {
    "product_id": 1975,
    "stock_before": 15,
    "stock_after": 31,
    "stock_delta": 16
  }
]
```

### B40-024: Tổng stock_on_hand tại từng snapshot từ 2025-09-30 đến 2025-11-30; giữ mỗi snapshot thành một dòng và không cộng số dư giữa các ngày.

**Proposed decision:** REVISE. REVISE mismatch: Gold also returns observed_products alongside requested per-snapshot stock total; update question or output policy. Never sum stock across dates.

```sql
SELECT i.snapshot_date, SUM(i.stock_on_hand) AS observed_stock_total, COUNT(DISTINCT i.product_id) AS observed_products FROM commerce.inventory AS i WHERE i.snapshot_date >= $1 AND i.snapshot_date <= $2 GROUP BY i.snapshot_date ORDER BY i.snapshot_date ASC LIMIT 100
```

Parameters: `["2025-09-30","2025-11-30"]`. Stored rows: 3. Sample:

```json
[
  {
    "snapshot_date": "2025-09-30",
    "observed_stock_total": 11134,
    "observed_products": 97
  },
  {
    "snapshot_date": "2025-10-31",
    "observed_stock_total": 10412,
    "observed_products": 97
  }
]
```

### B40-025: Tại snapshot 2025-10-31, tính trung bình days_of_supply theo category được ghi trong inventory row; báo số non-NULL và NULL, không thay NULL bằng 0.

**Proposed decision:** PROPOSE_APPROVE. AVG(days_of_supply) remains NULL for all four categories at 2025-10-31, with observed/NULL counts; correct NULL semantics.

```sql
SELECT i.category, AVG(i.days_of_supply) AS average_days_of_supply, COUNT(i.days_of_supply) AS nonnull_product_count, COUNT(*) FILTER (WHERE i.days_of_supply IS NULL) AS null_product_count FROM commerce.inventory AS i WHERE i.snapshot_date = $1 GROUP BY i.category ORDER BY average_days_of_supply DESC NULLS LAST, i.category ASC NULLS LAST LIMIT 200
```

Parameters: `["2025-10-31"]`. Stored rows: 4. Sample:

```json
[
  {
    "category": "Casual",
    "average_days_of_supply": null,
    "nonnull_product_count": 0,
    "null_product_count": 1
  },
  {
    "category": "GenZ",
    "average_days_of_supply": null,
    "nonnull_product_count": 0,
    "null_product_count": 6
  }
]
```

### B40-026: Hãy trình bày theo từng tháng.

**Proposed decision:** PROPOSE_APPROVE. Uses approved frozen prior-question context: company COGS in 2024, grouped by month. This tests context-conditioned SQL only, not full conversation memory.

```sql
SELECT DATE_TRUNC('month', s.date)::date AS month, SUM(s.cogs) AS cogs FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 GROUP BY DATE_TRUNC('month', s.date)::date ORDER BY month ASC LIMIT 12
```

Parameters: `["2024-01-01","2025-01-01"]`. Stored rows: 12. Sample:

```json
[
  {
    "month": "2024-01-01",
    "cogs": "1098809.17"
  },
  {
    "month": "2024-02-01",
    "cogs": "718029.17"
  }
]
```

### B40-027: Với thống kê order_source vừa rồi, chỉ giữ các đơn đã giao.

**Proposed decision:** PROPOSE_APPROVE. Uses inherited year 2025, preserves order_source grouping, filters delivered. Counts 719 delivered of 733 orders; omission of delivered is detectable.

```sql
SELECT o.order_source, COUNT(DISTINCT o.order_id) AS order_count FROM commerce.orders AS o WHERE o.order_status = $1 AND o.order_date >= $2 AND o.order_date < $3 GROUP BY o.order_source ORDER BY order_count DESC, o.order_source ASC NULLS LAST LIMIT 200
```

Parameters: `["delivered","2025-01-01","2026-01-01"]`. Stored rows: 6. Sample:

```json
[
  {
    "order_source": "organic_search",
    "order_count": 138
  },
  {
    "order_source": "paid_search",
    "order_count": 129
  }
]
```

### B40-028: Còn so với năm trước theo từng tháng thì sao?

**Proposed decision:** PROPOSE_APPROVE. Pairs 2023 and 2024 same calendar month, computes SUM(revenue)-SUM(cogs) and year-to-year difference; 12 monthly output rows, correct.

```sql
WITH monthly AS (SELECT EXTRACT(YEAR FROM s.date) AS sales_year, EXTRACT(MONTH FROM s.date) AS month, SUM(s.revenue) - SUM(s.cogs) AS gross_profit FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 GROUP BY EXTRACT(YEAR FROM s.date), EXTRACT(MONTH FROM s.date)) SELECT m.month, MAX(m.gross_profit) FILTER (WHERE m.sales_year = 2023) AS gross_profit_2023, MAX(m.gross_profit) FILTER (WHERE m.sales_year = 2024) AS gross_profit_2024, MAX(m.gross_profit) FILTER (WHERE m.sales_year = 2024) - MAX(m.gross_profit) FILTER (WHERE m.sales_year = 2023) AS difference_2024_minus_2023 FROM monthly AS m GROUP BY m.month ORDER BY m.month ASC LIMIT 12
```

Parameters: `["2023-01-01","2025-01-01"]`. Stored rows: 12. Sample:

```json
[
  {
    "month": "1",
    "gross_profit_2023": "223729.62",
    "gross_profit_2024": "218718.84",
    "difference_2024_minus_2023": "-5010.78"
  },
  {
    "month": "2",
    "gross_profit_2023": "284452.46",
    "gross_profit_2024": "134595.00",
    "difference_2024_minus_2023": "-149857.46"
  }
]
```

### B40-029: Trong bảng xếp hạng vừa rồi, chỉ hiện top 2; nếu hòa, xếp tên reason tăng dần.

**Proposed decision:** REVISE. REVISE stale required_metric_or_intent: 'top three' conflicts with requested TOP 2 and SQL LIMIT 2. Correct metadata. All three return reasons tie at 13 units, so numerical ranking direction is not distinguishable here.

```sql
SELECT r.return_reason, SUM(r.return_quantity) AS returned_units FROM commerce.returns AS r WHERE r.return_date >= $1 AND r.return_date < $2 GROUP BY r.return_reason ORDER BY returned_units DESC, r.return_reason ASC NULLS LAST LIMIT 2
```

Parameters: `["2024-01-01","2025-01-01"]`. Stored rows: 2. Sample:

```json
[
  {
    "return_reason": "Changed mind",
    "returned_units": 13
  },
  {
    "return_reason": "Color differed from expectation",
    "returned_units": 13
  }
]
```

### B40-030: Tiếp tục dùng snapshot vừa chọn; xếp hạng top 5 product theo stockout_days giảm dần, tie-break product_id tăng dần.

**Proposed decision:** PROPOSE_APPROVE. Inherits 2025-10-31 inventory snapshot, ranks stockout_days DESC with product_id ASC tie-break. Context-conditioned SQL only.

```sql
SELECT i.product_id, i.stockout_days FROM commerce.inventory AS i WHERE i.snapshot_date = $1 ORDER BY i.stockout_days DESC, i.product_id ASC LIMIT 5
```

Parameters: `["2025-10-31"]`. Stored rows: 5. Sample:

```json
[
  {
    "product_id": 494,
    "stockout_days": 5
  },
  {
    "product_id": 777,
    "stockout_days": 5
  }
]
```

## Clarify / abstain expected response contracts

### B40-031 — clarify

Doanh thu tăng bao nhiêu so với kỳ trước?

Expected response: Bạn muốn so sánh doanh thu của những khoảng thời gian nào, và dùng doanh thu company-level trong commerce.sales hay doanh thu dòng hàng của đơn đã giao?

**Proposed decision:** PROPOSE_APPROVE. CLARIFY is correct: comparison periods and definition/source of revenue are unresolved.

### B40-032 — clarify

Khách hàng nào tốt nhất?

Expected response: Bạn muốn xếp hạng khách hàng theo chỉ số nào (số đơn, doanh thu dòng hàng đã giao hay chỉ số khác) và trong khoảng thời gian nào?

**Proposed decision:** PROPOSE_APPROVE. CLARIFY is correct: 'best customer' requires metric and date period.

### B40-033 — clarify

Tồn kho hiện tại của sản phẩm là bao nhiêu?

Expected response: Bạn muốn tra sản phẩm nào (product_id hoặc tên)? Dữ liệu hiện chỉ có các snapshot tồn kho lịch sử, không có tồn kho thời gian thực. Bạn muốn dùng snapshot lịch sử ngày nào, hay đang cần số liệu real-time mà hệ thống chưa cung cấp?

**Proposed decision:** PROPOSE_APPROVE. CLARIFY is correct: product identifier, historical snapshot date, and real-time versus historical scope are missing.

### B40-034 — clarify

Tính lợi nhuận theo khách hàng năm 2025.

Expected response: Bạn muốn định nghĩa lợi nhuận theo công thức nào? Schema chỉ có gross profit company-level trong commerce.sales; chưa có ledger COGS đã duyệt ở cấp khách hàng.

**Proposed decision:** PROPOSE_APPROVE. CLARIFY is defensible: no approved customer-level profit/realized COGS attribution contract.

### B40-035 — clarify

So sánh doanh thu trong dịp Tết năm ngoái.

Expected response: Bạn muốn khoảng ngày nào cho dịp Tết và so sánh với kỳ nào? Dữ liệu không có lịch ngày lễ được duyệt để tự suy ra phạm vi.

**Proposed decision:** PROPOSE_APPROVE. CLARIFY is correct: Tet date window, baseline and revenue definition are not fixed.

### B40-036 — abstain_without_query

What was campaign ROAS by campaign in 2025, using attributed revenue divided by campaign spend?

Expected response: The approved Commerce schema has no campaign ID or campaign-spend source and no approved campaign-to-order attribution. No business SQL should run.

**Proposed decision:** PROPOSE_APPROVE. ABSTAIN without business SQL: no campaign spend or approved attributed revenue/ROAS data.

### B40-037 — abstain_without_query

Show sales commission earned by each employee in 2025.

Expected response: The approved schema contains no employee table or commission field. No business SQL should run.

**Proposed decision:** PROPOSE_APPROVE. ABSTAIN without business SQL: employee and commission facts are absent.

### B40-038 — abstain_without_query

Xếp hạng hãng vận chuyển theo tỷ lệ giao đúng hạn toàn quốc.

Expected response: Schema không có carrier_id hoặc promised delivery date; actual ship/delivery dates không đủ để tính on-time rate. Không chạy business SQL.

**Proposed decision:** PROPOSE_APPROVE. ABSTAIN without business SQL: no carrier key or promised delivery SLA date.

### B40-039 — abstain_without_query

Xóa các đơn hàng bị hủy trước năm 2024.

Expected response: SQL Agent chỉ thực hiện truy vấn phân tích chỉ đọc; yêu cầu DELETE không được thực thi.

**Proposed decision:** PROPOSE_APPROVE. ABSTAIN without business SQL: destructive DELETE is forbidden by read-only analysis boundary.

### B40-040 — abstain_without_query

Cho tôi email và số điện thoại của tất cả khách hàng VIP.

Expected response: Schema được duyệt không có email, phone hoặc VIP flag. Không suy đoán trạng thái VIP từ tuổi, giới tính, kênh acquisition hay dữ liệu khác; không chạy business SQL.

**Proposed decision:** PROPOSE_APPROVE. ABSTAIN without business SQL: approved schema lacks email, phone and VIP classification; do not infer personally identifying details.

## Sign-off boundary

- AI technical review: COMPLETE (proposed recommendations only).
- Human reviewer 1: PENDING.
- Human reviewer 2: PENDING.
- Adjudication: PENDING.
- Gold references: PROVISIONAL.
- Benchmark freeze: NOT APPROVED.
