-- Precompute the campaign-window rollup so dashboard and decision-support
-- requests do not aggregate all order items on every request.
CREATE MATERIALIZED VIEW commerce.dashboard_promotions_by_campaign AS
WITH tagged_items AS (
    SELECT order_id, product_id, quantity, unit_price, discount_amount, promo_id
    FROM commerce.order_items
    WHERE promo_id IS NOT NULL
    UNION ALL
    SELECT order_id, product_id, quantity, unit_price, discount_amount,
           promo_id_2 AS promo_id
    FROM commerce.order_items
    WHERE promo_id_2 IS NOT NULL AND promo_id_2 IS DISTINCT FROM promo_id
)
SELECT extract(year FROM p.start_date)::int AS year,
       p.promo_id,
       p.promo_name AS campaign,
       p.promo_channel AS channel,
       p.start_date::text AS campaign_start,
       p.end_date::text AS campaign_end,
       count(DISTINCT o.order_id)::int AS delivered_orders,
       coalesce(sum(t.quantity) FILTER (WHERE o.order_id IS NOT NULL), 0)::bigint AS units,
       coalesce(sum(t.quantity * t.unit_price - t.discount_amount)
           FILTER (WHERE o.order_id IS NOT NULL), 0)::double precision AS net_item_sales,
       coalesce(sum(t.quantity * products.cogs)
           FILTER (WHERE o.order_id IS NOT NULL), 0)::double precision AS catalog_cogs,
       coalesce(sum(t.quantity * t.unit_price - t.discount_amount - t.quantity * products.cogs)
           FILTER (WHERE o.order_id IS NOT NULL), 0)::double precision AS merchandise_gross_profit_proxy,
       (sum(t.quantity * t.unit_price - t.discount_amount - t.quantity * products.cogs)
           FILTER (WHERE o.order_id IS NOT NULL)
           / nullif(sum(t.quantity * t.unit_price - t.discount_amount)
               FILTER (WHERE o.order_id IS NOT NULL), 0))::double precision AS merchandise_gross_margin_proxy,
       coalesce(sum(t.discount_amount) FILTER (WHERE o.order_id IS NOT NULL), 0)::double precision AS discounts
FROM commerce.promotions p
LEFT JOIN tagged_items t ON t.promo_id = p.promo_id
LEFT JOIN commerce.products products ON products.product_id = t.product_id
LEFT JOIN commerce.orders o ON o.order_id = t.order_id
   AND o.order_status = 'delivered'
   AND o.order_date BETWEEN p.start_date AND p.end_date
GROUP BY p.promo_id, p.promo_name, p.promo_channel, p.start_date, p.end_date;

REVOKE ALL ON commerce.dashboard_promotions_by_campaign FROM PUBLIC, anon, authenticated;
