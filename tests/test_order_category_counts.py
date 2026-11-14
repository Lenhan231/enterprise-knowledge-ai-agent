import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.analytics.metric_ontology import resolve_metric_names, get_metric_definition
from core.analytics.text_to_sql import relevant_schema_tables, validate_commerce_sql, APPROVED_COLUMNS
from core.analytics.metric_validation import validate_metric_definitions, MetricDefinitionError
from core.sql_agent.agent import SQLAnalyticsAgent, AnalyticsPermissionDenied
from core.models.agents import AgentRequest, VerifiedIdentity

QUESTION = 'compare the number of order placed in may 2026 between Streetwear and Casual categories'
SQL = ('SELECT p.category, COUNT(DISTINCT o.order_id) AS order_count FROM commerce.orders o '
       'JOIN commerce.order_items oi ON o.order_id=oi.order_id '
       'JOIN commerce.products p ON oi.product_id=p.product_id '
       'WHERE o.order_date >= $1 AND o.order_date < $2 AND p.category IN ($3, $4) '
       'GROUP BY p.category ORDER BY 1 LIMIT 200')
PARAMETERS = ['2026-05-01', '2026-06-01', 'Streetwear', 'Casual']


class OrderCategoryTest(unittest.TestCase):
    def test_clarity_receives_metric_and_category_semantics(self):
        with patch.dict('os.environ', {'OPENROUTER_API_KEY':'test-placeholder'}), \
                patch('core.sql_agent.agent.OpenAI') as client:
            client.return_value.post.return_value = {'answers': {'intent': {'type':'choice', 'choice':'clear',
                'probabilities':{'clear':.95, 'ambiguous':.05}}}}
            SQLAnalyticsAgent(Mock())._check_ambiguity(QUESTION)
            state = client.return_value.post.call_args.kwargs['body']['state']
        self.assertIn('category', state['metric_definitions']['order_count']['dimensions'])
        self.assertIn('DISTINCT orders.order_id', state['metric_definitions']['order_count']['grouping_semantics'])
        self.assertTrue({'commerce.orders','commerce.order_items','commerce.products'} <= set(state['preferred_sources']))

    def test_recognizes_order_count_phrasing(self):
        for question in [QUESTION, 'Count orders by category', 'Count order by category', 'How many orders by category?', 'Total orders by category',
                         'Number of orders by category', 'Đếm đơn hàng theo danh mục tháng 5 năm 2026']:
            with self.subTest(question=question):
                self.assertIn('order_count', resolve_metric_names(question))
        self.assertNotIn('order_count', resolve_metric_names('Count order items by product'))

    def test_category_context_has_the_complete_approved_bridge(self):
        sources = relevant_schema_tables(QUESTION, {'order_count': get_metric_definition('order_count')})
        self.assertTrue({'commerce.orders', 'commerce.order_items', 'commerce.products'} <= sources)
        self.assertIn('category', get_metric_definition('order_count')['dimensions'])

    def test_distinct_orders_are_counted_once_per_category(self):
        validate_commerce_sql(SQL)
        definitions = validate_metric_definitions(SQL, {'order_count'}, PARAMETERS, APPROVED_COLUMNS)
        self.assertIn('order_count', definitions)
        with sqlite3.connect(':memory:') as db:
            db.execute("ATTACH DATABASE ':memory:' AS commerce")
            db.execute('CREATE TABLE commerce.orders (order_id INTEGER, order_date TEXT)')
            db.execute('CREATE TABLE commerce.order_items (order_id INTEGER, product_id INTEGER)')
            db.execute('CREATE TABLE commerce.products (product_id INTEGER, category TEXT)')
            db.executemany('INSERT INTO commerce.orders VALUES (?,?)', [(1,'2026-05-03'),(2,'2026-05-20'),(3,'2026-06-01')])
            db.executemany('INSERT INTO commerce.products VALUES (?,?)', [(1,'Streetwear'),(2,'Streetwear'),(3,'Casual')])
            db.executemany('INSERT INTO commerce.order_items VALUES (?,?)', [(1,1),(1,2),(1,3),(2,3),(3,1)])
            rows = db.execute(SQL, PARAMETERS).fetchall()
        self.assertEqual(rows, [('Casual', 2), ('Streetwear', 1)])
        for wrong in [SQL.replace('COUNT(DISTINCT o.order_id)', 'COUNT(*)'),
                      SQL.replace('COUNT(DISTINCT o.order_id)', 'COUNT(oi.order_id)')]:
            with self.assertRaises(MetricDefinitionError):
                validate_metric_definitions(wrong, {'order_count'}, PARAMETERS, APPROVED_COLUMNS)


class OrderCategoryGateTest(unittest.IsolatedAsyncioTestCase):
    async def test_clarity_threshold_and_permissions_are_still_enforced(self):
        repository, provider = AsyncMock(), Mock()
        agent = SQLAnalyticsAgent(repository, llm=provider)
        request = AgentRequest(question=QUESTION, identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}))
        with patch.object(agent, '_check_ambiguity', return_value={
                'choice':'clear', 'probabilities':{'clear':.79, 'ambiguous':.21}}):
            result = await agent.run_payload(request)
        self.assertEqual(agent.JEV_MIN_CLEAR_CONFIDENCE, .8)
        self.assertEqual(result['query_status'], 'clarification_required')
        repository.execute_approved_query.assert_not_awaited()
        provider.generate.assert_not_called()
        with patch.object(agent, '_check_ambiguity') as clarity:
            with self.assertRaises(AnalyticsPermissionDenied):
                await agent.run_payload(AgentRequest(question=QUESTION))
            clarity.assert_not_called()

    async def test_clear_request_cannot_execute_unapproved_sql(self):
        repository, provider = AsyncMock(), Mock()
        provider.generate.return_value = json.dumps({'sql':'SELECT u.email FROM public.users u LIMIT 1',
            'parameters':[], 'explanation':'Unapproved source'})
        agent = SQLAnalyticsAgent(repository, llm=provider)
        with patch.object(agent, '_check_ambiguity', return_value={
                'choice':'clear', 'probabilities':{'clear':.95, 'ambiguous':.05}}):
            result = await agent.run_payload(AgentRequest(question=QUESTION,
                identity=VerifiedIdentity(subject='test', permissions={'analytics:read'})))
        self.assertFalse(result['ok'])
        repository.execute_approved_query.assert_not_awaited()
