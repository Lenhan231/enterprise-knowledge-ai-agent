"""The SQL agent uses the live schema while keeping the read-only SQL gate."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.analytics.text_to_sql import SQLValidationError, validate_commerce_sql
from core.models.agents import AgentRequest, VerifiedIdentity
from core.sql_agent.agent import SQLAnalyticsAgent
from core.sql_agent.schema import configured_schemas


class DynamicSchemaTest(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_queries_a_discovered_schema_with_quoted_identifiers(self):
        query = 'SELECT t."customerName" FROM "MySchema"."order-history" AS t LIMIT 10'
        repository = Mock()
        repository.get_schema = AsyncMock(return_value={
            'tables': {'MySchema.order-history': frozenset({'id', 'customerName'})},
            'primary_keys': {'MySchema.order-history': frozenset({'id'})},
            'joins': frozenset(),
            'date_columns': frozenset(),
        })
        repository.execute_approved_query = AsyncMock(return_value=[{'customerName': 'An'}])
        provider = Mock()
        provider.generate = AsyncMock(return_value=json.dumps({'sql': query, 'parameters': []}))
        agent = SQLAnalyticsAgent(repository, llm=provider)

        result = await agent.run(AgentRequest(question='List customerName from order-history',
            identity=VerifiedIdentity(subject='local-test', permissions={'analytics:read'})))

        self.assertEqual(result.data['query_status'], 'executed')
        self.assertEqual(result.data['rows'], [{'customerName': 'An'}])
        self.assertIn('MySchema.order-history', provider.generate.await_args.args[0])
        repository.execute_approved_query.assert_awaited_once_with(query)

    async def test_auto_planner_replans_with_live_schema_only_for_sql_tasks(self):
        from core.agents.router import AgentRouter

        repository = Mock()
        repository.get_schema = AsyncMock(return_value={
            'tables': {'MySchema.order-history': frozenset({'id', 'customerName'})},
            'primary_keys': {'MySchema.order-history': frozenset({'id'})},
            'joins': frozenset(), 'date_columns': frozenset(),
        })
        sql_agent = SQLAnalyticsAgent(repository, llm=Mock())
        plan = json.dumps({'objective': 'query data', 'tasks': [
            {'id': 'query', 'agent': 'sql', 'question': 'List customerName from order-history'}]})
        provider = Mock()
        provider.generate = AsyncMock(side_effect=[plan, plan])
        router = AgentRouter(None, None, sql_agent, llm=provider)
        state = {
            'request': AgentRequest(question='List customerName from MySchema.order-history'),
            'history': [], 'execution': SimpleNamespace(plan=None), 'report_headings': None,
        }

        await router._plan(state)

        self.assertEqual(provider.generate.await_count, 2)
        self.assertIn('MySchema.order-history', provider.generate.await_args_list[1].args[0])
        repository.get_schema.assert_awaited_once()

    async def test_auto_planner_discovers_schema_when_analytics_question_was_misclassified_as_clarification(self):
        from core.agents.router import AgentRouter

        repository = Mock()
        repository.get_schema = AsyncMock(return_value={
            'tables': {'commerce.promotions': frozenset({'promo_id', 'promo_name'})},
            'primary_keys': {'commerce.promotions': frozenset({'promo_id'})},
            'joins': frozenset(), 'date_columns': frozenset(),
        })
        sql_agent = SQLAnalyticsAgent(repository, llm=Mock())
        clarification = json.dumps({'objective': 'promotion performance', 'tasks': [],
                                    'clarification': 'I need more context.'})
        resolved = json.dumps({'objective': 'promotion performance', 'tasks': [
            {'id': 'query', 'agent': 'sql', 'question': 'Compare promotion revenue and margin'}]})
        provider = Mock()
        provider.generate = AsyncMock(side_effect=[clarification, resolved])
        router = AgentRouter(None, None, sql_agent, llm=provider)
        question = 'Khuyến mãi nào tạo ra nhiều doanh thu nhất nhưng có biên lợi nhuận gộp thấp nhất?'
        state = {
            'request': AgentRequest(question=question), 'history': [],
            'execution': SimpleNamespace(plan=None), 'report_headings': None,
        }

        await router._plan(state)

        self.assertFalse(state['execution'].plan.clarification)
        self.assertEqual(provider.generate.await_count, 2)
        self.assertIn('commerce.promotions', provider.generate.await_args_list[1].args[0])
        repository.get_schema.assert_awaited_once()

    def test_live_schema_is_an_allowlist_and_system_schemas_cannot_be_configured(self):
        schema = {'MySchema.order-history': frozenset({'id', 'customerName'})}
        with self.assertRaises(SQLValidationError):
            validate_commerce_sql('SELECT t.id FROM public.users t LIMIT 1', schema_columns=schema)
        self.assertEqual(configured_schemas('commerce, reporting,commerce'), ('commerce', 'reporting'))
        with self.assertRaises(ValueError):
            configured_schemas('commerce, pg_catalog')

    def test_discovered_foreign_keys_and_primary_keys_validate_dynamic_join(self):
        schema = {
            'MySchema.users': frozenset({'id', 'customerName'}),
            'MySchema.orders': frozenset({'id', 'userId'}),
        }
        joins = {frozenset({('MySchema.orders', 'userId'), ('MySchema.users', 'id')})}
        primary_keys = {'MySchema.users': frozenset({'id'}), 'MySchema.orders': frozenset({'id'})}
        query = ('SELECT u."customerName" AS customer, COUNT(DISTINCT o.id) AS order_count '
                 'FROM "MySchema".users AS u LEFT JOIN "MySchema".orders AS o '
                 'ON o."userId" = u.id GROUP BY u."customerName" LIMIT 50')

        result = validate_commerce_sql(query, schema_columns=schema, approved_joins=joins,
                                       primary_keys=primary_keys)

        self.assertEqual(result.sources, ('MySchema.users', 'MySchema.orders'))


if __name__ == '__main__':
    unittest.main()
