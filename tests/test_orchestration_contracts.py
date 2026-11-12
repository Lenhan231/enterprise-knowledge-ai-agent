import asyncio
import json
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.agents.runtime import deadline, run_sync
from core.agents.knowledge_agent import KnowledgeAgent
from core.agents.router import AgentRouter
from core.agents.response import _supported_numbers
from core.models.agents import AgentRequest, AgentResult, Evidence, VerifiedIdentity
from test_bounded_execution import FakeAgent, FakeProvider, IDENTITY, source_result, task


class OrchestrationContractTest(unittest.IsolatedAsyncioTestCase):
    def test_numeric_grounding_accepts_localized_thousands_but_not_new_magnitudes(self):
        inputs = [{'data': {'rows': [{'count': 1320}]}, 'evidence': []}]
        self.assertTrue(_supported_numbers('1,320 products [S1]', inputs, 'Count products'))
        self.assertTrue(_supported_numbers('1.320 sản phẩm [S1]', inputs, 'Count products'))
        self.assertFalse(_supported_numbers('1.32 products [S1]', inputs, 'Count products'))
        self.assertFalse(_supported_numbers('1320e6 products [S1]', inputs, 'Count products'))

    def test_numeric_grounding_accepts_exactly_checked_results_with_sourced_operands(self):
        inputs = [{'data': {}, 'evidence': [{'content': 'Mỗi bữa tối đa 300.000 VND.'}]}]
        question = '4 nhân viên ăn một bữa, tối đa bao nhiêu?'
        self.assertTrue(_supported_numbers('4 × 300.000 = 1.200.000 VND [S1].', inputs, question))
        self.assertFalse(_supported_numbers('4 × 300.000 = 1.300.000 VND [S1].', inputs, question))  # wrong result
        self.assertFalse(_supported_numbers('5 × 300.000 = 1.500.000 VND [S1].', inputs, question))  # unsourced operand
        self.assertFalse(_supported_numbers('Tổng 1.200.000 VND [S1].', inputs, question))  # no checked equality

    def test_numeric_grounding_expands_shorthand_and_skips_units_between_operands(self):
        inputs = [{'data': {}, 'evidence': [{'content': 'Đến 5.000.000 VND do quản lý trực tiếp duyệt.'}]}]
        question = 'Báo giá 4.000.000 VND cộng vận chuyển 1.500.000 VND, 3 lô mỗi lô 18 triệu, mua đồ 4tr5'
        self.assertTrue(_supported_numbers('Mỗi lô 18.000.000 VND [S1].', inputs, question))
        self.assertTrue(_supported_numbers('Khoản 4.500.000 VND [S1].', inputs, question))
        self.assertTrue(_supported_numbers('3 × 18.000.000 = 54.000.000 VND [S1].', inputs, question))
        self.assertTrue(_supported_numbers('4.000.000 VND + 1.500.000 VND = 5.500.000 VND [S1].', inputs, question))
        self.assertFalse(_supported_numbers('4.000.000 VND + 1.500.000 VND = 5.600.000 VND [S1].', inputs, question))
        self.assertFalse(_supported_numbers('Mỗi lô 19.000.000 VND [S1].', inputs, question))

    async def test_knowledge_fails_closed_for_missing_or_empty_document_scope(self):
        rag = Mock()
        agent = KnowledgeAgent(rag)
        for identity in [None, VerifiedIdentity(subject='x'),
                         VerifiedIdentity(subject='x', document_roles={'admin'})]:
            with self.subTest(identity=identity), self.assertRaises(PermissionError):
                await agent.run(AgentRequest(question='policy', identity=identity))
        rag.generate_answer.assert_not_called()

    async def test_knowledge_insufficient_context_is_explicit_empty_outcome(self):
        rag = Mock()
        rag.generate_answer.return_value = type('R', (), {'answer': 'No evidence', 'contexts': [],
                                                         'source_ids': [], 'insufficient_context': True, 'verification': None})()
        result = await KnowledgeAgent(rag).run(AgentRequest(question='policy', identity=IDENTITY))
        self.assertFalse(result.metadata['ok'])
        self.assertTrue(result.metadata['insufficient_context'])

    async def test_policy_to_sql_dependency_preserves_cited_threshold(self):
        tasks = [task('k', 'knowledge', 'Policy stockout threshold'),
                 task('s', 'sql', 'Count rows exceeding the cited threshold', depends_on=['k'],
                      inputs=[{'task_id': 'k', 'kind': 'evidence'}])]
        sql = FakeAgent(source_result('analytics', rows=[{'count': 3}]))
        knowledge = FakeAgent(source_result('knowledge', content='Approved reorder threshold: 5 units.'))
        await AgentRouter(None, knowledge, sql, llm=FakeProvider(tasks)).run(
            AgentRequest(question='Count rows above policy threshold', identity=IDENTITY))
        self.assertIn('5 units', sql.requests[0].question)
        self.assertIn('policy.pdf', sql.requests[0].question)

    async def test_failed_dependency_blocks_child_and_unchanged_revision_stops(self):
        tasks = [task('s', 'sql', 'Count orders'), task('k', 'knowledge', 'Policy for returned rows',
                 depends_on=['s'], inputs=[{'task_id': 's', 'kind': 'rows'}])]
        sql, knowledge = FakeAgent(ValueError('unsupported')), FakeAgent(source_result('knowledge'))
        result = await AgentRouter(None, knowledge, sql, llm=FakeProvider(tasks)).run(
            AgentRequest(question='Orders then policy', identity=IDENTITY))
        self.assertEqual(len(sql.requests), 1)
        self.assertFalse(knowledge.requests)
        self.assertIn('blocked', [entry['status'] for entry in result.metadata['task_trace']])

    async def test_invented_numbers_in_synthesis_fall_back_to_actual_evidence(self):
        class Inventing(FakeProvider):
            async def generate(self, prompt):
                if prompt.startswith('You plan'):
                    return await super().generate(prompt)
                return json.dumps({'answer': '999 stockouts [S2]. Approval [S1].', 'used_tasks': ['k', 's']})
        tasks = [task('k', 'knowledge', 'Policy'), task('s', 'sql', 'Stockouts')]
        result = await AgentRouter(None, FakeAgent(source_result('knowledge')),
                                  FakeAgent(source_result('analytics', rows=[{'stockouts': 3}])),
                                  llm=Inventing(tasks)).run(AgentRequest(question='Stockouts and policy', identity=IDENTITY))
        self.assertTrue(result.metadata['fallback'])
        self.assertNotIn('999', result.answer)
        self.assertIn('3', result.answer)
        self.assertIn('[S2]', result.answer)

    async def test_single_knowledge_task_passes_its_verified_answer_through(self):
        verified = source_result('knowledge', content='Employee updates handover arrangements.')
        verified.answer = '1. Update the handover arrangements [S1].\n2. Name the replacement [S1].'
        verified.metadata = {'ok': True, 'claim_verification': {'status': 'supported'}, 'search': {'passages_to_model': 8}}
        result = await AgentRouter(None, FakeAgent(verified), FakeAgent(source_result('analytics', rows=[])),
                                   llm=FakeProvider([task('k', 'knowledge', 'Handover')])).run(
            AgentRequest(question='How do I hand over my work?', identity=IDENTITY))
        self.assertEqual(result.answer, verified.answer)
        self.assertNotIn('fallback', result.metadata)
        self.assertEqual(result.metadata['search'], {'passages_to_model': 8})
        self.assertEqual(result.metadata['selected_route'], 'knowledge')

    async def test_single_knowledge_task_keeps_the_withheld_message_and_reason(self):
        from core.rag.claim_verification import VERIFICATION_UNAVAILABLE_ANSWER
        withheld = AgentResult(answer=VERIFICATION_UNAVAILABLE_ANSWER, agent='knowledge', metadata={
            'ok': False, 'insufficient_context': False,
            'claim_verification': {'status': 'rejected', 'reason': 'contradicted'}})
        result = await AgentRouter(None, FakeAgent(withheld), FakeAgent(source_result('analytics', rows=[])),
                                   llm=FakeProvider([task('k', 'knowledge', 'Hotel limit for 10 days')])).run(
            AgentRequest(question='Hotel and meals for 10 days?', identity=IDENTITY))
        self.assertEqual(result.answer, VERIFICATION_UNAVAILABLE_ANSWER)
        self.assertEqual(result.metadata['claim_verification']['reason'], 'contradicted')
        self.assertFalse(result.metadata['ok'])

    async def test_lone_knowledge_task_gets_the_users_own_question_unless_it_is_a_follow_up(self):
        class Planner(FakeProvider):
            uses_context = None

            async def generate(self, prompt):
                plan = {'objective': 'Handover', 'tasks': [task('k', 'knowledge', 'Search for handover policies')]}
                if self.uses_context is not None:
                    plan['uses_context'] = self.uses_context
                return json.dumps(plan)

        knowledge, planner = FakeAgent(source_result('knowledge')), Planner([])
        router = AgentRouter(None, knowledge, FakeAgent(source_result('analytics', rows=[])), llm=planner)
        ask = lambda question: router.run(AgentRequest(question=question, identity=IDENTITY, conversation_id='c1'))

        await ask('How do I hand over my work?')                 # first turn: no history
        planner.uses_context = False
        await ask('What is the hotel limit per night?')          # later turn, stands alone
        planner.uses_context = True
        await ask('And in a major city?')                        # follow-up: needs the earlier turn
        planner.uses_context = None
        await ask('And for meals?')                              # flag missing: keep the planner's question

        self.assertEqual([request.question for request in knowledge.requests], [
            'How do I hand over my work?', 'What is the hotel limit per night?',
            'Search for handover policies', 'Search for handover policies'])

    async def test_documents_only_plan_with_several_knowledge_tasks_becomes_one_pass_through_task(self):
        tasks = [task('b', 'knowledge', 'Who approves 80 million (Appendix B)?'),
                 task('c', 'knowledge', 'When can a PO be issued (Appendix C)?')]
        verified = source_result('knowledge')
        verified.answer = '1. Department head, Procurement and Finance [S1].\n2. Only after approval [S1].'
        knowledge = FakeAgent(verified)
        question = 'Theo Phụ lục B và C, 80 triệu cần ai duyệt và PO phát hành khi nào?'
        result = await AgentRouter(None, knowledge, FakeAgent(source_result('analytics', rows=[])),
                                   llm=FakeProvider(tasks)).run(AgentRequest(question=question, identity=IDENTITY))
        self.assertEqual([request.question for request in knowledge.requests], [question])
        self.assertEqual(result.answer, verified.answer)
        self.assertNotIn('fallback', result.metadata)

    async def test_knowledge_question_with_predecessor_inputs_is_not_replaced(self):
        tasks = [task('s', 'sql', 'Top category'), task('k', 'knowledge', 'Policy for that category',
                 depends_on=['s'], inputs=[{'task_id': 's', 'kind': 'rows'}])]
        knowledge = FakeAgent(source_result('knowledge'))
        await AgentRouter(None, knowledge, FakeAgent(source_result('analytics', rows=[{'category': 'Shoes'}])),
                          llm=FakeProvider(tasks)).run(AgentRequest(question='Policy for the top category?', identity=IDENTITY))
        self.assertTrue(knowledge.requests[0].question.startswith('Policy for that category'))

    def test_list_numbering_is_not_a_claimed_number_but_amounts_still_are(self):
        inputs = [{'data': {}, 'evidence': [{'content': 'Up to 300.000 VND per meal.'}]}]
        self.assertTrue(_supported_numbers('1. Meals up to 300.000 VND [S1].\n2) Keep receipts [S1].\nBước 3: submit [S1].', inputs, 'q'))
        self.assertFalse(_supported_numbers('1. Meals up to 400.000 VND [S1].', inputs, 'q'))

    async def test_synchronous_worker_slot_lasts_until_thread_exits(self):
        release = threading.Event()
        started = threading.Event()
        def blocking():
            started.set()
            release.wait(2)
            return 'done'
        token = deadline.set(time.monotonic() + 0.03)
        try:
            with self.assertRaises(TimeoutError):
                await run_sync(blocking)
            self.assertTrue(started.is_set())
        finally:
            release.set()
            deadline.reset(token)
        await asyncio.sleep(0.01)
        self.assertEqual(await run_sync(lambda: 'available'), 'available')

    async def test_generated_agent_prose_cannot_validate_an_invented_number(self):
        class Repeating(FakeProvider):
            async def generate(self, prompt):
                if prompt.startswith('You plan'):
                    return await super().generate(prompt)
                return json.dumps({'answer': 'Policy approval [S1]. 999 products [S2].', 'used_tasks': ['k', 's']})
        sql_result = source_result('analytics', rows=[{'count': 3}])
        sql_result.answer = 'There are 999 products [S1].'
        result = await AgentRouter(None, FakeAgent(source_result('knowledge')), FakeAgent(sql_result),
            llm=Repeating([task('k', 'knowledge', 'Policy'), task('s', 'sql', 'Count products')])).run(
                AgentRequest(question='Count products and explain policy', identity=IDENTITY))
        self.assertTrue(result.metadata['fallback'])
        self.assertNotIn('999', result.answer)

    async def test_concurrent_results_do_not_depend_on_shared_destination(self):
        class Selecting(FakeProvider):
            async def generate(self, prompt):
                question = json.loads(prompt.split('DATA:\n')[1].split('\nInvalid')[0])['question']
                return json.dumps({'objective': question, 'tasks': [task('one', 'sql' if question == 'orders' else 'knowledge', question)]})
        router = AgentRouter(None, FakeAgent(source_result('knowledge')),
                             FakeAgent(source_result('analytics', rows=[{'count': 3}])), llm=Selecting([]))
        results = await asyncio.gather(*(router.run(AgentRequest(question=q, identity=IDENTITY)) for q in ['orders', 'policy']))
        self.assertEqual([r.metadata['selected_route'] for r in results], ['analytics', 'knowledge'])
