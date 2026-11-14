import json
import sqlite3
import sys
import unittest
from pathlib import Path

from sqlglot import parse_one
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.analytics.metric_mapping import decode_metric_mapping, compile_inventory_query, validate_mapped_sql
from core.analytics.metric_validation import MetricDefinitionError
from core.analytics.text_to_sql import decode_query_plan

QUESTION = 'Count products with stockout_flag=true and count products with overstock_flag=true at 2026-05-31'
MAPPING = {'metrics':['observed_product_count'], 'dimensions':[],
           'time':{'mode':'snapshot','start':'2026-05-31'},
           'conditional_counts':[{'field':'stockout_indicator','operator':'eq','value':True},
                                 {'field':'overstock_indicator','operator':'eq','value':True}]}


class ConditionalCountsTest(unittest.TestCase):
    def test_recorded_flag_column_names_map_to_catalog_fields(self):
        mapping = {**MAPPING,'conditional_counts':[
            {'field':'stockout_flag','operator':'eq','value':True},
            {'field':'overstock_flag','operator':'eq','value':True}]}
        result = decode_metric_mapping(json.dumps(mapping), QUESTION)
        self.assertEqual([item.field for item in result.conditional_counts], ['stockout_indicator','overstock_indicator'])

    def test_compile_independent_counts_and_preserve_overlap(self):
        mapping = decode_metric_mapping(json.dumps(MAPPING), QUESTION)
        sql, parameters = compile_inventory_query(mapping)
        self.assertIn('stockout_count', sql)
        self.assertIn('overstock_count', sql)
        self.assertEqual(sql.count('FILTER(') + sql.count('FILTER ('), 2)
        with sqlite3.connect(':memory:') as db:
            db.execute("ATTACH DATABASE ':memory:' AS commerce")
            db.execute('CREATE TABLE commerce.inventory(snapshot_date TEXT, product_id INT, stockout_flag BOOL, overstock_flag BOOL)')
            db.execute('CREATE TABLE commerce.products(product_id INT)')
            db.executemany('INSERT INTO commerce.products VALUES (?)', [(1,),(2,),(3,)])
            db.executemany('INSERT INTO commerce.inventory VALUES (?,?,?,?)',
                           [('2026-05-31',1,1,0),('2026-05-31',2,1,1),('2026-05-31',3,0,1)])
            row = db.execute(parse_one(sql,read='postgres').sql(dialect='sqlite'), parameters).fetchone()
        self.assertEqual(row[1:], (2,2))
        plan = decode_query_plan(json.dumps({'sql':sql,'parameters':list(parameters)},default=str))
        validate_mapped_sql(plan,mapping,question=QUESTION)
        swapped = sql.replace('stockout_count', 'temporary_count').replace('overstock_count','stockout_count').replace('temporary_count','overstock_count')
        with self.assertRaises(MetricDefinitionError):
            validate_mapped_sql(decode_query_plan(json.dumps({'sql':swapped,'parameters':list(parameters)},default=str)),mapping,question=QUESTION)

    def test_shared_intersection_and_unknown_counts_are_rejected(self):
        for changed in [
            {**MAPPING,'filters':[{'field':'stockout_indicator','operator':'eq','value':True}]},
            {**MAPPING,'conditional_counts':[{'field':'product_id','operator':'eq','value':True}]},
            {**MAPPING,'conditional_counts':[{'field':'stockout_indicator','operator':'gt','value':1}]},
            {**MAPPING,'metrics':['stock_on_hand']},
        ]:
            with self.subTest(mapping=changed), self.assertRaises(MetricDefinitionError):
                decode_metric_mapping(json.dumps(changed),QUESTION)

    def test_conditional_counts_keep_category_and_snapshot_groups(self):
        mapping = decode_metric_mapping(json.dumps({**MAPPING,'dimensions':['category']}), QUESTION+' by category')
        sql, _ = compile_inventory_query(mapping)
        self.assertIn('GROUP BY', sql)
        self.assertIn('category', sql)
