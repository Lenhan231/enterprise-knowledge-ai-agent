import copy
import unittest
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace

from core.models.agents import AgentRequest, Evidence, VerifiedIdentity
from core.agents.report.inventory_operations import load_contract, retrieve_policies


class PolicyRetrievalTest(unittest.IsolatedAsyncioTestCase):
    async def test_knowledge_filters_authorized_policy_documents_before_ranking(self):
        from core.agents.knowledge.agent import KnowledgeAgent
        rag=SimpleNamespace(retrieve_contexts=Mock(return_value=[]))
        repository=SimpleNamespace(accessible_document_ids_by_title=Mock(return_value=['visible-policy']),close=Mock())
        request=AgentRequest(question='Inventory policy',identity=VerifiedIdentity(subject='test',permissions={'documents:read'},document_roles={'operations'}),
            metadata={'retrieval_method':'bm25','_policy_source_titles':['Approved policy']})
        with patch('core.database.document_repository.DocumentRepository',return_value=repository):
            await KnowledgeAgent(rag).retrieve(request)
            self.assertEqual(rag.retrieve_contexts.call_args.kwargs['document_ids'],['visible-policy'])
            self.assertEqual(rag.retrieve_contexts.call_args.kwargs['roles'],['operations'])
            repository.accessible_document_ids_by_title.assert_called_with(['Approved policy'],['operations'])
            rag.retrieve_contexts.return_value=[{'document_name':'Approved policy','chunk_index':0,'content':'Unauthorized same-name document', 'metadata':{'document_id':'wrong-id'}}]
            self.assertEqual(await KnowledgeAgent(rag).retrieve(request),[])
            repository.accessible_document_ids_by_title.return_value=[]
            rag.retrieve_contexts.reset_mock()
            self.assertEqual(await KnowledgeAgent(rag).retrieve(request),[])
            rag.retrieve_contexts.assert_not_called()

    async def test_document_filter_cannot_be_silently_dropped_by_a_backend(self):
        from core.agents.knowledge.rag_service import RAGService
        def retrieve(request,roles=None,method=None):
            raise AssertionError('A backend without document scope must not be called')
        rag=RAGService(retrieval_service=SimpleNamespace(retrieve=retrieve),llm=object())
        with self.assertRaisesRegex(ValueError,'document-scoped'):
            rag.retrieve_contexts('Policy',roles=['operations'],document_ids=['policy'],retrieval_method='bm25')

    async def test_fixed_policy_retrieval_uses_lexical_search_and_accepts_enterprise_policy(self):
        evidence=Evidence(source_type='document',source='VietStyle_Enterprise_Operating_Policy_v1.0_EN.pdf',
            content='Reorder indicators prioritize review; they do not authorize an automatic purchase.',
            metadata={'document_id':'approved-policy','section_title':'Reorder signals and replenishment review','page_number':30})
        async def retrieve(request):
            if request.metadata.get('retrieval_method') != 'bm25':
                raise RuntimeError('Embedding service unavailable')
            return [evidence.model_copy(update={'content':'Section: System and data alignment\nPOLICY PAGE 30 | Inventory, receiving and returns'}),evidence,evidence]
        knowledge=SimpleNamespace(retrieve=AsyncMock(side_effect=retrieve))
        request=AgentRequest(question='Inventory report from Jan to Nov 2026',identity=VerifiedIdentity(
            subject='test',permissions={'documents:read'},document_roles={'operations'}))
        context=await retrieve_policies(knowledge,request)
        self.assertEqual(context['retrieval_status'],'available')
        self.assertEqual(len(context['documents']),1)
        self.assertEqual(context['documents'][0]['metadata']['page_number'],30)
        self.assertEqual(knowledge.retrieve.await_args.args[0].identity,request.identity)


class ReportGuidanceTest(unittest.TestCase):
    def test_inventory_guidance_explains_observation_action_and_verified_coverage(self):
        from core.agents.report.presentation import inventory_insights
        report=copy.deepcopy(load_contract()['runtime_output_template'])
        report['data_quality'].update(coverage_end='2026-11-13',partial_period=False,missing_or_unmatched_count=0)
        for metric in report['metrics']:
            metric.update(status='available',value={'stockout_products':17,'overstock_products':91,'reorder_products':0}.get(metric['id'],97))
        for rule in report['decisions']:
            rule['triggered']=rule['id'] in {'I01','I03'}
        before=copy.deepcopy(report)
        insights=inventory_insights(report)
        self.assertIn('17',insights['actions'][0]['why'])
        self.assertIn('confirm',insights['actions'][0]['action'].lower())
        self.assertTrue(any('9 of 9' in item for item in insights['validation_summary']))
        self.assertTrue(any('coverage' in item.lower() and 'verified' in item.lower() for item in insights['validation_summary']))
        self.assertEqual(report,before)
        report['data_quality'].update(partial_period=True,missing_or_unmatched_count=4)
        self.assertTrue(any('4' in item and 'missing' in item for item in inventory_insights(report)['validation_summary']))

    def test_sales_actions_explain_the_observation_and_next_step_without_changing_rules(self):
        from core.agents.report.presentation import decision_text
        from core.agents.report.sales_performance import load_contract as sales_contract
        rule=copy.deepcopy(sales_contract()['runtime_output_template']['decisions'][0])
        rule['triggered']=True
        before=copy.deepcopy(rule)
        text=decision_text(rule)
        self.assertIn('pricing',text.lower())
        self.assertIn('cause',text.lower())
        self.assertEqual(rule,before)
