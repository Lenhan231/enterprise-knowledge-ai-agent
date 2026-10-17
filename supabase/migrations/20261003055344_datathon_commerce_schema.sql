-- Competition source tables are kept in a private domain schema. Do not expose
-- this schema through the Supabase Data API or reshape competition metrics.
CREATE SCHEMA IF NOT EXISTS commerce;

CREATE TABLE commerce.products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    segment TEXT,
    size TEXT,
    color TEXT,
    price NUMERIC NOT NULL CHECK (price >= 0),
    cogs NUMERIC NOT NULL CHECK (cogs >= 0)
);

CREATE TABLE commerce.geography (
    zip TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    region TEXT,
    district TEXT
);

CREATE TABLE commerce.customers (
    customer_id INTEGER PRIMARY KEY,
    zip TEXT,
    city TEXT,
    signup_date DATE NOT NULL,
    gender TEXT,
    age_group TEXT,
    acquisition_channel TEXT,
    FOREIGN KEY (zip) REFERENCES commerce.geography(zip)
);

CREATE TABLE commerce.promotions (
    promo_id TEXT PRIMARY KEY,
    promo_name TEXT NOT NULL,
    promo_type TEXT NOT NULL CHECK (promo_type IN ('percentage', 'fixed')),
    discount_value NUMERIC NOT NULL CHECK (discount_value >= 0),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    applicable_category TEXT,
    promo_channel TEXT,
    stackable_flag BOOLEAN NOT NULL,
    min_order_value NUMERIC,
    CHECK (end_date >= start_date)
);

CREATE TABLE commerce.orders (
    order_id INTEGER PRIMARY KEY,
    order_date DATE NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES commerce.customers(customer_id),
    zip TEXT REFERENCES commerce.geography(zip),
    order_status TEXT NOT NULL,
    payment_method TEXT,
    device_type TEXT,
    order_source TEXT
);

CREATE TABLE commerce.order_items (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES commerce.orders(order_id),
    product_id INTEGER NOT NULL REFERENCES commerce.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC NOT NULL CHECK (unit_price >= 0),
    discount_amount NUMERIC NOT NULL CHECK (discount_amount >= 0),
    promo_id TEXT REFERENCES commerce.promotions(promo_id),
    promo_id_2 TEXT REFERENCES commerce.promotions(promo_id)
);

CREATE TABLE commerce.payments (
    order_id INTEGER PRIMARY KEY REFERENCES commerce.orders(order_id),
    payment_method TEXT NOT NULL,
    payment_value NUMERIC NOT NULL CHECK (payment_value >= 0),
    installments INTEGER CHECK (installments >= 0)
);

CREATE TABLE commerce.shipments (
    order_id INTEGER PRIMARY KEY REFERENCES commerce.orders(order_id),
    ship_date DATE,
    delivery_date DATE,
    shipping_fee NUMERIC CHECK (shipping_fee >= 0),
    CHECK (delivery_date IS NULL OR ship_date IS NULL OR delivery_date >= ship_date)
);

CREATE TABLE commerce.returns (
    return_id TEXT PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES commerce.orders(order_id),
    product_id INTEGER NOT NULL REFERENCES commerce.products(product_id),
    return_date DATE NOT NULL,
    return_reason TEXT,
    return_quantity INTEGER NOT NULL CHECK (return_quantity > 0),
    refund_amount NUMERIC NOT NULL CHECK (refund_amount >= 0)
);

CREATE TABLE commerce.reviews (
    review_id TEXT PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES commerce.orders(order_id),
    product_id INTEGER NOT NULL REFERENCES commerce.products(product_id),
    customer_id INTEGER NOT NULL REFERENCES commerce.customers(customer_id),
    review_date DATE NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_title TEXT
);

CREATE TABLE commerce.inventory (
    snapshot_date DATE NOT NULL,
    product_id INTEGER NOT NULL REFERENCES commerce.products(product_id),
    stock_on_hand INTEGER NOT NULL CHECK (stock_on_hand >= 0),
    units_received INTEGER NOT NULL CHECK (units_received >= 0),
    units_sold INTEGER NOT NULL CHECK (units_sold >= 0),
    stockout_days INTEGER NOT NULL CHECK (stockout_days >= 0),
    days_of_supply NUMERIC,
    fill_rate NUMERIC,
    stockout_flag BOOLEAN NOT NULL,
    overstock_flag BOOLEAN NOT NULL,
    reorder_flag BOOLEAN NOT NULL,
    sell_through_rate NUMERIC,
    product_name TEXT,
    category TEXT,
    segment TEXT,
    year INTEGER,
    month INTEGER,
    PRIMARY KEY (snapshot_date, product_id)
);

CREATE TABLE commerce.web_traffic (
    date DATE NOT NULL,
    sessions INTEGER NOT NULL CHECK (sessions >= 0),
    unique_visitors INTEGER NOT NULL CHECK (unique_visitors >= 0),
    page_views INTEGER NOT NULL CHECK (page_views >= 0),
    bounce_rate NUMERIC,
    avg_session_duration_sec NUMERIC,
    traffic_source TEXT NOT NULL,
    PRIMARY KEY (date, traffic_source)
);

CREATE TABLE commerce.sales (
    date DATE PRIMARY KEY,
    revenue NUMERIC NOT NULL,
    cogs NUMERIC NOT NULL
);

-- Private schema: no API grants. Defense-in-depth for any future role grants.
DO $$
DECLARE t RECORD;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'commerce' LOOP
        EXECUTE format('ALTER TABLE commerce.%I ENABLE ROW LEVEL SECURITY', t.tablename);
    END LOOP;
END $$;
