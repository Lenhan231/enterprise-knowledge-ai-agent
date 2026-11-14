import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from core.analytics.metric_mapping import compile_inventory_query, decode_metric_mapping, validate_mapped_sql
from core.analytics.metric_validation import MetricDefinitionError
from core.analytics.metric_validation import validate_metric_definitions
from core.analytics.text_to_sql import APPROVED_COLUMNS, SQLValidationError, decode_query_plan


class SemanticAuthorityTest(unittest.TestCase):
    def mapping(self, **changes):
        payload = dict(metrics=['days_of_supply'], dimensions=['product_id'], representation='product',
                       time={'mode':'snapshot', 'start':'2022-12-31'},
                       ranking={'metric':'days_of_supply', 'direction':'asc', 'limit':10})
        payload.update(changes)
        return decode_metric_mapping(json.dumps(payload),
            'Which products have the lowest non-null days_of_supply on 2022-12-31?')

    def test_non_null_population_and_safety_ceiling_are_in_the_plan(self):
        mapping = self.mapping()
        self.assertIsNone(mapping.ranking.limit)
        self.assertEqual([(f.field,f.operator) for f in mapping.filters], [('days_of_supply','is_not_null')])
        sql, params = compile_inventory_query(mapping)
        self.assertIn('days_of_supply IS NULL', sql)
        self.assertIn('LIMIT 200', sql)
        bad = sql.replace('NOT commerce.inventory.days_of_supply IS NULL AND ', '')
        self.assertNotEqual(sql,bad)
        with self.assertRaises(MetricDefinitionError):
            validate_mapped_sql(decode_query_plan(json.dumps({'sql':bad,'parameters':[str(p) for p in params]})),mapping)

    def test_known_metric_cannot_be_silently_substituted(self):
        with self.assertRaises(MetricDefinitionError):
            self.mapping(metrics=['stock_on_hand'],ranking=None)

    def test_explicit_ranking_cannot_be_dropped_or_reversed(self):
        for ranking in [None,{'metric':'days_of_supply','direction':'desc','limit':10}]:
            mapping=self.mapping(ranking=ranking)
            self.assertIsNotNone(mapping.ranking)
            self.assertEqual(mapping.ranking.direction,'asc')

    def test_most_recent_describes_time_not_ranking(self):
        mapping=decode_metric_mapping(json.dumps(dict(metrics=['stock_on_hand'],
            dimensions=['category'],time={'mode':'latest'})),
            'Stock on hand by category at the most recent available observation')
        self.assertIsNone(mapping.ranking)

    def test_filter_null_operator_rejects_a_value(self):
        with self.assertRaises(MetricDefinitionError):
            self.mapping(filters=[{'field':'days_of_supply','operator':'is_not_null','value':0}])

    def test_unrequested_self_join_and_outer_join_change_source_population(self):
        mapping=self.mapping(filters=[])
        sql,params=compile_inventory_query(mapping)
        for bad in [sql.replace('JOIN commerce.products', 'LEFT JOIN commerce.products'),
                    sql.replace('inventory.product_id = products.product_id', "inventory.product_id = products.product_id AND inventory.snapshot_date='2022-12-31'"),
                    sql.replace(' WHERE ', ' JOIN commerce.inventory extra ON extra.product_id=products.product_id WHERE ')]:
            with self.subTest(sql=bad),self.assertRaises(MetricDefinitionError):
                validate_mapped_sql(decode_query_plan(json.dumps({'sql':bad,'parameters':[str(p) for p in params]})),mapping)

    def test_synthetic_nulls_and_tied_ranks_are_observable(self):
        mapping=self.mapping()
        sql,params=compile_inventory_query(mapping)
        from sqlglot import parse_one
        with sqlite3.connect(':memory:') as db:
            db.execute("ATTACH DATABASE ':memory:' AS commerce")
            db.executescript('CREATE TABLE commerce.inventory(snapshot_date TEXT,product_id INT,days_of_supply REAL);'
                'CREATE TABLE commerce.products(product_id INT PRIMARY KEY);'
                "INSERT INTO commerce.inventory VALUES ('2022-12-31',3,NULL),('2022-12-31',2,4),"
                "('2022-12-31',1,4),('2022-11-30',4,0); INSERT INTO commerce.products VALUES(1),(2),(3),(4);")
            # Keep the compiler's complete SQL and bind values; only transpile dialect syntax.
            query=parse_one(sql,read='postgres').sql(dialect='sqlite')
            actual=db.execute(query,tuple(str(p) for p in params)).fetchall()
        self.assertEqual(actual,[('2022-12-31',1,4.0),('2022-12-31',2,4.0)])

    def test_cancelled_population_and_tied_top_n_are_validated(self):
        sql=("SELECT p.product_id,SUM(oi.quantity) AS n FROM commerce.order_items oi "
             "JOIN commerce.orders o ON o.order_id=oi.order_id JOIN commerce.products p ON oi.product_id=p.product_id "
             "WHERE o.order_date >= DATE '2022-01-01' AND o.order_date < DATE '2023-01-01' "
             "AND LOWER(o.order_status) NOT IN ('cancelled','canceled') GROUP BY p.product_id ORDER BY 2 DESC,p.product_id LIMIT 20")
        question='List the 20 products with the highest order_items.quantity sold during 2022, excluding cancelled orders.'
        validate_metric_definitions(sql,set(),(),APPROVED_COLUMNS,question=question)
        for bad in [sql.replace("LOWER(o.order_status) NOT IN ('cancelled','canceled')","o.order_status <> 'cancelled'"),
                    sql.replace(',p.product_id LIMIT',' LIMIT'),sql.replace('LIMIT 20','LIMIT 10')]:
            with self.subTest(sql=bad),self.assertRaises(MetricDefinitionError):
                validate_metric_definitions(bad,set(),(),APPROVED_COLUMNS,question=question)

    def test_multi_snapshot_mean_and_balance_keep_the_catalog_grain(self):
        for metric in ['fill_rate','stock_on_hand']:
            mapping=decode_metric_mapping(json.dumps(dict(metrics=[metric],dimensions=['category'],
                time={'mode':'range','start':'2022-12-01','end':'2022-12-31'})),
                metric+' by category in December 2022')
            sql,params=compile_inventory_query(mapping)
            bad=sql.replace('GROUP BY commerce.inventory.snapshot_date,','GROUP BY ')
            with self.assertRaises((MetricDefinitionError,SQLValidationError)):
                validate_mapped_sql(decode_query_plan(json.dumps({'sql':bad,'parameters':[str(p) for p in params]})),mapping)

    def test_non_null_discount_equivalence_does_not_authorize_zero_for_missing_values(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('CREATE TABLE lines(quantity INT NOT NULL,unit_price REAL NOT NULL,discount_amount REAL NOT NULL);'
                'INSERT INTO lines VALUES(2,10,3),(1,10,0);')
            self.assertEqual(db.execute('SELECT SUM(quantity*unit_price-discount_amount) FROM lines').fetchone(),
                db.execute('SELECT SUM(quantity*unit_price-COALESCE(discount_amount,0)) FROM lines').fetchone())
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT INTO lines VALUES(1,10,NULL)')
