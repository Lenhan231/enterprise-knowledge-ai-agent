"""Independent adversarial fixtures, separate from frozen benchmark references."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(os.environ.get('SQL_CROSS_DOMAIN_ROOT',ROOT))
sys.path[:0]=[str(WORK),str(WORK/'src')]
from core.analytics.text_to_sql import decode_query_plan,APPROVED_COLUMNS
from core.analytics.metric_validation import validate_metric_definitions,MetricDefinitionError
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
    db.executescript('''CREATE TABLE commerce.products(product_id INT PRIMARY KEY,product_name TEXT,category TEXT);
    CREATE TABLE commerce.inventory(snapshot_date TEXT,product_id INT,units_sold INT,stockout_flag BOOLEAN,
    PRIMARY KEY(snapshot_date,product_id));
    CREATE TABLE commerce.orders(order_id INT PRIMARY KEY,order_date TEXT,order_status TEXT);
    CREATE TABLE commerce.order_items(order_item_id INT PRIMARY KEY,order_id INT,product_id INT,quantity INT CHECK(quantity>0));
    CREATE TABLE commerce.returns(return_id INT PRIMARY KEY,order_id INT,product_id INT,return_date TEXT,return_quantity INT);
    INSERT INTO commerce.products VALUES(1,'same','A'),(2,'same','A'),(3,'third','B'),(4,'order-only','D'),(5,'old-order','C'),(6,'inventory-only','E');
    INSERT INTO commerce.inventory VALUES('2022-12-15',1,4,1),('2022-12-31',1,6,1),('2022-12-31',2,3,1),
    ('2022-12-31',3,2,0),('2022-12-31',5,7,1),('2022-12-31',6,0,1),('2022-11-30',1,99,1);
    INSERT INTO commerce.orders VALUES(1,'2022-12-05','cancelled'),(2,'2022-12-10','completed'),
    (3,'2022-12-11','completed'),(4,'2022-11-01','completed'),(5,'2023-01-01','completed');
    INSERT INTO commerce.order_items VALUES(1,1,1,1),(2,2,1,1),(3,3,1,6),(4,2,2,4),(5,3,3,2),(6,3,4,5),(7,4,5,10),(8,5,1,100);
    INSERT INTO commerce.returns VALUES(1,1,1,'2022-12-05',1),(2,2,1,'2022-12-20',2),
    (3,2,2,'2022-12-20',2),(4,3,3,'2022-12-20',1),(5,4,5,'2022-12-20',1),(6,5,1,'2023-01-01',100);''')
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
    def test_extra_november_return_exposes_annual_population_narrowing(self):
        with fixture() as db:
            db.execute("INSERT INTO commerce.returns VALUES(7,2,1,'2022-11-15',4)")
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
        from core.reports.planning import ReportTask
        from core.reports.facts import facts_from_analytics
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
