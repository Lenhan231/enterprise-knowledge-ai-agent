"""Reports and Auto/SQL must use the same approved data boundary."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.analytics.text_to_sql import APPROVED_COLUMNS
from core.agents.report_agent import ReportAgent
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.models.agents import AgentRequest, VerifiedIdentity
from core.reports.planning import ReportPlan, planning_prompt, validate_plan
from core.analytics.text_to_sql import validate_commerce_sql
from core.reports.facts import facts_from_analytics
from core.reports.generation import deterministic_rows
from core.models.agents import AgentResult
from test_report_inventory import Writer, plan


class SharedReportSchemaTest(unittest.TestCase):
    def test_duplicate_raw_sql_rows_keep_their_source_row_identity(self):
        specification = ReportPlan.model_validate({'purpose': 'Methods', 'tasks': [{'id': 'methods', 'question': 'List product colors'}],
            'sections': [{'heading': 'Methods', 'tasks': ['methods']}]})
        result = AgentResult(answer='Rows', agent='sql', data={
            'sql': 'SELECT o.color FROM commerce.products o LIMIT 200', 'parameters': [],
            'rows': [{'color': 'blue'}, {'color': 'blue'}]})
        facts = facts_from_analytics(specification.tasks[0], result, 'S1')
        rows = deterministic_rows(['color'], facts)
        self.assertEqual(len(rows), 2)
        self.assertEqual([fact.source_row for fact in facts], [0, 1])

    def test_report_prompt_contains_the_complete_shared_schema(self):
        prompt = planning_prompt('Inventory and order count report')
        schema = json.loads(prompt.split('\nAvailable SQL schema: ')[1].splitlines()[0])
        self.assertEqual(schema, {table: sorted(columns) for table, columns in APPROVED_COLUMNS.items()})
        self.assertNotIn('commerce.returns', prompt)
        self.assertNotIn('return_rate', prompt)
        self.assertNotIn('Only commerce.inventory and commerce.products are available', prompt)

    def test_reports_share_inventory_only_sources(self):
        self.assertIn('commerce.products', validate_commerce_sql('SELECT o.product_id FROM commerce.products o LIMIT 200').sources)
        with self.assertRaises(ValueError):
            validate_commerce_sql('SELECT order_id FROM commerce.orders LIMIT 200')
        with self.assertRaises(ValueError):
            validate_commerce_sql('SELECT u.password FROM auth.users u LIMIT 200')

    def test_plan_can_delegate_a_task_to_shared_sql_analytics(self):
        specification = {'purpose': 'Product count', 'tasks': [{'id': 'orders', 'question': 'Master product count'}],
            'sections': [{'heading': 'Orders', 'tasks': ['orders'], 'table_columns': ['product_count']}]}
        result = validate_plan(ReportPlan.model_validate(specification), 'Master product count')
        self.assertEqual(result.tasks[0].question, 'Master product count')
        schema = ReportPlan.model_json_schema()
        self.assertEqual(schema['$defs']['InventoryReportMapping']['properties']['domain']['const'], 'inventory')


class SharedReportExecutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_mixed_report_uses_the_shared_sql_validator_and_preserves_identity(self):
        specification = plan()
        specification['tasks'].append({'id': 'orders', 'question': 'Master product count'})
        specification['sections'].append({'heading': 'Orders', 'tasks': ['orders'], 'table_columns': ['product_count']})
        repository = type('Repository', (), {})()
        async def rows(sql, *parameters):
            if 'commerce.products' in sql and 'commerce.inventory' not in sql:
                return [{'product_count': 42}]
            return [{'snapshot_date': '2022-12-31', 'category': 'A', 'stock_on_hand': 10}]
        repository.execute_approved_query = AsyncMock(side_effect=rows)
        class SQLProvider:
            async def generate(self, prompt):
                return json.dumps({'sql': 'SELECT COUNT(DISTINCT o.product_id) AS product_count FROM commerce.products o LIMIT 200',
                    'parameters': []})
        sql_agent = SQLAnalyticsAgent(repository, llm=SQLProvider())
        original = sql_agent.run
        sql_agent.run = AsyncMock(wraps=original)
        agent = ReportAgent(AsyncMock(), sql_agent, llm=Writer(specification))
        identity = VerifiedIdentity(subject='analyst', permissions={'documents:read', 'analytics:read'}, document_roles={'employee'})
        request = AgentRequest(question='Stock on hand latest available snapshot by category and master product count', identity=identity)
        result, payload, _ = await agent.generate_from_template(request, source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertIn(b'42 [F', payload)
        self.assertEqual(sql_agent.run.await_args.args[0].identity, identity)
        self.assertEqual(repository.execute_approved_query.await_count, 2)
        count = next(fact for fact in result.metadata['facts'] if fact['metric'] == 'product_count')
        self.assertEqual(count['unit'], 'source_field')
        self.assertEqual(count['dimensions'], {'product_count': '42'})
        self.assertIn('commerce.products', count['filters'][0]['sql'])

    async def test_unapproved_sql_is_rejected_before_database_execution(self):
        specification = {'purpose': 'Orders', 'tasks': [{'id': 'orders', 'question': 'Master product count'}],
            'sections': [{'heading': 'Orders', 'tasks': ['orders'], 'table_columns': ['product_count']}]}
        repository = type('Repository', (), {})()
        repository.execute_approved_query = AsyncMock()
        provider = type('Provider', (), {})()
        provider.generate = AsyncMock(return_value=json.dumps({'sql': 'SELECT u.password FROM auth.users u LIMIT 200'}))
        agent = ReportAgent(AsyncMock(), SQLAnalyticsAgent(repository, llm=provider), llm=Writer(specification))
        identity = VerifiedIdentity(subject='analyst', permissions={'analytics:read'})
        result, payload, _ = await agent.generate_from_template(AgentRequest(question='Master product count', identity=identity), source_mode='analytics')
        self.assertEqual(result.metadata['failure_type'], 'validation_failed')
        self.assertEqual(payload, b'')
        repository.execute_approved_query.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
