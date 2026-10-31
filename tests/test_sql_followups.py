import asyncio
import copy
from datetime import date
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core.analytics.metric_mapping import decode_sql_turn
from core.analytics.metric_validation import MetricDefinitionError
from core.agents.router import AgentRouter
from core.agents.sql_analytics_agent import SQLAnalyticsAgent, AnalyticsPermissionDenied
from core.models.agents import AgentRequest, AgentResult, VerifiedIdentity, validate_chat_metadata

BASE = {'metrics':['stock_on_hand'],'dimensions':['category'],'time':{'mode':'snapshot','start':'2022-12-31'}}
STATE = {'accepted':BASE,'pending':None}
IDENTITY = VerifiedIdentity(subject='test',permissions={'analytics:read'})


class SQLPatchTest(unittest.TestCase):
    def test_mixed_language_filter_patch_and_snapshot_refresh(self):
        mapping,used=self.decode({'action':'followup','changes':{'filters':[{'field':'color','operator':'eq','value':'blue'}]}},
                                 question='Chỉ lấy blue products thôi')
        self.assertTrue(used)
        refreshed,_=self.decode({'action':'followup','changes':{'time':{'mode':'latest'}}},
                                {'accepted':mapping.model_dump(),'pending':None},'Refresh to latest snapshot')
        self.assertEqual(refreshed.time.mode,'latest')
        self.assertEqual(refreshed.filters[0].value,'blue')

    def test_context_injection_is_rejected_at_client_boundary(self):
        with self.assertRaises(ValueError):validate_chat_metadata({'_sql_context':STATE})

    def decode(self,payload,state=None,question='Only blue products'):
        return decode_sql_turn(json.dumps(payload),question,state or STATE)

    def test_followup_merges_filters_and_ranking_without_dropping_scope(self):
        mapping,used=self.decode({'action':'followup','changes':{'filters':[{'field':'color','operator':'eq','value':'blue'}]}})
        self.assertTrue(used)
        self.assertEqual(mapping.time.start,'2022-12-31')
        mapping,used=self.decode({'action':'followup','changes':{'ranking':{'limit':3,'direction':'desc'}}},
                                 {'accepted':mapping.model_dump(),'pending':None},'Now show the top three categories')
        self.assertEqual(mapping.metrics,['stock_on_hand'])
        self.assertEqual(mapping.dimensions,['category'])
        self.assertEqual(mapping.filters[0].value,'blue')
        self.assertEqual(mapping.ranking.metric,'stock_on_hand')
        self.assertEqual(mapping.ranking.limit,3)

    def test_filter_replacement_removal_clear_and_ranking_removal(self):
        state=copy.deepcopy(STATE)
        state['accepted']['filters']=[{'field':'color','operator':'eq','value':'blue'},{'field':'size','operator':'eq','value':'M'}]
        state['accepted']['ranking']={'metric':'stock_on_hand','direction':'desc','limit':3}
        mapping,_=self.decode({'action':'followup','changes':{'filters':[{'field':'color','operator':'eq','value':'black'}],
                                                           'ranking':None}},state)
        self.assertEqual({f.field:f.value for f in mapping.filters},{'color':'black','size':'M'})
        self.assertIsNone(mapping.ranking)
        mapping,_=self.decode({'action':'followup','changes':{'remove_filters':['color']}},state)
        self.assertEqual([f.field for f in mapping.filters],['size'])
        mapping,_=self.decode({'action':'followup','changes':{'clear_filters':True}},state)
        self.assertEqual(mapping.filters,[])

    def test_fresh_question_has_no_inherited_filters_or_date(self):
        mapping,used=self.decode({'action':'new','mapping':{'metrics':['fill_rate'],'time':{'mode':'latest'}}},question='Average fill rate at latest snapshot')
        self.assertFalse(used)
        self.assertEqual(mapping.metrics,['fill_rate'])
        self.assertEqual(mapping.time.mode,'latest')
        self.assertEqual(mapping.filters,[])
        with self.assertRaises(MetricDefinitionError):
            self.decode({'action':'new','mapping':{'metrics':['stock_on_hand']}},question='Show stock by category')

    def test_missing_context_unknown_metric_and_ambiguous_ranking_fail_closed(self):
        for payload,state in [({'action':'followup','changes':{'ranking':{'limit':3}}},{'accepted':None,'pending':None}),
                              ({'action':'followup','changes':{'metrics':['reorder_quantity']}},STATE),
                              ({'action':'followup','changes':{'ranking':{'limit':3}}},
                               {'accepted':{**BASE,'metrics':['stock_on_hand','fill_rate']},'pending':None})]:
            with self.assertRaises(MetricDefinitionError):self.decode(payload,state)

    def test_pending_reply_resolves_original_question_without_reusing_old_scope(self):
        state={'accepted':BASE,'pending':{'question':'Show mean fill rate by category','clarification':'Which snapshot?'}}
        mapping,used=self.decode({'action':'answer','mapping':{'metrics':['fill_rate'],'dimensions':['category'],'time':{'mode':'latest'}}},state,'Latest available snapshot')
        self.assertEqual(mapping.metrics,['fill_rate'])
        self.assertTrue(used)
        with self.assertRaises(MetricDefinitionError):self.decode({'action':'followup','changes':{'ranking':{'limit':3}}},state)


class SQLConversationTest(unittest.IsolatedAsyncioTestCase):
    async def test_expiry_identity_permission_changes_and_restart_clear_scope(self):
        agent=Mock();seen=[]
        async def run(request):
            seen.append(request.metadata.get('_sql_context'))
            return AgentResult(answer='done',agent='analytics',data={'query_status':'executed'},metadata={'semantic_interpretation':BASE})
        agent.run=run
        router=AgentRouter(None,None,agent)
        clock=Mock(return_value=0);router.sql_conversations.clock=clock
        await router.run_mode(self.request('First'),'sql')
        await router.run_mode(self.request('Follow up'),'sql')
        self.assertIsNotNone(seen[-1]['accepted'])
        await router.run_mode(self.request('Other user',subject='someone-else'),'sql')
        self.assertIsNone(seen[-1]['accepted'])
        await router.run_mode(self.request('Other session',conversation='new'),'sql')
        self.assertIsNone(seen[-1]['accepted'])
        changed=self.request('Changed role').model_copy(update={'identity':VerifiedIdentity(subject='test',permissions={'analytics:read'},document_roles={'operations'})})
        await router.run_mode(changed,'sql')
        self.assertIsNone(seen[-1]['accepted'])
        clock.return_value=1801
        await router.run_mode(changed,'sql')
        self.assertIsNone(seen[-1]['accepted'])
        fresh=AgentRouter(None,None,agent)
        await fresh.run_mode(self.request('After restart'),'sql')
        self.assertIsNone(seen[-1]['accepted'])

    async def test_no_id_and_non_sql_modes_do_not_receive_or_update_sql_context(self):
        agent=Mock();seen=[]
        async def run(request):
            seen.append(request.metadata)
            return AgentResult(answer='done',agent='analytics')
        agent.run=run
        router=AgentRouter(None,agent,agent,dashboard_agent=agent,report_agent=agent)
        for mode in ('sql','knowledge','dashboard','report'):
            await router.run_mode(self.request('Question',conversation=None if mode=='sql' else 'session',permissions={'analytics:read','documents:read'}),mode)
        self.assertTrue(all('_sql_context' not in item for item in seen))
        self.assertEqual(len(router.sql_conversations.entries),0)

    async def test_failed_turn_retains_last_scope_and_blocks_implicit_revival(self):
        agent=Mock()
        agent.run=AsyncMock(side_effect=[
            AgentResult(answer='done',agent='analytics',data={'query_status':'executed'},metadata={'semantic_interpretation':BASE}),
            AgentResult(answer='Unsupported',agent='analytics',metadata={'clarification_required':True,'_sql_context_action':'new'})])
        router=AgentRouter(None,None,agent)
        await router.run_mode(self.request('First'),'sql')
        await router.run_mode(self.request('What safety stock do we need?'),'sql')
        from core.analytics.metric_mapping import SQLConversationState
        state=SQLConversationState.model_validate_json(router.sql_conversations.entries[('test','session')].history[-1]['sql_state'])
        self.assertEqual(state.accepted.metrics,['stock_on_hand'])
        with self.assertRaises(MetricDefinitionError):
            decode_sql_turn(json.dumps({'action':'followup','changes':{'clear_filters':True}}),'Only blue',state.model_dump())
        with self.assertRaises(MetricDefinitionError):
            decode_sql_turn(json.dumps({'action':'answer','mapping':BASE}),'Latest',state.model_dump())

    async def test_concurrent_turns_are_serialized_and_timeout_does_not_commit(self):
        entered=asyncio.Event();release=asyncio.Event();agent=Mock();calls=[]
        async def run(request):
            calls.append(request.metadata['_sql_context'])
            if len(calls)==1:
                entered.set();await release.wait()
            return AgentResult(answer='done',agent='analytics',data={'query_status':'executed'},metadata={'semantic_interpretation':BASE})
        agent.run=run;router=AgentRouter(None,None,agent)
        first=asyncio.create_task(router.run_mode(self.request('First'),'sql'))
        await entered.wait()
        second=asyncio.create_task(router.run_mode(self.request('Second'),'sql'))
        await asyncio.sleep(0)
        self.assertEqual(len(calls),1)
        release.set();await asyncio.gather(first,second)
        self.assertIsNotNone(calls[1]['accepted'])
        slow=Mock();slow.run=AsyncMock(side_effect=lambda request:None)
        async def blocked(request):await asyncio.sleep(1)
        slow.run=blocked
        timed=AgentRouter(None,None,slow,request_timeout=.01)
        result=await timed.run_mode(self.request('Timeout'),'sql')
        self.assertFalse(result.metadata['ok'])
        self.assertEqual(timed.sql_conversations.entries[('test','session')].history,[])

    async def test_denied_user_never_reads_context_or_calls_provider(self):
        provider,repo=Mock(),AsyncMock();router=AgentRouter(None,None,SQLAnalyticsAgent(repo,llm=provider))
        request=self.request('Only blue').model_copy(update={'identity':VerifiedIdentity(subject='test')})
        with self.assertRaises(PermissionError):await router.run_mode(request,'sql')
        self.assertEqual(len(router.sql_conversations.entries),0)
        provider.generate.assert_not_called()
        repo.execute_approved_query.assert_not_awaited()

    def request(self,question,subject='test',conversation='session',permissions=None):
        return AgentRequest(question=question,conversation_id=conversation,
                            identity=VerifiedIdentity(subject=subject,permissions=permissions or {'analytics:read'},document_roles={'admin'}))

    async def test_three_turn_sequence_pins_latest_and_executes_each_turn(self):
        first='SELECT i.snapshot_date,p.category,SUM(i.stock_on_hand) AS stock_on_hand FROM commerce.inventory AS i JOIN commerce.products AS p ON i.product_id=p.product_id WHERE i.snapshot_date=$1 GROUP BY i.snapshot_date,p.category LIMIT 200'
        second=first.replace(' GROUP BY',' AND p.color=$2 GROUP BY')
        third=second.replace('LIMIT 200','ORDER BY 3 DESC LIMIT 3')
        provider=Mock()
        provider.generate.side_effect=[json.dumps({'action':'new','mapping':{**BASE,'time':{'mode':'latest'}}}),json.dumps({'sql':first,'parameters':['2022-12-31']}),
                                       json.dumps({'action':'followup','changes':{'filters':[{'field':'color','operator':'eq','value':'blue'}]}}),json.dumps({'sql':second,'parameters':['2022-12-31','blue']}),
                                       json.dumps({'action':'followup','changes':{'ranking':{'direction':'desc','limit':3}}}),json.dumps({'sql':third,'parameters':['2022-12-31','blue']})]
        repository=AsyncMock()
        repository.execute_approved_query.side_effect=[[{'snapshot_date':date(2022,12,31)}],
            [{'snapshot_date':date(2022,12,31),'category':'A','stock_on_hand':12}],[],
            [{'snapshot_date':date(2022,12,31),'category':'A','stock_on_hand':3}]]
        router=AgentRouter(None,None,SQLAnalyticsAgent(repository,llm=provider))
        results=[]
        for question in ['Show stock by category at latest snapshot','Only blue products','Now show the top three categories']:
            results.append(await router.run_mode(self.request(question),'sql'))
        self.assertTrue(results[0].metadata['ok'],results[0].answer)
        self.assertEqual(results[1].data['query_status'],'executed')
        self.assertTrue(results[2].metadata['ok'],results[2].answer)
        self.assertTrue(results[2].metadata['context_used'])
        self.assertEqual(results[2].metadata['semantic_interpretation']['time']['start'],'2022-12-31')
        self.assertEqual(repository.execute_approved_query.await_count,4)
        saved=router.sql_conversations.entries[('test','session')].history
        self.assertNotIn('stock_on_hand": 12',json.dumps(saved))
        self.assertNotIn('SELECT',json.dumps(saved))
