"""Independent fixtures for the isolated deterministic hybrid, never production routing."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('SQL_DETERMINISTIC_ROOT', ROOT))
sys.path[:0] = [str(SOURCE), str(SOURCE / 'src')]
from evaluation.hybrid_field_contract import field_contract
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.analytics.metric_mapping import decode_metric_mapping, compile_inventory_query
from core.analytics.text_to_sql import decode_query_plan
from core.models.agents import AgentRequest, VerifiedIdentity
from sqlglot import parse_one

IDENTITY = VerifiedIdentity(subject='deterministic-test', permissions={'analytics:read'})


@unittest.skipUnless('SQL_DETERMINISTIC_ROOT' in os.environ, 'Isolated deterministic experiment')
class DeterministicHybridTest(unittest.IsolatedAsyncioTestCase):
    async def test_rbac_and_existing_generic_repair_remain_in_force(self):
        from core.agents.sql_analytics_agent import AnalyticsPermissionDenied
        repo, provider = AsyncMock(), Mock()
        with self.assertRaises(AnalyticsPermissionDenied):
            await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(question='List product_id from products'))
        provider.generate.assert_not_called()
        provider.generate.side_effect = [json.dumps(dict(sql='DELETE FROM commerce.orders')),
            json.dumps(dict(sql='SELECT o.order_id,o.order_status FROM commerce.orders o ORDER BY o.order_id LIMIT 1'))]
        repo.execute_approved_query.return_value=[]
        result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(
            question='List order_id and order_status from commerce.orders ordered by order_id, limit 1.',identity=IDENTITY))
        self.assertEqual(result.data.get('query_status'),'executed',result.answer)
        self.assertEqual(provider.generate.call_count,2)
        repo.execute_approved_query.assert_awaited_once()

    def test_raw_rows_keep_nulls_duplicate_names_ties_and_snapshot_filters(self):
        from evaluation.hybrid_field_contract import compile_field_query
        db=sqlite3.connect(':memory:');db.execute("ATTACH DATABASE ':memory:' AS commerce")
        db.execute('CREATE TABLE commerce.products(product_id INT,product_name TEXT,color TEXT,size TEXT,price NUMERIC)')
        db.executemany('INSERT INTO commerce.products VALUES (?,?,?,?,?)',
            [(3,'same','blue','M',100),(2,'same','blue',None,100),(1,'same','red','M',999)])
        db.execute('CREATE TABLE commerce.inventory(snapshot_date TEXT,product_id INT)')
        db.executemany('INSERT INTO commerce.inventory VALUES (?,?)',
            [('2022-11-30',1),('2022-12-31',1),('2022-12-31',2)])
        for question,expected in [
            ("Show product id, product name, size and price from products with color='blue' sorted by price descending limit 2",
             [(2,'same',None,100),(3,'same','M',100)]),
            ("Liệt kê ngày snapshot và mã sản phẩm từ tồn kho với ngày snapshot='2022-12-31' giới hạn 10",
             [('2022-12-31',1),('2022-12-31',2)]),
        ]:
            plan=compile_field_query(field_contract(question))
            sql=parse_one(plan.sql,read='postgres').sql(dialect='sqlite')
            self.assertEqual(db.execute(sql,tuple(str(v) if hasattr(v,'isoformat') else v for v in plan.parameters)).fetchall(),expected)
        db.close()

    def test_unapproved_cross_snapshot_total_needs_clarification(self):
        from core.analytics.metric_validation import MetricDefinitionError
        payload = dict(metrics=['units_received'], dimensions=['category'],
            time=dict(mode='range',start='2022-01-01',end='2022-12-31'))
        with self.assertRaises(MetricDefinitionError) as caught:
            decode_metric_mapping(json.dumps(payload),'Which categories had the greatest total units_received during 2022?')
        self.assertTrue(caught.exception.clarification)
        payload['dimensions'].append('snapshot_date')
        self.assertIsNotNone(decode_metric_mapping(json.dumps(payload),'Show monthly units_received by category in 2022.'))

    async def test_bilingual_requests_preserve_every_slot_without_a_provider(self):
        questions = [
            "Show product id, product name, color and price from products where color = 'blue' sorted by price descending limit 5.",
            "Liệt kê mã sản phẩm, tên sản phẩm, màu sắc và giá từ sản phẩm với màu sắc = 'blue' sắp xếp theo giá giảm dần giới hạn 5.",
        ]
        for question in questions:
            with self.subTest(question=question):
                repo, provider = AsyncMock(), Mock()
                repo.execute_approved_query.return_value = []
                result = await SQLAnalyticsAgent(repo, llm=provider).run(AgentRequest(question=question, identity=IDENTITY))
                self.assertEqual(result.data.get('query_status'), 'executed', result.answer)
                sql = result.data['sql'].lower()
                self.assertIn('color = $', sql)
                self.assertIn('price desc', sql)
                self.assertIn('limit 5', sql)
                self.assertIn('blue', result.data['parameters'])
                provider.generate.assert_not_called()

    async def test_unsupported_tail_is_clarified_without_execution(self):
        repo, provider = AsyncMock(), Mock()
        result = await SQLAnalyticsAgent(repo, llm=provider).run(AgentRequest(
            question="Show product id from products with color='blue' except discontinued products", identity=IDENTITY))
        self.assertTrue(result.metadata.get('clarification_required'), result.answer)
        repo.execute_approved_query.assert_not_awaited()
        provider.generate.assert_not_called()

    def test_scalar_count_preserves_zero_and_snapshot_without_grouping(self):
        mapping = decode_metric_mapping(json.dumps(dict(metrics=['observed_product_count'], dimensions=[],
            filters=[dict(field='reorder_indicator', operator='eq', value=True)],
            time=dict(mode='snapshot', start='2022-12-31'))),
            'How many products have reorder_flag=true on 2022-12-31?')
        sql, parameters = compile_inventory_query(mapping)
        self.assertNotIn('GROUP BY', sql)
        db = sqlite3.connect(':memory:')
        db.execute("ATTACH DATABASE ':memory:' AS commerce")
        db.execute('CREATE TABLE commerce.products(product_id INT PRIMARY KEY)')
        db.execute('CREATE TABLE commerce.inventory(product_id INT,snapshot_date TEXT,reorder_flag BOOLEAN)')
        db.executemany('INSERT INTO commerce.products VALUES (?)', [(1,), (2,)])
        db.executemany('INSERT INTO commerce.inventory VALUES (?,?,?)',
            [(1,'2022-11-30',1),(1,'2022-12-31',0),(2,'2022-12-31',0)])
        tree = parse_one(sql, read='postgres')
        # SQLite is a synthetic semantic oracle; production still executes PostgreSQL through its repository.
        from sqlglot import exp
        tree = tree.transform(lambda n: exp.convert(str(parameters[int(n.this.this)-1])) if isinstance(n,exp.Parameter) else n)
        values = db.execute(tree.sql(dialect='sqlite')).fetchall()
        self.assertEqual(values, [('2022-12-31',0)])
        db.close()
