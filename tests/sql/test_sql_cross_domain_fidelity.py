"""Independent adversarial fixtures, separate from frozen benchmark references."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(os.environ.get('SQL_CROSS_DOMAIN_ROOT',ROOT))
sys.path[:0]=[str(WORK),str(WORK/'src')]
from core.agents.sql.text_to_sql import decode_query_plan,APPROVED_COLUMNS,validate_commerce_sql,validate_sql_security
from core.agents.sql.metric_validation import validate_metric_definitions,MetricDefinitionError
from sqlglot import exp,parse_one

QUESTIONS={
 'S23':'Which products have the highest ratio of returned units in 2022 to ordered units in 2022?',
 'S26':'Which products had stockout_flag=true in December 2022 and any customer orders that month?',
 'S27':'For each category, compare summed December 2022 inventory units_sold with December 2022 ordered quantities.'}
SQL={
 'S23':"""WITH ret AS (SELECT r.product_id,SUM(r.return_quantity) AS returned_units FROM commerce.returns r
 WHERE r.return_date>=DATE '2022-01-01' AND r.return_date<DATE '2023-01-01' GROUP BY r.product_id),
 ord AS (SELECT oi.product_id,SUM(oi.quantity) AS ordered_units FROM commerce.order_items oi
 JOIN commerce.orders o ON oi.order_id=o.order_id WHERE o.order_date>=DATE '2022-01-01'
 AND o.order_date<DATE '2023-01-01' GROUP BY oi.product_id)
 SELECT ret.product_id,ret.returned_units,ord.ordered_units,
 CAST(ret.returned_units AS NUMERIC)/NULLIF(ord.ordered_units,0) AS ratio
 FROM ret JOIN ord ON ret.product_id=ord.product_id ORDER BY 4 DESC NULLS LAST,ret.product_id LIMIT 200""",
 'S26':"""SELECT i.snapshot_date,i.product_id,p.product_name FROM commerce.inventory i
 JOIN commerce.products p ON i.product_id=p.product_id
 WHERE i.snapshot_date>=DATE '2022-12-01' AND i.snapshot_date<DATE '2023-01-01' AND i.stockout_flag=TRUE
 AND EXISTS(SELECT 1 FROM commerce.order_items oi JOIN commerce.orders o ON oi.order_id=o.order_id
 WHERE oi.product_id=p.product_id AND o.order_date>=DATE '2022-12-01' AND o.order_date<DATE '2023-01-01')
 ORDER BY i.snapshot_date,i.product_id LIMIT 200""",
 'S27':"""WITH inv AS(SELECT p.category,SUM(i.units_sold) AS inventory_units_sold
 FROM commerce.inventory i JOIN commerce.products p ON i.product_id=p.product_id
 WHERE i.snapshot_date>=DATE '2022-12-01' AND i.snapshot_date<DATE '2023-01-01' GROUP BY p.category),
 ord AS(SELECT q.category,SUM(oi.quantity) AS ordered_units FROM commerce.order_items oi
 JOIN commerce.orders o ON oi.order_id=o.order_id JOIN commerce.products q ON oi.product_id=q.product_id
 WHERE o.order_date>=DATE '2022-12-01' AND o.order_date<DATE '2023-01-01' GROUP BY q.category)
 SELECT COALESCE(inv.category,ord.category) AS category,inv.inventory_units_sold,ord.ordered_units
 FROM inv FULL JOIN ord ON inv.category=ord.category ORDER BY 1 LIMIT 200"""}
METRICS={'S23':set(),'S26':{'stockout_indicator'},'S27':{'inventory_units_sold'}}


def validate(key,sql):
    plan=decode_query_plan(json.dumps(dict(sql=sql)))
    return validate_metric_definitions(plan.sql,METRICS[key],plan.parameters,APPROVED_COLUMNS,question=QUESTIONS[key])


def fixture():
    db=sqlite3.connect(':memory:');db.execute("ATTACH DATABASE ':memory:' AS commerce")
    db.executescript('''CREATE TABLE commerce.products(product_id INT PRIMARY KEY,product_name TEXT,category TEXT,cogs NUMERIC DEFAULT 1,
    segment TEXT DEFAULT 'default');
    CREATE TABLE commerce.inventory(snapshot_date TEXT,product_id INT,units_sold INT,stockout_flag BOOLEAN,
    reorder_flag BOOLEAN DEFAULT FALSE,sell_through_rate NUMERIC,stockout_days INT DEFAULT 0,
    PRIMARY KEY(snapshot_date,product_id));
    CREATE TABLE commerce.orders(order_id INT PRIMARY KEY,order_date TEXT,order_status TEXT,customer_id INT,zip TEXT);
    CREATE TABLE commerce.order_items(order_item_id INT PRIMARY KEY,order_id INT,product_id INT,quantity INT CHECK(quantity>0),
    unit_price NUMERIC DEFAULT 1,discount_amount NUMERIC DEFAULT 0,promo_id INT,promo_id_2 INT);
    CREATE TABLE commerce.returns(return_id INT PRIMARY KEY,order_id INT,product_id INT,return_date TEXT,return_quantity INT,refund_amount NUMERIC DEFAULT 0);
    CREATE TABLE commerce.reviews(review_id INT PRIMARY KEY,product_id INT,rating INT,review_date TEXT);
    CREATE TABLE commerce.customers(customer_id INT PRIMARY KEY,acquisition_channel TEXT,zip TEXT);
    CREATE TABLE commerce.geography(zip TEXT PRIMARY KEY,region TEXT);
    CREATE TABLE commerce.payments(payment_id INT PRIMARY KEY,order_id INT,payment_value NUMERIC);
    CREATE TABLE commerce.promotions(promo_id INT PRIMARY KEY,promo_name TEXT,promo_type TEXT,discount_value NUMERIC,
    start_date TEXT,end_date TEXT,applicable_category TEXT,promo_channel TEXT,stackable_flag BOOLEAN,min_order_value NUMERIC);
    INSERT INTO commerce.products(product_id,product_name,category) VALUES
    (1,'same','A'),(2,'same','A'),(3,'third','B'),(4,'order-only','D'),(5,'old-order','C'),(6,'inventory-only','E');
    INSERT INTO commerce.inventory(snapshot_date,product_id,units_sold,stockout_flag) VALUES('2022-12-15',1,4,1),('2022-12-31',1,6,1),('2022-12-31',2,3,1),
    ('2022-12-31',3,2,0),('2022-12-31',5,7,1),('2022-12-31',6,0,1),('2022-11-30',1,99,1);
    INSERT INTO commerce.orders(order_id,order_date,order_status) VALUES(1,'2022-12-05','cancelled'),(2,'2022-12-10','completed'),
    (3,'2022-12-11','completed'),(4,'2022-11-01','completed'),(5,'2023-01-01','completed');
    INSERT INTO commerce.order_items(order_item_id,order_id,product_id,quantity) VALUES
    (1,1,1,1),(2,2,1,1),(3,3,1,6),(4,2,2,4),(5,3,3,2),(6,3,4,5),(7,4,5,10),(8,5,1,100);
    INSERT INTO commerce.returns(return_id,order_id,product_id,return_date,return_quantity) VALUES(1,1,1,'2022-12-05',1),(2,2,1,'2022-12-20',2),
    (3,2,2,'2022-12-20',2),(4,3,3,'2022-12-20',1),(5,4,5,'2022-12-20',1),(6,5,1,'2023-01-01',100);''')
    db.executemany('INSERT INTO commerce.reviews VALUES(?,?,?,?)', [
        (1, 1, 5, '2022-12-02'), (2, 1, 4, '2022-12-12'),
        (3, 2, 3, '2022-12-03'), (4, 3, 2, '2022-12-15'),
    ])
    return db


def execute_fixture(db,sql):
    tree=parse_one(sql,read='postgres')
    # SQLite integer NUMERIC division differs from PostgreSQL; use REAL only in this synthetic oracle.
    for cast in tree.find_all(exp.Cast):
        if cast.to.this in {exp.DataType.Type.DECIMAL,exp.DataType.Type.DOUBLE}:
            cast.set('to',exp.DataType.build('DOUBLE'))
    cursor=db.execute(tree.sql(dialect='sqlite'))
    return [dict(zip([c[0] for c in cursor.description],row)) for row in cursor.fetchall()]


class CrossDomainFixtureTruthTest(unittest.TestCase):
    def test_inventory_efficiency_uses_exact_snapshot_and_order_aggregate(self):
        sql = """WITH selected_snapshot AS (
          SELECT MAX(snapshot_date) AS snapshot_date FROM commerce.inventory
        ), inventory_latest AS (
          SELECT i.snapshot_date,i.product_id,i.units_sold,i.stockout_flag,i.reorder_flag,
                 i.sell_through_rate,i.stockout_days
          FROM commerce.inventory i JOIN selected_snapshot s ON s.snapshot_date=i.snapshot_date
        ), monthly_sales AS (
          SELECT oi.product_id,SUM(oi.quantity) AS ordered_units,COUNT(DISTINCT o.order_id) AS order_count
          FROM commerce.order_items oi JOIN commerce.orders o ON o.order_id=oi.order_id
          WHERE o.order_status='completed' AND o.order_date>='2022-12-01' AND o.order_date<'2023-01-01'
          GROUP BY 1
        )
        SELECT i.snapshot_date,p.category,p.product_id,i.units_sold,i.stockout_flag,i.reorder_flag,
               i.sell_through_rate,i.stockout_days,COALESCE(s.ordered_units,0) AS ordered_units,
               COALESCE(s.order_count,0) AS order_count
        FROM inventory_latest i JOIN commerce.products p ON p.product_id=i.product_id
        LEFT JOIN monthly_sales s ON s.product_id=i.product_id
        WHERE i.stockout_flag=TRUE OR i.reorder_flag=TRUE ORDER BY p.category,p.product_id LIMIT 200"""
        validate_sql_security(sql, allowed_sources=set(APPROVED_COLUMNS))
        with fixture() as db:
            db.execute("UPDATE commerce.inventory SET stockout_flag=FALSE WHERE snapshot_date='2022-12-31' AND product_id IN (5,6)")
            db.execute("UPDATE commerce.inventory SET reorder_flag=TRUE,sell_through_rate=0.7,stockout_days=3 WHERE snapshot_date='2022-12-31' AND product_id=1")
            db.execute("UPDATE commerce.inventory SET reorder_flag=TRUE,sell_through_rate=0.8,stockout_days=2 WHERE snapshot_date='2022-12-31' AND product_id=2")
            rows=execute_fixture(db,sql)
            self.assertEqual(rows,[
                {'snapshot_date':'2022-12-31','category':'A','product_id':1,'units_sold':6,'stockout_flag':1,
                 'reorder_flag':1,'sell_through_rate':0.7,'stockout_days':3,'ordered_units':7,'order_count':2},
                {'snapshot_date':'2022-12-31','category':'A','product_id':2,'units_sold':3,'stockout_flag':1,
                 'reorder_flag':1,'sell_through_rate':0.8,'stockout_days':2,'ordered_units':4,'order_count':1},
            ])
            self.assertTrue(all(row['snapshot_date']=='2022-12-31' for row in rows))

    def test_promotion_attribution_aggregates_each_promo_without_claiming_lift(self):
        sql = """WITH campaign_sales AS (
          SELECT promo.promo_id,COUNT(DISTINCT o.order_id) AS attributed_orders,
                 SUM(oi.quantity*oi.unit_price-oi.discount_amount) AS attributed_net_sales,
                 SUM(oi.quantity*p.cogs) AS cogs,
                 SUM(oi.quantity*oi.unit_price-oi.discount_amount)-SUM(oi.quantity*p.cogs) AS merchandise_gross_profit
          FROM commerce.promotions promo JOIN commerce.order_items oi
            ON promo.promo_id=oi.promo_id OR promo.promo_id=oi.promo_id_2
          JOIN commerce.products p ON p.product_id=oi.product_id
          JOIN commerce.orders o ON o.order_id=oi.order_id
          WHERE o.order_status='completed' AND o.order_date>=promo.start_date AND o.order_date<=promo.end_date
          GROUP BY 1
        )
        SELECT p.promo_id,p.promo_name,COALESCE(s.attributed_orders,0) AS attributed_orders,
               COALESCE(s.attributed_net_sales,0) AS attributed_net_sales,
               COALESCE(s.merchandise_gross_profit,0) AS merchandise_gross_profit
        FROM commerce.promotions p LEFT JOIN campaign_sales s ON s.promo_id=p.promo_id
        ORDER BY 4 DESC,1 LIMIT 200"""
        validate_sql_security(sql, allowed_sources=set(APPROVED_COLUMNS))
        with fixture() as db:
            db.executemany('INSERT INTO commerce.promotions VALUES(?,?,?,?,?,?,?,?,?,?)', [
                (1,'Winter A','coupon',10,'2022-12-01','2022-12-31','A','email',0,0),
                (2,'Winter B','markdown',15,'2022-12-01','2022-12-31','A','social',0,0),
            ])
            db.execute('UPDATE commerce.products SET cogs=3 WHERE product_id=1')
            db.execute('UPDATE commerce.order_items SET promo_id=1,promo_id_2=2 WHERE order_item_id=2')
            db.execute('UPDATE commerce.order_items SET promo_id=2 WHERE order_item_id=4')
            rows=execute_fixture(db,sql)
            self.assertEqual(rows,[
                {'promo_id':2,'promo_name':'Winter B','attributed_orders':1,'attributed_net_sales':5,'merchandise_gross_profit':-2},
                {'promo_id':1,'promo_name':'Winter A','attributed_orders':1,'attributed_net_sales':1,'merchandise_gross_profit':-2},
            ])
            # The same tagged line can be attributed to both declared promotion IDs; this is descriptive, not lift.
            self.assertEqual(rows[0]['attributed_orders'],rows[1]['attributed_orders'])

    def test_category_product_rank_separates_net_sales_cogs_and_margin(self):
        sql = """WITH item_facts AS (
          SELECT oi.order_id,oi.product_id,p.category,
                 SUM(oi.quantity*oi.unit_price-oi.discount_amount) AS net_sales,
                 SUM(oi.quantity*p.cogs) AS cogs
          FROM commerce.order_items oi
          JOIN commerce.orders o ON o.order_id=oi.order_id
          JOIN commerce.products p ON p.product_id=oi.product_id
          WHERE o.order_status='completed' AND o.order_date>='2022-01-01' AND o.order_date<'2023-01-01'
          GROUP BY 1,2,3
        ), product_facts AS (
          SELECT f.product_id,f.category,SUM(f.net_sales) AS net_sales,SUM(f.cogs) AS cogs,
                 SUM(f.net_sales)-SUM(f.cogs) AS gross_profit,
                 100.0*(SUM(f.net_sales)-SUM(f.cogs))/NULLIF(SUM(f.net_sales),0) AS gross_margin_pct
          FROM item_facts f GROUP BY 1,2
        ), ranked AS (
          SELECT p.product_id,p.category,p.net_sales,p.cogs,p.gross_profit,p.gross_margin_pct,
                 RANK() OVER(PARTITION BY p.category ORDER BY p.net_sales DESC,p.gross_margin_pct ASC) AS category_rank
          FROM product_facts p
        )
        SELECT category,product_id,net_sales,cogs,gross_profit,gross_margin_pct,category_rank
        FROM ranked WHERE category_rank<=2 ORDER BY category,category_rank LIMIT 200"""
        validate_sql_security(sql, allowed_sources=set(APPROVED_COLUMNS))
        with fixture() as db:
            db.execute('UPDATE commerce.products SET cogs=3 WHERE product_id=1')
            db.execute('UPDATE commerce.products SET cogs=0.5 WHERE product_id=2')
            db.execute('UPDATE commerce.order_items SET unit_price=CASE order_item_id '
                       'WHEN 2 THEN 12 WHEN 3 THEN 8 WHEN 4 THEN 3 ELSE 1 END')
            rows=execute_fixture(db,sql)
            self.assertEqual(rows[0]['category'],'A')
            self.assertEqual(rows[0]['product_id'],1)
            self.assertEqual(rows[0]['net_sales'],60)
            self.assertEqual(rows[0]['cogs'],21)
            self.assertEqual(rows[0]['gross_profit'],39)
            self.assertAlmostEqual(rows[0]['gross_margin_pct'],65)
            self.assertEqual(rows[0]['category_rank'],1)
            raw_line_margin=execute_fixture(db,"""SELECT p.product_id,
              100.0*(SUM(oi.quantity*oi.unit_price-oi.discount_amount)-SUM(p.cogs))/SUM(oi.quantity*oi.unit_price-oi.discount_amount) AS margin
              FROM commerce.order_items oi JOIN commerce.orders o ON o.order_id=oi.order_id
              JOIN commerce.products p ON p.product_id=oi.product_id
              WHERE o.order_status='completed' AND o.order_date>='2022-01-01' AND o.order_date<'2023-01-01'
              GROUP BY p.product_id ORDER BY 1 LIMIT 200""")
            self.assertNotEqual(rows[0]['gross_margin_pct'],raw_line_margin[0]['margin'])

    def test_regional_return_risk_ctes_preserve_order_grain_across_all_facts(self):
        sql = """WITH line AS (
          SELECT oi.order_id,SUM(oi.quantity*oi.unit_price-oi.discount_amount) AS line_net,
                 SUM(oi.quantity*p.cogs) AS sold_cogs
          FROM commerce.order_items oi JOIN commerce.products p ON p.product_id=oi.product_id
          GROUP BY 1
        ), returns_by_order AS (
          SELECT r.order_id,SUM(r.return_quantity) AS returned_quantity,
                 SUM(r.refund_amount) AS refund_amount,
                 SUM(r.return_quantity*p.cogs) AS returned_cogs,1 AS has_return
          FROM commerce.returns r JOIN commerce.products p ON p.product_id=r.product_id
          GROUP BY 1
        ), order_finance AS (
          SELECT o.order_id,l.line_net-COALESCE(r.refund_amount,0) AS net_revenue,
                 l.line_net-l.sold_cogs-COALESCE(r.refund_amount,0)+COALESCE(r.returned_cogs,0) AS gross_profit,
                 COALESCE(r.has_return,0) AS has_return
          FROM commerce.orders o JOIN line l ON l.order_id=o.order_id
          LEFT JOIN returns_by_order r ON r.order_id=o.order_id
        ), payments_by_order AS (
          SELECT p.order_id,SUM(p.payment_value) AS payment_total
          FROM commerce.payments p GROUP BY p.order_id
        ), order_facts AS (
          SELECT o.order_id,o.customer_id,COALESCE(g.region,'UNKNOWN') AS delivery_region,
                 COALESCE(c.acquisition_channel,'UNKNOWN') AS acquisition_channel,
                 f.net_revenue,f.gross_profit,f.has_return,COALESCE(pay.payment_total,0) AS payment_total
          FROM commerce.orders o JOIN order_finance f ON f.order_id=o.order_id
          LEFT JOIN commerce.customers c ON c.customer_id=o.customer_id
          LEFT JOIN commerce.geography g ON g.zip=o.zip
          LEFT JOIN payments_by_order pay ON pay.order_id=o.order_id
          WHERE o.order_date>='2022-07-05' AND o.order_date<='2022-12-31'
        ), cohorts AS (
          SELECT f.delivery_region,f.acquisition_channel,COUNT(*) AS order_count,
                 COUNT(DISTINCT f.customer_id) AS buyer_count,SUM(f.has_return) AS returned_orders,
                 SUM(f.net_revenue) AS net_revenue,SUM(f.gross_profit) AS gross_profit,
                 SUM(f.payment_total) AS payments
          FROM order_facts f GROUP BY 1,2 HAVING COUNT(*)>=5
        ), ranked AS (
          SELECT c.delivery_region,c.acquisition_channel,c.order_count,c.buyer_count,c.returned_orders,
                 c.net_revenue,c.gross_profit,c.payments,
                 100.0*c.returned_orders/NULLIF(c.order_count,0) AS return_rate_pct,
                 RANK() OVER(ORDER BY 100.0*c.returned_orders/NULLIF(c.order_count,0) DESC,
                                      c.delivery_region,c.acquisition_channel) AS risk_rank
          FROM cohorts c
        )
        SELECT r.delivery_region,r.acquisition_channel,r.order_count,r.buyer_count,r.returned_orders,
               r.return_rate_pct,r.net_revenue,r.gross_profit,r.payments,r.risk_rank
        FROM ranked r ORDER BY 10 LIMIT 10"""
        validate_sql_security(sql,allowed_sources=set(APPROVED_COLUMNS))
        with fixture() as db:
            db.executemany('INSERT INTO commerce.geography VALUES(?,?)', [
                ('10001','East'),('90001','West'),('70001','South')])
            db.executemany('INSERT INTO commerce.customers VALUES(?,?,?)', [
                (1,'organic_search','10001'),(2,'organic_search','10001'),(3,'organic_search','10001'),
                (4,'email_campaign','90001'),(5,'email_campaign','90001'),(6,'email_campaign','90001'),
                (7,'influencer','70001'),(8,'influencer','70001'),
            ])
            db.execute('UPDATE commerce.products SET cogs=3 WHERE product_id=1')
            db.execute('UPDATE commerce.products SET cogs=2 WHERE product_id=2')
            orders=[]; items=[]; returns=[]; payments=[]
            for offset in range(10):
                order_id=100+offset
                east=offset<5
                customer_id=(offset%3+1) if east else (offset%3+4)
                orders.append((order_id,f'2022-12-{offset+1:02}', 'delivered',customer_id,'10001' if east else '90001'))
                items.extend([(order_id*10+1,order_id,1,2,10,1),(order_id*10+2,order_id,2,1,8,0)])
                payments.append((order_id*10+1,order_id,30))
                if offset in {0,1,5}:
                    if offset == 0:
                        returns.extend([(order_id*10+1,order_id,1,'2022-12-20',1,4),
                                        (order_id*10+2,order_id,1,'2022-12-21',1,5)])
                    else:
                        returns.append((order_id*10+1,order_id,2,'2022-12-20',1,6))
            for offset in range(4):
                order_id=110+offset
                orders.append((order_id,f'2022-12-{offset+11:02}','delivered',7+offset%2,'70001'))
                items.extend([(order_id*10+1,order_id,1,2,10,1),(order_id*10+2,order_id,2,1,8,0)])
                payments.append((order_id*10+1,order_id,30))
                returns.append((order_id*10+1,order_id,2,'2022-12-25',1,8))
            db.executemany('INSERT INTO commerce.orders VALUES(?,?,?,?,?)',orders)
            db.executemany('INSERT INTO commerce.order_items(order_item_id,order_id,product_id,quantity,unit_price,discount_amount) VALUES(?,?,?,?,?,?)',items)
            db.executemany('INSERT INTO commerce.returns VALUES(?,?,?,?,?,?)',returns)
            db.executemany('INSERT INTO commerce.payments VALUES(?,?,?)',payments)
            rows=execute_fixture(db,sql)
            self.assertEqual(rows,[
                {'delivery_region':'East','acquisition_channel':'organic_search','order_count':5,
                 'buyer_count':3,'returned_orders':2,'return_rate_pct':40.0,'net_revenue':120,
                 'gross_profit':88,'payments':150,'risk_rank':1},
                {'delivery_region':'West','acquisition_channel':'email_campaign','order_count':5,
                 'buyer_count':3,'returned_orders':1,'return_rate_pct':20.0,'net_revenue':129,
                 'gross_profit':91,'payments':150,'risk_rank':2},
            ])
            self.assertNotIn('South',[row['delivery_region'] for row in rows])
            raw_return_join=sql.replace(
                'SELECT r.order_id,SUM(r.return_quantity) AS returned_quantity,\n'
                '                 SUM(r.refund_amount) AS refund_amount,\n'
                '                 SUM(r.return_quantity*p.cogs) AS returned_cogs,1 AS has_return\n'
                '          FROM commerce.returns r JOIN commerce.products p ON p.product_id=r.product_id\n'
                '          GROUP BY 1',
                'SELECT r.order_id,r.return_quantity AS returned_quantity,r.refund_amount,\n'
                '                 r.return_quantity*p.cogs AS returned_cogs,1 AS has_return\n'
                '          FROM commerce.returns r JOIN commerce.products p ON p.product_id=r.product_id',
            )
            self.assertNotEqual(rows,execute_fixture(db,raw_return_join))

    def test_rating_segment_comparison_aggregates_facts_before_joining(self):
        sql = """WITH product_revenue AS (
          SELECT oi.product_id, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS product_revenue
          FROM commerce.order_items oi JOIN commerce.orders o ON o.order_id=oi.order_id
          WHERE o.order_status='completed' AND o.order_date>=DATE '2022-01-01' AND o.order_date<DATE '2023-01-01'
          GROUP BY 1
        ), product_ratings AS (
          SELECT r.product_id, AVG(r.rating) AS average_rating, COUNT(r.review_id) AS review_count
          FROM commerce.reviews r WHERE r.review_date>=DATE '2022-01-01' AND r.review_date<DATE '2023-01-01'
          GROUP BY 1
        ), product_groups AS (
          SELECT pr.product_id, pr.product_revenue, COALESCE(rt.average_rating,0) AS average_rating,
                 COALESCE(rt.review_count,0) AS review_count
          FROM product_revenue pr LEFT JOIN product_ratings rt ON rt.product_id=pr.product_id
        )
        SELECT CASE WHEN pg.average_rating>=4 THEN '4+' ELSE 'under 4' END AS rating_group,
               COUNT(pg.product_id) AS product_count, SUM(pg.product_revenue) AS revenue,
               SUM(pg.review_count) AS review_count
        FROM product_groups pg GROUP BY 1 ORDER BY 1 LIMIT 200"""
        validate_commerce_sql(sql, schema_columns=APPROVED_COLUMNS)
        with fixture() as db:
            db.execute('UPDATE commerce.order_items SET unit_price=CASE order_item_id '
                       'WHEN 2 THEN 40 WHEN 3 THEN 10 WHEN 4 THEN 2.5 WHEN 5 THEN 2.5 '
                       'ELSE 1 END')
            rows = execute_fixture(db, sql)
            self.assertEqual(rows, [
                {'rating_group': '4+', 'product_count': 1, 'revenue': 100, 'review_count': 2},
                {'rating_group': 'under 4', 'product_count': 4, 'revenue': 30, 'review_count': 2},
            ])
            unsafe_rows = execute_fixture(db, """SELECT CASE WHEN r.rating>=4 THEN '4+' ELSE 'under 4' END AS rating_group,
                COUNT(DISTINCT oi.product_id) AS product_count,
                SUM(oi.quantity*oi.unit_price-oi.discount_amount) AS revenue,COUNT(r.review_id) AS review_count
                FROM commerce.order_items oi JOIN commerce.orders o ON o.order_id=oi.order_id
                JOIN commerce.reviews r ON r.product_id=oi.product_id
                WHERE o.order_status='completed' AND o.order_date>='2022-01-01' AND o.order_date<'2023-01-01'
                GROUP BY 1 ORDER BY 1 LIMIT 200""")
            self.assertNotEqual(rows, unsafe_rows)

    def test_returns_quality_and_review_ctes_do_not_fan_out_product_facts(self):
        sql = """WITH ordered AS (
          SELECT oi.product_id,SUM(oi.quantity) AS ordered_units,COUNT(DISTINCT oi.order_id) AS order_count
          FROM commerce.order_items oi JOIN commerce.orders o ON o.order_id=oi.order_id
          WHERE o.order_status='completed' AND o.order_date>='2022-01-01' AND o.order_date<'2023-01-01'
          GROUP BY 1
        ), returned AS (
          SELECT r.product_id,SUM(r.return_quantity) AS returned_units,
                 COUNT(DISTINCT r.order_id) AS returned_orders,SUM(r.refund_amount) AS refund_amount
          FROM commerce.returns r JOIN commerce.orders o ON o.order_id=r.order_id
          WHERE o.order_status='completed' AND r.return_date>='2022-01-01' AND r.return_date<'2023-01-01'
          GROUP BY 1
        ), ratings AS (
          SELECT r.product_id,AVG(r.rating) AS avg_rating,COUNT(r.review_id) AS review_count
          FROM commerce.reviews r WHERE r.review_date>='2022-01-01' AND r.review_date<'2023-01-01'
          GROUP BY 1
        )
        SELECT p.product_id,o.order_count,o.ordered_units,COALESCE(r.returned_orders,0) AS returned_orders,
               COALESCE(r.returned_units,0) AS returned_units,
               100.0*COALESCE(r.returned_units,0)/NULLIF(o.ordered_units,0) AS return_rate_pct,
               COALESCE(r.refund_amount,0) AS refund_amount,a.avg_rating,a.review_count
        FROM ordered o JOIN commerce.products p ON p.product_id=o.product_id
        LEFT JOIN returned r ON r.product_id=o.product_id LEFT JOIN ratings a ON a.product_id=o.product_id
        ORDER BY 6 DESC,1 LIMIT 200"""
        validate_sql_security(sql, allowed_sources=set(APPROVED_COLUMNS))
        with fixture() as db:
            db.execute("INSERT INTO commerce.returns(return_id,order_id,product_id,return_date,return_quantity,refund_amount) VALUES(7,2,2,'2022-12-22',1,9)")
            db.execute("INSERT INTO commerce.reviews VALUES(5,2,5,'2022-12-23')")
            rows=execute_fixture(db,sql)
            self.assertEqual(rows[0],{'product_id':2,'order_count':1,'ordered_units':4,'returned_orders':1,
                                      'returned_units':3,'return_rate_pct':75.0,'refund_amount':9,
                                      'avg_rating':4.0,'review_count':2})
            self.assertEqual(rows[1]['product_id'],3)
            self.assertEqual(rows[1]['return_rate_pct'],50.0)
            raw=execute_fixture(db,"""SELECT p.product_id,SUM(r.refund_amount) AS refund_amount
              FROM commerce.products p JOIN commerce.returns r ON r.product_id=p.product_id
              JOIN commerce.reviews v ON v.product_id=p.product_id
              JOIN commerce.orders o ON o.order_id=r.order_id
              WHERE o.order_status='completed' AND r.return_date>='2022-01-01' AND r.return_date<'2023-01-01'
              GROUP BY p.product_id ORDER BY p.product_id LIMIT 200""")
            self.assertNotEqual(rows[0]['refund_amount'],next(row['refund_amount'] for row in raw if row['product_id']==2))

    def test_extra_november_return_exposes_annual_population_narrowing(self):
        with fixture() as db:
            db.execute("INSERT INTO commerce.returns(return_id,order_id,product_id,return_date,return_quantity) VALUES(7,2,1,'2022-11-15',4)")
            annual=execute_fixture(db,SQL['S23'])
            narrowed=execute_fixture(db,SQL['S23'].replace("r.return_date>=DATE '2022-01-01'","r.return_date>=DATE '2022-12-01'"))
            self.assertNotEqual(annual,narrowed)
    def test_independent_aggregates_and_missing_categories(self):
        with fixture() as db:
            rows=execute_fixture(db,SQL['S27'])
            self.assertEqual(rows,[dict(category='A',inventory_units_sold=13,ordered_units=12),
                dict(category='B',inventory_units_sold=2,ordered_units=2),dict(category='C',inventory_units_sold=7,ordered_units=None),
                dict(category='D',inventory_units_sold=None,ordered_units=5),dict(category='E',inventory_units_sold=0,ordered_units=None)])
            bad=execute_fixture(db,SQL['S27'].replace('COALESCE(inv.category,ord.category)','COALESCE(inv.category,inv.category)'))
            self.assertNotEqual(rows,bad)
    def test_presence_correlation_and_multiple_observations(self):
        with fixture() as db:
            rows=execute_fixture(db,SQL['S26'])
            self.assertEqual([(r['snapshot_date'],r['product_id']) for r in rows],[('2022-12-15',1),('2022-12-31',1),('2022-12-31',2)])
            self.assertGreater(len(execute_fixture(db,SQL['S26'].replace('oi.product_id=p.product_id AND ',''))),len(rows))
    def test_ratio_operands_duplicate_names_and_multifact_multiplication(self):
        with fixture() as db:
            rows=execute_fixture(db,SQL['S23'])
            self.assertEqual([r['product_id'] for r in rows[:3]],[2,3,1])
            self.assertEqual(rows[2]['ratio'],.375)
            # The annual denominator includes the November order for product 5: do not turn this into December-only orders.
            self.assertEqual(rows[3]['ratio'],.1)
            raw=db.execute('SELECT 1.0*SUM(r.return_quantity)/SUM(oi.quantity) FROM commerce.returns r JOIN commerce.order_items oi '
                "ON r.product_id=oi.product_id WHERE r.product_id=1 AND r.return_date<'2023-01-01' AND oi.order_id<5").fetchone()[0]
            self.assertNotEqual(raw,.375)


@unittest.skipUnless('SQL_CROSS_DOMAIN_ROOT' in os.environ,'Isolated cross-domain validation experiment')
class CrossDomainContractGapTest(unittest.TestCase):
    def test_annual_period_cannot_hide_narrowing_date_expressions(self):
        for sql in [SQL['S23'].replace("r.return_date>=DATE '2022-01-01'", "EXTRACT(YEAR FROM r.return_date)=2022 AND r.return_date>=DATE '2022-12-01'"),
                    SQL['S23'].replace("r.return_date>=DATE '2022-01-01'", "EXTRACT(MONTH FROM r.return_date)=12 AND r.return_date>=DATE '2022-01-01'")]:
            with self.subTest(sql=sql),self.assertRaises(MetricDefinitionError):validate('S23',sql)
        validate('S23',SQL['S23'].replace("r.return_date>=DATE '2022-01-01' AND r.return_date<DATE '2023-01-01'",
                                        'EXTRACT(YEAR FROM r.return_date)=2022'))
    def test_order_alias_normalization_respects_quoted_names_and_ambiguity(self):
        plan=decode_query_plan(json.dumps({'sql':'SELECT -p.price AS "Price",p.product_id FROM commerce.products p ORDER BY price LIMIT 200'}))
        self.assertEqual(parse_one(plan.sql,read='postgres').args['order'].expressions[0].this.sql(),'p.price')
        for sql in ['SELECT p.price AS x,p.product_id AS x FROM commerce.products p ORDER BY x LIMIT 200',
                    'SELECT p.price AS x FROM commerce.products p WHERE x>0 ORDER BY x LIMIT 200']:
            with self.subTest(sql=sql),self.assertRaises(ValueError):decode_query_plan(json.dumps({'sql':sql}))
    def test_period_rollup_does_not_inherit_canonical_snapshot_approval(self):
        from core.models.agents import AgentResult
        from core.agents.report.planning import ReportTask
        from core.agents.report.facts import facts_from_analytics
        definitions=validate('S27',SQL['S27'])
        result=AgentResult(answer='Rows',agent='sql_analytics',data={'sql':SQL['S27'],'parameters':[],
            'rows':[{'category':'A','inventory_units_sold':13,'ordered_units':12}]},metadata={'metrics':definitions})
        fact=next(f for f in facts_from_analytics(ReportTask(id='comparison',question=QUESTIONS['S27']),result,'S1')
                  if f.metric=='inventory_units_sold')
        self.assertEqual(fact.approval_status,'not_established')
        self.assertNotIn('within one snapshot',fact.formula)
    def test_valid_complete_queries(self):
        for key,sql in SQL.items():
            with self.subTest(case=key):validate(key,sql)
    def test_valid_aliases_key_order_and_redundant_distinct(self):
        for key,sql in [('S23',SQL['S23'].replace('ORDER BY 4','ORDER BY ratio')),
                        ('S26',SQL['S26'].replace('SELECT i.snapshot_date','SELECT DISTINCT i.snapshot_date').replace('oi.product_id=p.product_id','p.product_id=oi.product_id')),
                        ('S27',SQL['S27'].replace('COALESCE(inv.category,ord.category)','COALESCE(ord.category,inv.category)').replace('ORDER BY 1','ORDER BY category'))]:
            with self.subTest(case=key):validate(key,sql)
    def test_ratio_cannot_hide_product_identity(self):
        with self.assertRaises(MetricDefinitionError):validate('S23',SQL['S23'].replace('SELECT ret.product_id,ret.returned_units','SELECT ret.returned_units').replace('ORDER BY 4','ORDER BY 3'))
    def test_presence_requires_correlation_and_complete_order_population(self):
        for sql in [SQL['S26'].replace('oi.product_id=p.product_id AND ',''),
                    SQL['S26'].replace('oi.product_id=p.product_id','oi.product_id=1'),
                    SQL['S26'].replace("AND o.order_date<DATE '2023-01-01'", "AND o.order_date<DATE '2023-01-01' AND o.order_status='completed'")]:
            with self.subTest(sql=sql),self.assertRaises((MetricDefinitionError,ValueError)):validate('S26',sql)
    def test_presence_cannot_hide_an_outer_population_filter(self):
        with self.assertRaises(MetricDefinitionError):
            validate('S26',SQL['S26'].replace('AND i.stockout_flag=TRUE',"AND i.stockout_flag=TRUE AND p.category='A'"))
    def test_category_comparison_cannot_repeat_one_side_or_drop_categories(self):
        for sql in [SQL['S27'].replace('COALESCE(inv.category,ord.category)','COALESCE(inv.category,inv.category)'),
                    SQL['S27'].replace('LIMIT 200','LIMIT 1'),SQL['S27'].replace('ORDER BY 1','')]:
            with self.subTest(sql=sql),self.assertRaises(MetricDefinitionError):validate('S27',sql)
    def test_presence_has_stable_complete_observation_key_and_safety_ceiling(self):
        for sql in [SQL['S26'].replace('i.snapshot_date,i.product_id LIMIT','i.product_id LIMIT'),
                    SQL['S26'].replace('LIMIT 200','LIMIT 1')]:
            with self.subTest(sql=sql),self.assertRaises(MetricDefinitionError):validate('S26',sql)
