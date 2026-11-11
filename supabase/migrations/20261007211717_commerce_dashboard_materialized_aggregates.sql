-- Keep the Commerce source tables canonical. These read-only dashboard snapshots
-- avoid sorting hundreds of thousands of transaction rows on every UI request.
CREATE MATERIALIZED VIEW commerce.dashboard_promotions_by_year AS
SELECT extract(year FROM o.order_date)::int AS year,
       (coalesce(oi.promo_id, oi.promo_id_2) IS NOT NULL) AS used_promotion,
       count(DISTINCT o.order_id)::int AS delivered_orders,
       sum(oi.quantity)::bigint AS units,
       sum(oi.quantity * oi.unit_price - oi.discount_amount)::double precision AS net_sales,
       sum(oi.quantity * p.cogs)::double precision AS catalog_cogs,
       sum(oi.quantity * oi.unit_price - oi.discount_amount - oi.quantity * p.cogs)::double precision AS merchandise_gross_profit_proxy,
       (sum(oi.quantity * oi.unit_price - oi.discount_amount - oi.quantity * p.cogs)
           / nullif(sum(oi.quantity * oi.unit_price - oi.discount_amount), 0))::double precision AS merchandise_gross_margin_proxy,
       sum(oi.discount_amount)::double precision AS discounts
FROM commerce.orders o JOIN commerce.order_items oi USING (order_id)
JOIN commerce.products p USING (product_id)
WHERE o.order_status = 'delivered'
GROUP BY 1, 2;
REVOKE ALL ON commerce.dashboard_promotions_by_year FROM PUBLIC, anon, authenticated;

CREATE MATERIALIZED VIEW commerce.dashboard_logistics_by_year_region AS
SELECT extract(year FROM s.delivery_date)::int AS year,
       coalesce(g.region, 'Unknown') AS region,
       count(*)::int AS deliveries,
       round(avg(s.delivery_date - s.ship_date)::numeric, 2)::double precision AS avg_transit_days,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY s.delivery_date - s.ship_date)::double precision AS median_transit_days,
       round(avg(s.shipping_fee)::numeric, 2)::double precision AS avg_shipping_fee
FROM commerce.shipments s JOIN commerce.orders o USING (order_id)
LEFT JOIN commerce.geography g ON g.zip = o.zip
WHERE s.ship_date IS NOT NULL AND s.delivery_date >= s.ship_date
GROUP BY 1, 2;
REVOKE ALL ON commerce.dashboard_logistics_by_year_region FROM PUBLIC, anon, authenticated;
