-- Run as a database administrator. Create the LOGIN role and its password
-- separately in the deployment secret manager, then grant it membership in
-- commerce_analytics_reader. The application must receive that login through
-- ANALYTICS_DATABASE_URL; never use the postgres/service role connection.

begin;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'commerce_analytics_reader') then
        create role commerce_analytics_reader nologin
            nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls;
    end if;
end
$$;

revoke all on all tables in schema commerce from commerce_analytics_reader;
revoke create on schema commerce from commerce_analytics_reader;
grant usage on schema commerce to commerce_analytics_reader;

grant select (date, revenue, cogs)
    on commerce.sales to commerce_analytics_reader;
grant select (order_id, order_date, zip, order_status, payment_method, device_type, order_source)
    on commerce.orders to commerce_analytics_reader;
grant select (order_item_id, order_id, product_id, quantity, unit_price, discount_amount, promo_id, promo_id_2)
    on commerce.order_items to commerce_analytics_reader;
grant select (zip, city, region, district)
    on commerce.geography to commerce_analytics_reader;
grant select (snapshot_date, product_id, stock_on_hand, units_received, units_sold,
              stockout_days, days_of_supply, fill_rate, stockout_flag,
              overstock_flag, reorder_flag, sell_through_rate, product_name,
              category, segment, year, month)
    on commerce.inventory to commerce_analytics_reader;
grant select (product_id, product_name, category, segment, size, color, price, cogs)
    on commerce.products to commerce_analytics_reader;
grant select (promo_id, promo_name, promo_type, discount_value, start_date, end_date,
              applicable_category, promo_channel, stackable_flag, min_order_value)
    on commerce.promotions to commerce_analytics_reader;
grant select (return_id, order_id, product_id, return_date, return_reason,
              return_quantity, refund_amount)
    on commerce.returns to commerce_analytics_reader;
grant select (review_id, order_id, product_id, review_date, rating, review_title)
    on commerce.reviews to commerce_analytics_reader;
grant select (order_id, ship_date, delivery_date, shipping_fee)
    on commerce.shipments to commerce_analytics_reader;
grant select (date, sessions, unique_visitors, page_views, bounce_rate,
              avg_session_duration_sec, traffic_source)
    on commerce.web_traffic to commerce_analytics_reader;

-- The source tables have RLS enabled. Keep RLS on and allow only this
-- dedicated reader role to see the approved competition rows.
do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'sales', 'orders', 'order_items', 'geography', 'inventory',
        'products', 'promotions', 'returns', 'reviews', 'shipments',
        'web_traffic'
    ] loop
        if not exists (
            select 1
            from pg_policies
            where schemaname = 'commerce'
              and tablename = table_name
              and policyname = 'commerce_reader_select'
        ) then
            execute format(
                'create policy "commerce_reader_select" on commerce.%I '
                'for select to commerce_analytics_reader using (true)',
                table_name
            );
        end if;
    end loop;
end
$$;

alter role commerce_analytics_reader set default_transaction_read_only = on;
alter role commerce_analytics_reader set statement_timeout = '5s';

commit;
