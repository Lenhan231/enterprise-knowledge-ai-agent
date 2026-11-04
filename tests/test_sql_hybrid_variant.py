import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock,Mock,patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(os.environ.get('SQL_HYBRID_ROOT',ROOT))
sys.path[:0]=[str(SOURCE),str(SOURCE/'src')]
from core.agents.sql_analytics_agent import SQLAnalyticsAgent,AnalyticsPermissionDenied
from core.models.agents import AgentRequest,VerifiedIdentity

HYBRID='SQL_HYBRID_ROOT' in os.environ
IDENTITY=VerifiedIdentity(subject='hybrid-evaluation',permissions={'analytics:read'})
QUESTION="List product_id,product_name,color,price from products where color='blue' and price>=100 order by price desc limit 5."
SQL='SELECT p.product_id,p.product_name,p.color,p.price FROM commerce.products p WHERE p.color=$1 AND p.price>=$2 ORDER BY 4 DESC,p.product_id LIMIT 5'
OBSERVATIONS=[]


class HybridAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_rbac_before_contract_provider_or_repository(self):
        repo,provider=AsyncMock(),Mock()
        with self.assertRaises(AnalyticsPermissionDenied):
            await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(question=QUESTION))
        provider.generate.assert_not_called();repo.execute_approved_query.assert_not_awaited()

    async def test_canonical_inventory_keeps_mapping_and_compilation(self):
        repo,provider=AsyncMock(),Mock()
        provider.generate.return_value=json.dumps(dict(metrics=['stock_on_hand'],dimensions=['product_id'],representation='product',
            time=dict(mode='snapshot',start='2022-12-31'),ranking=dict(metric='stock_on_hand',direction='desc',limit=2),
            filters=[dict(field='color',operator='eq',value='blue')]))
        repo.execute_approved_query.return_value=[dict(snapshot_date='2022-12-31',product_id=1,stock_on_hand=5)]
        result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(question='Top 2 blue products by stock_on_hand on 2022-12-31.',identity=IDENTITY))
        self.assertEqual(result.data.get('query_status'),'executed',result.answer)
        self.assertIn('semantic_interpretation',result.metadata)
        self.assertNotIn('field_retrieval',result.metadata)
        self.assertEqual(provider.generate.call_count,1)

    @unittest.skipUnless(HYBRID,'Isolated hybrid integration')
    async def test_direct_repair_keeps_complete_field_contract(self):
        repo,provider=AsyncMock(),Mock()
        provider.generate.side_effect=[json.dumps(dict(sql=SQL.replace('p.color=$1 AND ','').replace('$2','$1'),parameters=[100])),
                                       json.dumps(dict(sql=SQL,parameters=['blue',100]))]
        repo.execute_approved_query.return_value=[dict(product_id=1,product_name='A',color='blue',price=100)]
        result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(question=QUESTION,identity=IDENTITY))
        self.assertEqual(result.data.get('query_status'),'executed',result.answer)
        self.assertEqual(provider.generate.call_count,2)
        self.assertIn('Validated raw-field contract',provider.generate.call_args.args[0])
        repo.execute_approved_query.assert_awaited_once()
        OBSERVATIONS.append(dict(case='direct_filter_repair',calls=2,executed=True))

    @unittest.skipUnless(HYBRID,'Isolated hybrid integration')
    async def test_oversized_model_literal_is_validation_failure_and_can_be_repaired(self):
        repo,provider=AsyncMock(),Mock()
        provider.generate.side_effect=[json.dumps(dict(sql=SQL.replace('p.price>=$2','p.price>=1e1000000'),parameters=['blue'])),
                                       json.dumps(dict(sql=SQL,parameters=['blue',100]))]
        repo.execute_approved_query.return_value=[dict(product_id=1,product_name='A',color='blue',price=100)]
        result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(question=QUESTION,identity=IDENTITY))
        self.assertEqual(result.data.get('query_status'),'executed',result.answer)
        self.assertEqual(provider.generate.call_count,2)
        repo.execute_approved_query.assert_awaited_once()
        OBSERVATIONS.append(dict(case='oversized_model_number',invalid_attempt_blocked=True,calls=2,executed_after_repair=True))

    @unittest.skipUnless(HYBRID,'Isolated hybrid integration')
    async def test_bad_direct_sql_is_rejected_after_one_repair(self):
        for sql,params in [(SQL,['red',100]),(SQL.replace('p.product_name,',''),['blue',100]),
                           (SQL.replace('DESC','ASC'),['blue',100]),(SQL.replace('LIMIT 5','LIMIT 4'),['blue',100]),
                           ('DELETE FROM commerce.products',[]),
                           ('SELECT p.secret FROM private.secrets p LIMIT 5',[])]:
            repo,provider=AsyncMock(),Mock();provider.generate.return_value=json.dumps(dict(sql=sql,parameters=params))
            result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(question=QUESTION,identity=IDENTITY))
            self.assertNotEqual(result.data.get('query_status'),'executed')
            self.assertFalse(result.metadata.get('clarification_required',False))
            self.assertEqual(provider.generate.call_count,2)
            repo.execute_approved_query.assert_not_awaited()
            OBSERVATIONS.append(dict(case='direct_mutation',sql=sql,blocked=True,calls=2))

    async def test_blue_stock_filter_is_not_lost_on_fallback(self):
        repo,provider=AsyncMock(),Mock()
        mapping=dict(metrics=['stock_on_hand'],dimensions=['product_id'],representation='product',
            time=dict(mode='snapshot',start='2022-12-31'),ranking=dict(metric='stock_on_hand',direction='desc',limit=2),
            filters=[dict(field='color',operator='eq',value='blue')])
        provider.generate.return_value=json.dumps(mapping)
        wrong='SELECT i.snapshot_date,i.product_id,i.stock_on_hand FROM commerce.inventory i JOIN commerce.products p ON i.product_id=p.product_id WHERE i.snapshot_date=$1 ORDER BY 3 DESC NULLS LAST,i.product_id LIMIT 2'
        with patch('core.agents.sql_analytics_agent.compile_inventory_query',return_value=(wrong,('2022-12-31',))):
            result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(question='Top 2 blue products by stock_on_hand on 2022-12-31.',identity=IDENTITY))
        self.assertNotEqual(result.data.get('query_status'),'executed')
        repo.execute_approved_query.assert_not_awaited()
        OBSERVATIONS.append(dict(case='free_text_blue_stock',blocked=True,calls=provider.generate.call_count))

    @unittest.skipUnless(HYBRID,'Isolated hybrid integration')
    async def test_inventory_date_cannot_disappear(self):
        repo,provider=AsyncMock(),Mock()
        sql='SELECT i.snapshot_date,i.product_id FROM commerce.inventory i ORDER BY i.product_id,i.snapshot_date LIMIT 10'
        provider.generate.return_value=json.dumps(dict(sql=sql))
        result=await SQLAnalyticsAgent(repo,llm=provider).run(AgentRequest(
            question="List snapshot_date,product_id from inventory where snapshot_date='2022-12-31' limit 10",identity=IDENTITY))
        self.assertNotEqual(result.data.get('query_status'),'executed')
        self.assertEqual(provider.generate.call_count,2)
        repo.execute_approved_query.assert_not_awaited()
        OBSERVATIONS.append(dict(case='dropped_snapshot',blocked=True,calls=2))
