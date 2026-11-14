"""Production inventory safeguards retained from retired SQL experiments."""
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.sql_agent.agent import SQLAnalyticsAgent, AnalyticsPermissionDenied
from core.models.agents import AgentRequest, VerifiedIdentity
IDENTITY=VerifiedIdentity(subject='inventory-adversarial',permissions={'analytics:read','documents:read'})
SQL = 'SELECT i.snapshot_date,i.product_id,i.stock_on_hand FROM commerce.inventory i JOIN commerce.products p ON i.product_id=p.product_id WHERE i.snapshot_date=$1 AND p.color=$2 ORDER BY 3 DESC NULLS LAST,i.product_id LIMIT 2'
QUESTION = "Top 2 products by highest stock_on_hand on 2022-12-31, only color='blue'."
MAPPING = dict(metrics=['stock_on_hand'], dimensions=['product_id'], representation='product', time={'mode': 'snapshot', 'start': '2022-12-31'}, filters=[dict(field='color', operator='eq', value='blue')], ranking=dict(metric='stock_on_hand', direction='desc', limit=2))

class InventoryAdversarialAgentTest(unittest.IsolatedAsyncioTestCase):

    async def execute(self, sql=SQL, question=QUESTION, parameters=None, identity=IDENTITY):
        provider, repo = (Mock(), AsyncMock())
        provider.generate.return_value = json.dumps(MAPPING)
        repo.execute_approved_query.return_value = [dict(snapshot_date='2022-12-31', product_id=1, stock_on_hand=5)]
        agent = SQLAnalyticsAgent(repo, llm=provider)
        with patch('core.sql_agent.agent.compile_inventory_query', create=True, return_value=(sql, tuple(parameters if parameters is not None else ['2022-12-31', 'blue']))):
            result = await agent.run(AgentRequest(question=question, identity=identity))
        return (result, provider, repo)

    async def test_rbac_precedes_every_provider_and_repository_call(self):
        provider, repo = (Mock(), AsyncMock())
        with self.assertRaises(AnalyticsPermissionDenied):
            await SQLAnalyticsAgent(repo, llm=provider).run(AgentRequest(question=QUESTION, identity=VerifiedIdentity(subject='denied')))
        provider.generate.assert_not_called()
        repo.execute_approved_query.assert_not_awaited()

    async def test_valid_inventory_contract(self):
        result, provider, repo = await self.execute()
        self.assertEqual(result.data.get('query_status'), 'executed', result.answer)
        self.assertEqual(provider.generate.call_count, 1)
        repo.execute_approved_query.assert_awaited_once()

    async def test_invalid_sql_never_reaches_repository(self):
        cases = [(SQL.replace('stock_on_hand', 'stock_on_hand*2'), None), (SQL, ['2021-12-31', 'blue']), (SQL.replace(' AND p.color=$2', ''), ['2022-12-31']), (SQL.replace('DESC NULLS LAST', 'ASC'), None), ('DELETE FROM commerce.inventory', []), ('SELECT s.secret FROM private.secrets s LIMIT 2', []), (SQL.replace('JOIN commerce.products p ON i.product_id=p.product_id', 'JOIN commerce.products p ON i.product_id=p.product_id JOIN commerce.returns r ON r.product_id=p.product_id'), None)]
        for sql, params in cases:
            with self.subTest(sql=sql):
                result, provider, repo = await self.execute(sql, parameters=params)
                self.assertNotEqual(result.data.get('query_status'), 'executed')
                repo.execute_approved_query.assert_not_awaited()
                self.assertLessEqual(provider.generate.call_count, 1)

    async def test_ordinary_inventory_fields_do_not_require_metric_mapping(self):
        sql = 'SELECT i.snapshot_date,i.product_id,i.year,i.month FROM commerce.inventory i ORDER BY 1,2 LIMIT 200'
        provider, repo = (Mock(), AsyncMock())
        provider.generate.side_effect = [json.dumps(dict(domain='other')), *[json.dumps(dict(sql=sql, parameters=[]))] * 2]
        repo.execute_approved_query.return_value = []
        result = await SQLAnalyticsAgent(repo, llm=provider).run(AgentRequest(question='List recorded snapshot_date, product_id, year and month from inventory.', identity=IDENTITY))
        allowed = result.data.get('query_status') == 'executed'
        self.assertTrue(allowed, result.answer)
        if not False:
            provider.generate.assert_not_called()

    async def test_ordinary_product_query(self):
        sql = 'SELECT p.product_id,p.product_name,p.category FROM commerce.products p ORDER BY 1 LIMIT 200'
        provider, repo = (Mock(), AsyncMock())
        provider.generate.return_value = json.dumps(dict(sql=sql, parameters=[]))
        repo.execute_approved_query.return_value = []
        result = await SQLAnalyticsAgent(repo, llm=provider).run(AgentRequest(question='List product IDs, names and categories.', identity=IDENTITY))
        self.assertEqual(result.data.get('query_status'), 'executed', result.answer)
        self.assertEqual(provider.generate.call_count, 1)

    async def test_free_text_filter_loss_is_measured_on_synthetic_rows(self):
        from sqlglot import parse_one
        question = 'Top 2 blue products by highest stock_on_hand on 2022-12-31.'
        wrong = SQL.replace(' AND p.color=$2', '')
        provider, repo = (Mock(), AsyncMock())
        provider.generate.return_value = json.dumps(MAPPING)
        with sqlite3.connect(':memory:') as db:
            db.row_factory = sqlite3.Row
            db.execute("ATTACH DATABASE ':memory:' AS commerce")
            db.executescript("CREATE TABLE commerce.inventory(snapshot_date TEXT,product_id INT,stock_on_hand INT);CREATE TABLE commerce.products(product_id INT PRIMARY KEY,color TEXT);INSERT INTO commerce.inventory VALUES('2022-12-31',1,5),('2022-12-31',2,100);INSERT INTO commerce.products VALUES(1,'blue'),(2,'red');")

            async def query(sql, *params):
                return [dict(r) for r in db.execute(parse_one(sql, read='postgres').sql(dialect='sqlite'), tuple((str(p) for p in params)))]
            repo.execute_approved_query.side_effect = query
            with patch('core.sql_agent.agent.compile_inventory_query', create=True, return_value=(wrong, ('2022-12-31',))):
                result = await SQLAnalyticsAgent(repo, llm=provider).run(AgentRequest(question=question, identity=IDENTITY))
        ids = [r['product_id'] for r in result.data.get('rows', [])]
        gap = result.data.get('query_status') == 'executed' and ids != [1]
        self.assertFalse(gap, 'A dropped filter must never publish the wrong product population.')


class InventoryCanonicalFallbackTest(unittest.IsolatedAsyncioTestCase):

    async def test_rbac_before_contract_provider_or_repository(self):
        repo, provider = (AsyncMock(), Mock())
        with self.assertRaises(AnalyticsPermissionDenied):
            await SQLAnalyticsAgent(repo, llm=provider).run(AgentRequest(question=QUESTION))
        provider.generate.assert_not_called()
        repo.execute_approved_query.assert_not_awaited()

    async def test_canonical_inventory_keeps_mapping_and_compilation(self):
        repo, provider = (AsyncMock(), Mock())
        provider.generate.return_value = json.dumps(dict(metrics=['stock_on_hand'], dimensions=['product_id'], representation='product', time=dict(mode='snapshot', start='2022-12-31'), ranking=dict(metric='stock_on_hand', direction='desc', limit=2), filters=[dict(field='color', operator='eq', value='blue')]))
        repo.execute_approved_query.return_value = [dict(snapshot_date='2022-12-31', product_id=1, stock_on_hand=5)]
        result = await SQLAnalyticsAgent(repo, llm=provider).run(AgentRequest(question='Top 2 blue products by stock_on_hand on 2022-12-31.', identity=IDENTITY))
        self.assertEqual(result.data.get('query_status'), 'executed', result.answer)
        self.assertIn('semantic_interpretation', result.metadata)
        self.assertNotIn('field_retrieval', result.metadata)
        self.assertEqual(provider.generate.call_count, 1)

    async def test_blue_stock_filter_is_not_lost_on_fallback(self):
        repo, provider = (AsyncMock(), Mock())
        mapping = dict(metrics=['stock_on_hand'], dimensions=['product_id'], representation='product', time=dict(mode='snapshot', start='2022-12-31'), ranking=dict(metric='stock_on_hand', direction='desc', limit=2), filters=[dict(field='color', operator='eq', value='blue')])
        provider.generate.return_value = json.dumps(mapping)
        wrong = 'SELECT i.snapshot_date,i.product_id,i.stock_on_hand FROM commerce.inventory i JOIN commerce.products p ON i.product_id=p.product_id WHERE i.snapshot_date=$1 ORDER BY 3 DESC NULLS LAST,i.product_id LIMIT 2'
        with patch('core.sql_agent.agent.compile_inventory_query', return_value=(wrong, ('2022-12-31',))):
            result = await SQLAnalyticsAgent(repo, llm=provider).run(AgentRequest(question='Top 2 blue products by stock_on_hand on 2022-12-31.', identity=IDENTITY))
        self.assertNotEqual(result.data.get('query_status'), 'executed')
        repo.execute_approved_query.assert_not_awaited()
