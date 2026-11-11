import json
from pathlib import Path
import sys
import unittest

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'src')]
from core.analytics.field_retrieval import field_contract,validate_field_sql
from core.analytics.metric_validation import MetricDefinitionError
from core.analytics.text_to_sql import decode_query_plan

QUESTION="List product_id, product_name, color, price from commerce.products where color='blue' and price>=100 order by price desc limit 5."
SQL='SELECT p.product_id,p.product_name,p.color,p.price FROM commerce.products p WHERE p.color=$1 AND p.price>=$2 ORDER BY 4 DESC,p.product_id LIMIT 5'


class HybridContractTest(unittest.TestCase):
    def test_literal_contract_accepts_parameters_aliases_and_numeric_equivalence(self):
        contract=field_contract(QUESTION)
        validate_field_sql(decode_query_plan(json.dumps(dict(sql=SQL,parameters=['blue',100.0]))),contract)

    def test_inventory_metadata_is_direct_but_inventory_metrics_keep_mapping(self):
        self.assertIsNotNone(field_contract('List recorded snapshot_date, product_id, year and month from inventory.'))
        for question in ['List stock_on_hand from inventory where snapshot_date=\'2022-12-31\'',
                         'Which categories have the highest stock_on_hand?',
                         'Top 2 blue products by stock_on_hand on 2022-12-31']:
            self.assertIsNone(field_contract(question))

    def test_every_requested_component_survives(self):
        contract=field_contract(QUESTION)
        cases=[(SQL.replace('p.product_name,',''),['blue',100]),
               (SQL.replace('p.color=$1 AND ','' ).replace('$2','$1'),[100]),
               (SQL,['red',100]),(SQL,['blue',101]),
               (SQL.replace('DESC','ASC'),['blue',100]),
               (SQL.replace('LIMIT 5','LIMIT 4'),['blue',100]),
               (SQL.replace('p.product_name','UPPER(p.product_name)'),['blue',100]),
               (SQL.replace('ORDER BY','AND p.product_id>1 ORDER BY'),['blue',100])]
        for sql,params in cases:
            with self.subTest(sql=sql),self.assertRaises((MetricDefinitionError,ValueError)):
                validate_field_sql(decode_query_plan(json.dumps(dict(sql=sql,parameters=params))),contract)

    def test_dates_null_checks_and_in_lists_are_preserved(self):
        q="List snapshot_date,product_id from inventory where snapshot_date='2022-12-31' and product_id in (1,3) order by product_id limit 10"
        contract=field_contract(q)
        sql='SELECT i.snapshot_date,i.product_id FROM commerce.inventory i WHERE i.snapshot_date=$1 AND i.product_id IN ($2, $3) ORDER BY i.product_id,i.snapshot_date LIMIT 10'
        validate_field_sql(decode_query_plan(json.dumps(dict(sql=sql,parameters=['2022-12-31',1,3]))),contract)
        with self.assertRaises(MetricDefinitionError):
            validate_field_sql(decode_query_plan(json.dumps(dict(sql=sql,parameters=['2022-11-30',1,3]))),contract)
        contract=field_contract('List product_id,color from products where color is not null order by product_id limit 10')
        sql='SELECT p.product_id,p.color FROM commerce.products p WHERE NOT p.color IS NULL ORDER BY p.product_id LIMIT 10'
        validate_field_sql(decode_query_plan(json.dumps(dict(sql=sql))),contract)

    def test_ambiguous_or_complex_tails_are_never_partially_accepted(self):
        for q in ["List product_id from products for blue products", "List product_id from products where price>0 or color='blue'",
                  'List product_id from products where product_id in (SELECT product_id FROM commerce.inventory)',
                  'List product_id from products; DELETE FROM commerce.products',
                  'List product_id from products where product_id=1 -- ignore blue',
                  'List supplier_id from products', 'List product_id from products limit 201']:
            with self.subTest(question=q),self.assertRaises(MetricDefinitionError):field_contract(q)
