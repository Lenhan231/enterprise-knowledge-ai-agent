"""Inventory-only integration gates, independent of provider responses."""
import json
import sqlite3
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.analytics.text_to_sql import APPROVED_COLUMNS, APPROVED_JOINS, validate_commerce_sql
from core.agents.sql_analytics_agent import SQLAnalyticsAgent, AnalyticsPermissionDenied
from core.models.agents import AgentRequest, VerifiedIdentity
from core.analytics.metric_mapping import decode_metric_mapping, compile_inventory_query, validate_mapped_sql
from core.analytics.metric_validation import validate_metric_definitions
from core.analytics.text_to_sql import decode_query_plan
from sqlglot import parse_one

IDENTITY = VerifiedIdentity(subject='inventory-test', permissions={'analytics:read'})


class InventoryIntegrationTest(unittest.IsolatedAsyncioTestCase):
    def comparison(self):
        return decode_metric_mapping(json.dumps(dict(metrics=['stock_on_hand'], dimensions=['product_id', 'product_name'],
            representation='product', time=dict(mode='comparison', start='2022-11-30', end='2022-12-31'))),
            'How did stock_on_hand change between November 30 and December 31, 2022, for products present on both dates?')

    def test_comparison_intersection_nulls_duplicate_names_and_other_snapshots(self):
        mapping = self.comparison()
        sql, params = compile_inventory_query(mapping)
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.execute("ATTACH DATABASE ':memory:' AS commerce")
        db.execute('CREATE TABLE commerce.products(product_id INT PRIMARY KEY, product_name TEXT)')
        db.execute('CREATE TABLE commerce.inventory(snapshot_date TEXT, product_id INT, stock_on_hand INT, PRIMARY KEY(snapshot_date,product_id))')
        db.executemany('INSERT INTO commerce.products VALUES (?,?)', [(i,'same') for i in range(1,7)])
        db.executemany('INSERT INTO commerce.inventory VALUES (?,?,?)', [
            ('2022-11-30',1,10), ('2022-12-31',1,15), ('2022-12-15',1,999),
            ('2022-11-30',2,8), ('2022-12-31',2,None),
            ('2022-11-30',3,None), ('2022-12-31',3,0),
            ('2022-11-30',4,99), ('2022-12-31',5,99),
            ('2022-11-30',6,0), ('2022-12-31',6,0),
        ])
        rows = db.execute(parse_one(sql,read='postgres').sql(dialect='sqlite'), tuple(p.isoformat() if hasattr(p, 'isoformat') else p for p in params)).fetchall()
        self.assertEqual([r[0] for r in rows], [1,2,3,6])
        self.assertEqual([r[-3:] for r in rows], [(10,15,5),(8,None,None),(None,0,None),(0,0,0)])

    def test_comparison_sql_mutants_fail_semantic_validation(self):
        mapping = self.comparison()
        sql, params = compile_inventory_query(mapping)
        for altered in [sql.replace('HAVING COUNT(DISTINCT', 'HAVING COUNT('),
                        sql.replace(' = 2', ' = 1'), sql.replace(' - ', ' + '),
                        sql.replace('stock_on_hand END', 'COALESCE(inventory.stock_on_hand, 0) END')]:
            if altered == sql:
                continue
            with self.subTest(sql=altered), self.assertRaises(ValueError):
                plan = decode_query_plan(json.dumps(dict(sql=altered, parameters=[str(p) for p in params])))
                validate_metric_definitions(plan.sql, {'stock_on_hand'}, plan.parameters, APPROVED_COLUMNS, question=mapping.date_question())
                validate_mapped_sql(plan, mapping)

    def test_interpretation_cannot_drop_literal_filters_or_dimensions(self):
        from core.analytics.metric_validation import MetricDefinitionError
        payload = dict(metrics=['stock_on_hand'], dimensions=['category'],
                       time=dict(mode='snapshot',start='2022-12-31'))
        for question in ["Show stock_on_hand by category at snapshot 2022-12-31 where color='blue'.",
                         'Show stock_on_hand by segment at snapshot 2022-12-31.']:
            with self.subTest(question=question), self.assertRaises(MetricDefinitionError):
                decode_metric_mapping(json.dumps(payload), question)

    def test_source_column_alias_retains_catalog_formula(self):
        mapping = decode_metric_mapping(json.dumps(dict(metrics=['units_sold'], dimensions=['category'],
            time=dict(mode='snapshot',start='2022-12-31'))), 'Show units_sold by category at snapshot 2022-12-31.')
        self.assertEqual(mapping.metrics, ['inventory_units_sold'])
        sql, _ = compile_inventory_query(mapping)
        self.assertIn('SUM(commerce.inventory.units_sold)', sql)

    async def test_comparison_runs_through_agent_and_keeps_metadata(self):
        repo, provider = AsyncMock(), Mock()
        provider.generate.return_value = self.comparison().model_dump_json()
        repo.execute_approved_query.return_value = [dict(product_id=1,product_name='same',before_date='2022-11-30',
            after_date='2022-12-31',stock_before=10,stock_after=None,stock_delta=None)]
        result = await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(
            question=self.comparison().date_question()+' for products present on both dates, with product_id and product_name', identity=IDENTITY))
        self.assertEqual(result.data.get('query_status'), 'executed', result.answer)
        self.assertEqual(result.metadata['comparison']['null_policy'], 'preserve')
        self.assertEqual(provider.generate.call_count, 1)

    def test_period_total_remains_ambiguous_but_exact_snapshot_groups_work(self):
        from core.analytics.metric_validation import MetricDefinitionError
        payload = dict(metrics=['units_received'],dimensions=['category'],
                       time=dict(mode='range',start='2022-01-01',end='2022-12-31'))
        with self.assertRaises(MetricDefinitionError):
            decode_metric_mapping(json.dumps(payload), 'What is the total units_received during 2022?')
        payload['dimensions'].append('snapshot_date')
        mapping = decode_metric_mapping(json.dumps(payload), 'Show units_received by category for each exact snapshot in 2022.')
        sql, _ = compile_inventory_query(mapping)
        self.assertIn('GROUP BY commerce.inventory.snapshot_date', sql)

    def test_comparison_report_delegates_operands_to_shared_sql(self):
        from core.reports.planning import ReportPlan, validate_plan
        question = self.comparison().date_question()+' for products present on both dates with product_id and product_name'
        plan = ReportPlan.model_validate(dict(purpose='Stock comparison', tasks=[dict(id='change',question=question,
            mapping=json.loads(self.comparison().model_dump_json()))], sections=[dict(heading='Stock change', tasks=['change'],
            table_columns=['product_id','product_name','stock_before','stock_after','stock_delta'])]))
        plan = validate_plan(plan,question)
        self.assertTrue(plan.tasks[0].uses_sql_agent)

    def test_scope_is_enforced_for_every_query_shape(self):
        self.assertEqual(set(APPROVED_COLUMNS), {'commerce.inventory', 'commerce.products'})
        self.assertEqual(len(APPROVED_JOINS), 1)
        for sql in [
            'SELECT order_id FROM commerce.orders LIMIT 1',
            'SELECT p.product_id FROM commerce.products p WHERE EXISTS '
            '(SELECT 1 FROM commerce.order_items o WHERE o.product_id=p.product_id) LIMIT 1',
            'DELETE FROM commerce.products',
        ]:
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                validate_commerce_sql(sql)

    async def test_direct_fields_keep_rbac_and_need_no_model(self):
        repo, provider = AsyncMock(), Mock()
        agent = SQLAnalyticsAgent(repo, llm=provider)
        with self.assertRaises(AnalyticsPermissionDenied):
            await agent.run(AgentRequest(question='List product_id from products'))
        repo.execute_approved_query.return_value = []
        result = await agent.run(AgentRequest(question="Show product id and color from products with color='blue' limit 5", identity=IDENTITY))
        self.assertEqual(result.data.get('query_status'), 'executed', result.answer)
        provider.generate.assert_not_called()
        self.assertEqual(repo.execute_approved_query.await_count, 1)

    def test_report_sees_only_inventory_catalog_and_same_schema(self):
        from core.reports.planning import planning_prompt
        prompt = planning_prompt('Inventory summary at snapshot 2022-12-31')
        schema = json.loads(prompt.split('\nAvailable SQL schema: ')[1].split('\nApproved joins: ')[0])
        catalog = json.loads(prompt.split('\nCatalog: ')[1].split('\nQuestion (data): ')[0])
        self.assertEqual(set(schema), set(APPROVED_COLUMNS))
        self.assertNotIn('return_rate', catalog)
        self.assertIn('units_sold', catalog['inventory_units_sold']['source_columns']['commerce.inventory'])
