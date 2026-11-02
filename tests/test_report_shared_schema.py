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
        specification = ReportPlan.model_validate({'purpose': 'Methods', 'tasks': [{'id': 'methods', 'question': 'List payment methods'}],
            'sections': [{'heading': 'Methods', 'tasks': ['methods']}]})
        result = AgentResult(answer='Rows', agent='sql', data={
            'sql': 'SELECT o.payment_method FROM commerce.orders o LIMIT 200', 'parameters': [],
            'rows': [{'payment_method': 'card'}, {'payment_method': 'card'}]})
        facts = facts_from_analytics(specification.tasks[0], result, 'S1')
        rows = deterministic_rows(['payment_method'], facts)
        self.assertEqual(len(rows), 2)
        self.assertEqual([fact.source_row for fact in facts], [0, 1])

    def test_report_prompt_contains_the_complete_shared_schema(self):
        prompt = planning_prompt('Inventory and order count report')
        schema = json.loads(prompt.split('\nAvailable SQL schema: ')[1].splitlines()[0])
        self.assertEqual(schema, {table: sorted(columns) for table, columns in APPROVED_COLUMNS.items()})
        self.assertIn('commerce.returns', prompt)
        self.assertIn('return_rate', prompt)
        self.assertNotIn('Only commerce.inventory and commerce.products are available', prompt)

    def test_reports_allow_approved_orders_and_still_reject_unapproved_tables(self):
        self.assertIn('commerce.orders', validate_commerce_sql('SELECT o.order_id FROM commerce.orders o LIMIT 200').sources)
        with self.assertRaises(ValueError):
            validate_commerce_sql('SELECT u.password FROM auth.users u LIMIT 200')

    def test_plan_can_delegate_a_task_to_shared_sql_analytics(self):
        specification = {'purpose': 'Order count', 'tasks': [{'id': 'orders', 'question': 'Order count in 2022'}],
            'sections': [{'heading': 'Orders', 'tasks': ['orders'], 'table_columns': ['order_count']}]}
        result = validate_plan(ReportPlan.model_validate(specification), 'Order count in 2022')
        self.assertEqual(result.tasks[0].question, 'Order count in 2022')
        schema = ReportPlan.model_json_schema()
        self.assertEqual(schema['$defs']['InventoryReportMapping']['properties']['domain']['const'], 'inventory')


class SharedReportExecutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_mixed_report_uses_the_shared_sql_validator_and_preserves_identity(self):
        specification = plan()
        specification['tasks'].append({'id': 'orders', 'question': 'Order count in 2022'})
        specification['sections'].append({'heading': 'Orders', 'tasks': ['orders'], 'table_columns': ['order_count']})
        repository = type('Repository', (), {})()
        async def rows(sql, *parameters):
            if 'commerce.orders' in sql:
                return [{'order_count': 42}]
            return [{'snapshot_date': '2022-12-31', 'category': 'A', 'stock_on_hand': 10}]
        repository.execute_approved_query = AsyncMock(side_effect=rows)
        class SQLProvider:
            async def generate(self, prompt):
                return json.dumps({'sql': 'SELECT COUNT(DISTINCT o.order_id) AS order_count FROM commerce.orders o WHERE o.order_date >= $1 AND o.order_date < $2 LIMIT 200',
                    'parameters': ['2022-01-01', '2023-01-01']})
        sql_agent = SQLAnalyticsAgent(repository, llm=SQLProvider())
        original = sql_agent.run
        sql_agent.run = AsyncMock(wraps=original)
        agent = ReportAgent(AsyncMock(), sql_agent, llm=Writer(specification))
        identity = VerifiedIdentity(subject='analyst', permissions={'documents:read', 'analytics:read'}, document_roles={'employee'})
        request = AgentRequest(question='Stock on hand latest available snapshot by category and order count in 2022', identity=identity)
        result, payload, _ = await agent.generate_from_template(request, source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertIn(b'42 [F', payload)
        self.assertEqual(sql_agent.run.await_args.args[0].identity, identity)
        self.assertEqual(repository.execute_approved_query.await_count, 2)
        count = next(fact for fact in result.metadata['facts'] if fact['metric'] == 'order_count')
        self.assertEqual(count['unit'], 'orders')
        self.assertEqual(count['dimensions'], {})
        self.assertIn('commerce.orders', count['filters'][0]['sql'])

    async def test_unapproved_sql_is_rejected_before_database_execution(self):
        specification = {'purpose': 'Orders', 'tasks': [{'id': 'orders', 'question': 'Order count in 2022'}],
            'sections': [{'heading': 'Orders', 'tasks': ['orders'], 'table_columns': ['order_count']}]}
        repository = type('Repository', (), {})()
        repository.execute_approved_query = AsyncMock()
        provider = type('Provider', (), {})()
        provider.generate = AsyncMock(return_value=json.dumps({'sql': 'SELECT u.password FROM auth.users u LIMIT 200'}))
        agent = ReportAgent(AsyncMock(), SQLAnalyticsAgent(repository, llm=provider), llm=Writer(specification))
        identity = VerifiedIdentity(subject='analyst', permissions={'analytics:read'})
        result, payload, _ = await agent.generate_from_template(AgentRequest(question='Order count in 2022', identity=identity), source_mode='analytics')
        self.assertEqual(result.metadata['failure_type'], 'validation_failed')
        self.assertEqual(payload, b'')
        repository.execute_approved_query.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
