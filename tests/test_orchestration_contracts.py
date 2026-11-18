import asyncio
import json
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.agents.runtime import deadline, run_sync
from core.agents.decision_support.execution import TaskOutcome
from core.agents.knowledge_agent import KnowledgeAgent
from core.agents.router import AgentRouter
from core.agents.intent_classifier import JEV_ROUTES, classify_jev_route
from core.agents.response import _supported_numbers
from core.models.agent_plan import AgentPlan
from core.models.agents import AgentRequest, AgentResult, Evidence, VerifiedIdentity
from core.prompts.agents import SYNTHESIS_PROMPT
from test_bounded_execution import FakeAgent, FakeProvider, IDENTITY, source_result, task


class OrchestrationContractTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        jev = patch('core.agents.decision_support.router.classify_jev_route',
                    side_effect=RuntimeError('Jev disabled in unit test'))
        jev.start()
        self.addCleanup(jev.stop)

    def test_jev_selects_tools_independently_above_half_probability(self):
        payload = {'model': 'typesafe/jev-1.14', 'answers': {
            'knowledge_required': {'type': 'choice', 'choice': 'yes',
                                   'probabilities': {'yes': 0.72, 'no': 0.28}},
            'sql_required': {'type': 'choice', 'choice': 'no',
                             'probabilities': {'yes': 0.50, 'no': 0.50}},
            'history_required': {'type': 'choice', 'choice': 'no',
                                 'probabilities': {'yes': 0.01, 'no': 0.99}},
        }}
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(payload).encode()
        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}), \
             patch('core.agents.intent_classifier.urllib.request.urlopen', return_value=response) as urlopen:
            decision = classify_jev_route('Doanh thu và chính sách campaign')

        request = urlopen.call_args.args[0]
        sent = json.loads(request.data)
        self.assertEqual(set(sent['questions']), {'knowledge_required', 'sql_required', 'history_required'})
        self.assertIn('which promotion candidate', sent['questions']['knowledge_required']['instructions'])
        self.assertEqual(decision['selected_tools'], ['knowledge'])
        self.assertEqual(decision['route'], 'knowledge')
        self.assertFalse(decision['history_required'])

    def test_synthesis_preserves_exact_numbers_and_does_not_invent_ranks_or_units(self):
        self.assertIn('copy numeric values exactly as supplied, without rounding', SYNTHESIS_PROMPT)
        self.assertIn('Do not assign a currency/unit unless the evidence supplies it', SYNTHESIS_PROMPT)
        self.assertIn('Do not call results top, highest, lowest, or ranked', SYNTHESIS_PROMPT)
        self.assertIn('cite SQL task IDs for query values and Knowledge task IDs for policy/document claims', SYNTHESIS_PROMPT)

    def test_planner_uses_general_model_instead_of_sql_specific_provider(self):
        sql_provider = Mock(name='sql_provider')
        sql = Mock()
        sql._provider.return_value = sql_provider
        planner_provider = Mock(name='planner_provider')

        with patch.dict('os.environ', {'DECISION_PLANNER_LLM_PROVIDER': 'groq'}, clear=False), \
             patch('core.llm.groq_provider.GroqProvider', return_value=planner_provider) as groq:
            router = AgentRouter(None, None, sql)
            self.assertIs(router._provider(), planner_provider)

        groq.assert_called_once_with(model=None)
        sql._provider.assert_not_called()
        self.assertTrue(router._owns_llm)

    def test_auto_planner_uses_cloudflare_when_credentials_are_configured(self):
        planner = Mock(name='planner')
        with patch.dict('os.environ', {
                'DECISION_PLANNER_LLM_PROVIDER': 'auto',
                'CLOUDFLARE_ACCOUNT_ID': 'account',
                'CLOUDFLARE_API_TOKEN': 'token',
                'DECISION_PLANNER_CLOUDFLARE_MODEL': '@cf/openai/gpt-oss-20b'}, clear=False), \
             patch('core.llm.Cloudflare_provider.CloudflareProvider', return_value=planner) as cloudflare:
            router = AgentRouter(None, None, None)
            self.assertIs(router._provider(), planner)

        cloudflare.assert_called_once_with(model='@cf/openai/gpt-oss-20b')

    def test_planner_can_use_authenticated_local_codex_cli(self):
        from core.agents.runtime import CodexCLIProvider

        with patch.dict('os.environ', {'DECISION_PLANNER_LLM_PROVIDER': 'codex_cli'}, clear=False):
            router = AgentRouter(None, None, None)
            provider = router._provider()

        self.assertIsInstance(provider, CodexCLIProvider)
        self.assertTrue(router._owns_llm)

    def test_auto_response_uses_separate_cloudflare_provider_when_configured(self):
        planner = Mock(name='planner')
        response = Mock(name='response')
        with patch.dict('os.environ', {
                'DECISION_RESPONSE_LLM_PROVIDER': 'auto',
                'CLOUDFLARE_ACCOUNT_ID': 'account',
                'CLOUDFLARE_API_TOKEN': 'token',
                'DECISION_RESPONSE_CLOUDFLARE_MODEL': '@cf/openai/gpt-oss-20b'}, clear=False), \
             patch('core.llm.Cloudflare_provider.CloudflareProvider', return_value=response) as cloudflare:
            router = AgentRouter(None, None, None)
            router.llm = planner
            self.assertIs(router._provider(), planner)
            self.assertIs(router._response_provider(), response)

        cloudflare.assert_called_once_with(model='@cf/openai/gpt-oss-20b')
        self.assertTrue(router._owns_response_llm)

    def test_response_can_select_authenticated_local_codex_cli(self):
        with patch.dict('os.environ', {'DECISION_RESPONSE_LLM_PROVIDER': 'codex_cli'}, clear=False):
            router = AgentRouter(None, None, None)
            self.assertEqual(router._response_provider(), 'codex_cli')
        self.assertFalse(router._owns_response_llm)

    def test_explicit_provider_injection_remains_single_model_override(self):
        injected = Mock(name='injected')
        with patch.dict('os.environ', {'DECISION_RESPONSE_LLM_PROVIDER': 'cloudflare'}, clear=False):
            router = AgentRouter(None, None, None, llm=injected)
            self.assertIs(router._response_provider(), injected)
        self.assertFalse(router._owns_response_llm)

    def test_jev_routes_both_tools_to_planner(self):
        payload = {'answers': {
            'knowledge_required': {'type': 'choice', 'choice': 'yes',
                                   'probabilities': {'yes': 0.76, 'no': 0.24}},
            'sql_required': {'type': 'choice', 'choice': 'yes',
                             'probabilities': {'yes': 0.94, 'no': 0.06}},
            'history_required': {'type': 'choice', 'choice': 'no',
                                 'probabilities': {'yes': 0.01, 'no': 0.99}},
        }}
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(payload).encode()
        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}), \
             patch('core.agents.intent_classifier.urllib.request.urlopen', return_value=response):
            decision = classify_jev_route('Which products should we promote?')

        self.assertEqual(decision['selected_tools'], ['knowledge', 'sql'])
        self.assertEqual(decision['route'], 'plan_required')

    async def test_jev_plan_required_route_uses_planner_for_tool_selection(self):
        router = AgentRouter(None, None, None, llm=FakeProvider([]))
        question = 'What should we do with products that have low margin and high inventory?'
        resolved = AgentPlan.model_validate({
            'objective': question,
            'tasks': [
                {'id': 'k', 'agent': 'knowledge', 'question': question},
                {'id': 's', 'agent': 'sql', 'question': question},
            ],
        })
        with patch('core.agents.decision_support.router.classify_jev_route', return_value={
                'route': 'plan_required', 'selected_tools': ['knowledge', 'sql'],
                'confidence': 0.0, 'history_required': False}), \
             patch('core.agents.decision_support.router.plan_request',
                   new=AsyncMock(return_value=resolved)) as plan_request:
            state = await router._plan({
                'request': AgentRequest(question=question, identity=IDENTITY),
                'history': [], 'execution': Mock(), 'report_headings': None,
            })

        self.assertEqual(JEV_ROUTES, {'knowledge', 'sql', 'plan_required'})
        self.assertEqual(state['plan'], resolved)
        plan_request.assert_awaited_once()
        self.assertEqual(plan_request.await_args.kwargs['selected_tools'], ['knowledge', 'sql'])

    async def test_jev_single_tool_route_cannot_drop_business_sql_evidence(self):
        question = 'Doanh nghiệp nên ưu tiên nhập thêm, quảng bá hoặc ngừng bán những sản phẩm nào để cải thiện lợi nhuận?'
        router = AgentRouter(None, None, None, llm=FakeProvider([]))
        resolved = AgentPlan.model_validate({
            'objective': question,
            'tasks': [
                {'id': 'k', 'agent': 'knowledge', 'question': question},
                {'id': 's', 'agent': 'sql', 'question': question},
            ],
        })
        with patch('core.agents.decision_support.router.classify_jev_route', return_value={
                'route': 'knowledge', 'confidence': 0.99, 'history_required': False}), \
             patch('core.agents.decision_support.router.plan_request',
                   new=AsyncMock(return_value=resolved)) as plan_request:
            state = await router._plan({
                'request': AgentRequest(question=question, identity=IDENTITY),
                'history': [], 'execution': Mock(), 'report_headings': None,
            })

        self.assertEqual(state['plan'], resolved)
        plan_request.assert_awaited_once()

    async def test_short_followup_uses_planner_when_jev_misses_history_dependency(self):
        router = AgentRouter(None, None, None, llm=FakeProvider([]))
        request = AgentRequest(question='giờ nên đẩy mạnh vào segment nào nhỉ', identity=IDENTITY)
        resolved = AgentPlan.model_validate({
            'objective': 'Recommend a product segment using the prior quarterly revenue analysis',
            'tasks': [{'id': 's', 'agent': 'sql',
                       'question': 'Compare quarterly product revenue by segment'}],
        })
        with patch('core.agents.decision_support.router.classify_jev_route', return_value={
                'route': 'sql', 'confidence': 0.99, 'history_required': False}), \
             patch('core.agents.decision_support.router.plan_request',
                   new=AsyncMock(return_value=resolved)) as plan_request:
            state = await router._plan({
                'request': request,
                'history': [{'question': 'quarterly revenue by product segment',
                             'scope': 'quarterly product revenue by segment'}],
                'execution': Mock(),
                'report_headings': None,
            })

        self.assertEqual(state['plan'], resolved)
        plan_request.assert_awaited_once()

    async def test_numbered_clarification_reply_restores_scope_and_selected_option(self):
        from core.agents.decision_support.router import _resolve_clarification_choice

        original = 'Trong năm 2026, 5 danh mục nào có doanh thu thuần cao nhất? Hiển thị COGS.'
        clarification = (
            'Bạn muốn tính COGS theo danh mục thế nào?\n\n'
            '1. Tính SUM(products.cogs × quantity)\n'
            '2. Bỏ COGS và gross margin\n'
            '3. Hiển thị COGS toàn công ty riêng'
        )
        clarification_plan = AgentPlan.model_validate({
            'objective': original,
            'tasks': [{'id': 's', 'agent': 'sql', 'question': original}],
        })
        router = AgentRouter(None, None, None, llm=FakeProvider([]))
        original_request = AgentRequest(question=original, identity=IDENTITY,
                                        conversation_id='clarification-session')
        clarification_result = AgentResult(
            answer=clarification, agent='sql',
            metadata={'ok': False, 'status': 'clarification_required'})
        pending = Mock(plan=clarification_plan, outcomes={
            's': TaskOutcome(clarification_plan.tasks[0], 'clarification_required',
                             result=clarification_result)},
            sql_context=None, trace=[], invocations=1)
        initial_state = {
            'result': AgentResult(answer=clarification, agent='agentic',
                metadata={'ok': False, 'status': 'clarification_required'}),
            'plan': clarification_plan,
            'execution': pending,
        }
        with patch('core.agents.decision_support.router.Execution', return_value=pending), \
             patch.object(router.graph, 'ainvoke', new=AsyncMock(return_value=initial_state)):
            await router._run(original_request)

        async with router.conversations.session(original_request) as stored_history:
            history = list(stored_history)
        self.assertEqual(history[0]['clarification_plan'], clarification_plan.model_dump_json())
        self.assertEqual(_resolve_clarification_choice('1', history)[:3],
                         (original, 1, 'Tính SUM(products.cogs × quantity)'))
        option_replies = (
            ('một', 1, 'Tính SUM(products.cogs × quantity)'),
            ('phương án một', 1, 'Tính SUM(products.cogs × quantity)'),
            ('lựa chọn số 1', 1, 'Tính SUM(products.cogs × quantity)'),
            ('one', 1, 'Tính SUM(products.cogs × quantity)'),
            ('hai', 2, 'Bỏ COGS và gross margin'),
            ('phương án hai', 2, 'Bỏ COGS và gross margin'),
            ('lựa chọn số 2', 2, 'Bỏ COGS và gross margin'),
            ('two', 2, 'Bỏ COGS và gross margin'),
            ('ba', 3, 'Hiển thị COGS toàn công ty riêng'),
            ('phương án ba', 3, 'Hiển thị COGS toàn công ty riêng'),
            ('lựa chọn số 3', 3, 'Hiển thị COGS toàn công ty riêng'),
            ('three', 3, 'Hiển thị COGS toàn công ty riêng'),
        )
        for reply, number, option in option_replies:
            with self.subTest(reply=reply):
                self.assertEqual(_resolve_clarification_choice(reply, history)[:3],
                                 (original, number, option))
        self.assertIsNone(_resolve_clarification_choice('4', history))

        request = AgentRequest(question='1', identity=IDENTITY,
                               conversation_id='clarification-session')
        execution = Mock()
        execution.request = request
        with patch('core.agents.decision_support.router.classify_jev_route') as classifier, \
             patch('core.agents.decision_support.router.plan_request',
                   new=AsyncMock()) as planner:
            state = await router._plan({
                'request': request, 'history': history, 'execution': execution,
                'report_headings': None,
            })

        self.assertIn(original, execution.request.question)
        self.assertIn('User clarification choice (1): Tính SUM(products.cogs × quantity)',
                      execution.request.question)
        self.assertEqual(state['plan'].tasks[0].question, execution.request.question)
        self.assertEqual(state['plan'].objective, original)
        self.assertEqual(state['plan'].tasks[0].agent, 'sql')
        self.assertIn(original, state['request'].question)
        classifier.assert_not_called()
        planner.assert_not_awaited()

    async def test_binary_clarification_reply_restores_scope_without_replanning(self):
        original = 'Lấy snapshot tồn kho mới nhất của từng sản phẩm và tính số lượng bán trong 30 ngày trước snapshot.'
        plan = AgentPlan.model_validate({
            'objective': original,
            'tasks': [{'id': 's', 'agent': 'sql', 'question': original}],
        })
        turn = {
            'question': original,
            'scope': original,
            'clarification': 'Bạn muốn dùng snapshot mới nhất của mỗi sản phẩm?\n\n1. Có\n2. Không',
            'clarification_plan': plan.model_dump_json(),
        }
        router = AgentRouter(None, None, None, llm=FakeProvider([]))
        request = AgentRequest(question='có', identity=IDENTITY,
                               conversation_id='binary-clarification-session')
        execution = Mock()
        execution.request = request
        with (
            patch('core.agents.decision_support.router.classify_jev_route') as classifier,
            patch('core.agents.decision_support.router.plan_request',
                  new=AsyncMock()) as planner,
        ):
            state = await router._plan({
                'request': request, 'history': [turn], 'execution': execution,
                'report_headings': None,
            })

        self.assertEqual(state['plan'].objective, original)
        self.assertIn('User clarification choice (1): Có', state['plan'].tasks[0].question)
        self.assertIn(original, state['plan'].tasks[0].question)
        classifier.assert_not_called()
        planner.assert_not_awaited()
        from core.agents.decision_support.router import _resolve_clarification_choice
        self.assertEqual(_resolve_clarification_choice('không', [turn])[:3],
                         (original, 2, 'Không'))

    async def test_sql_outage_fallback_still_uses_auto_response_layer(self):
        question = 'doanh thu năm 2025'
        router = AgentRouter(None, None, FakeAgent(source_result('analytics', rows=[{'revenue': 123}])),
                             llm=FakeProvider([]))

        result = await router.run(AgentRequest(question=question, identity=IDENTITY))

        self.assertTrue(result.metadata['planning_fallback'])
        self.assertIn('Doanh thu: 123', result.answer)
        self.assertNotEqual(result.answer, 'Supported observation [S1].')

    def test_numeric_grounding_accepts_localized_thousands_but_not_new_magnitudes(self):
        inputs = [{'data': {'rows': [{'count': 1320}]}, 'evidence': []}]
        self.assertTrue(_supported_numbers('1,320 products [S1]', inputs, 'Count products'))
        self.assertTrue(_supported_numbers('1.320 sản phẩm [S1]', inputs, 'Count products'))
        revenue_inputs = [{'data': {'rows': [
            {'year': '2025-01-01T00:00:00+00:00', 'revenue': '3369646.71'},
            {'year': '2026-01-01T00:00:00+00:00', 'revenue': '18881151.90'},
        ]}, 'evidence': []}]
        self.assertTrue(_supported_numbers(
            'Doanh thu năm 2025 là 3 369 646,71 và năm 2026 là 18 881 151,90 [S1].',
            revenue_inputs, 'so sánh 2 năm'))
        self.assertFalse(_supported_numbers(
            'Doanh thu năm 2025 là 3 369 646,72 và năm 2026 là 18 881 151,90 [S1].',
            revenue_inputs, 'so sánh 2 năm'))
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
                                                         'source_ids': [], 'insufficient_context': True, 'verification': None, 'withheld_draft': None})()
        result = await KnowledgeAgent(rag).run(AgentRequest(question='policy', identity=IDENTITY))
        self.assertFalse(result.metadata['ok'])
        self.assertTrue(result.metadata['insufficient_context'])

    async def test_metric_definition_retrieval_is_role_scoped_and_never_approves_rag_text(self):
        rag = Mock()
        rag.retrieve_contexts.return_value = [{'content': 'Candidate metric guidance'}]
        agent = KnowledgeAgent(rag)
        result = await agent.retrieve_metric_definition(
            AgentRequest(question='Revenue and stockout association', identity=IDENTITY),
            'Revenue and stockout association',
        )
        self.assertEqual(result, [{'content': 'Candidate metric guidance'}])
        args, kwargs = rag.retrieve_contexts.call_args
        self.assertIn('formula, grain, source tables', args[0])
        self.assertEqual(kwargs['roles'], ['admin'])
        self.assertEqual(kwargs['limit'], 5)

        unauthorized = AgentRequest(question='Revenue metric', identity=VerifiedIdentity(
            subject='analyst', permissions={'analytics:read'}))
        with self.assertRaises(PermissionError):
            await agent.retrieve_metric_definition(unauthorized, 'Revenue metric')
        self.assertEqual(rag.retrieve_contexts.call_count, 1)

    async def test_policy_to_sql_dependency_preserves_cited_threshold(self):
        tasks = [task('k', 'knowledge', 'Policy stockout threshold'),
                 task('s', 'sql', 'Count rows exceeding the cited threshold', depends_on=['k'],
                      inputs=[{'task_id': 'k', 'kind': 'evidence', 'field': 'thresholds'}])]
        sql = FakeAgent(source_result('analytics', rows=[{'count': 3}]))
        knowledge = FakeAgent(source_result('knowledge', content='Approved reorder threshold: 5 units.'))
        await AgentRouter(None, knowledge, sql, llm=FakeProvider(tasks)).run(
            AgentRequest(question='Count rows above policy threshold', identity=IDENTITY))
        self.assertEqual(sql.requests[0].question, 'Count rows exceeding the cited threshold')
        self.assertIn('5 units', sql.requests[0].metadata['_predecessor_evidence'])
        self.assertIn('policy.pdf', sql.requests[0].metadata['_predecessor_evidence'])

    async def test_policy_handoff_does_not_duplicate_long_evidence_content(self):
        content = 'Approved reorder threshold: 5 units. ' + ('Policy detail. ' * 500)
        tasks = [task('k', 'knowledge', 'Policy stockout threshold'),
                 task('s', 'sql', 'Count rows exceeding the cited threshold', depends_on=['k'],
                      inputs=[{'task_id': 'k', 'kind': 'evidence'}])]
        sql = FakeAgent(source_result('analytics', rows=[{'count': 3}]))
        knowledge = FakeAgent(source_result('knowledge', content=content))

        await AgentRouter(None, knowledge, sql, llm=FakeProvider(tasks)).run(
            AgentRequest(question='Count rows above policy threshold', identity=IDENTITY))

        handoff = sql.requests[0].metadata['_predecessor_evidence']
        self.assertIn('5 units', handoff)
        self.assertIn('policy.pdf', handoff)
        self.assertEqual(handoff.count('Policy detail.'), 500)

    async def test_large_policy_evidence_is_bounded_without_losing_knowledge_summary(self):
        knowledge_result = source_result('knowledge', content='Inventory policy. ' * 2_000)
        knowledge_result.answer = 'Review stock above the policy threshold of 120 days [S1].'
        knowledge_result.evidence = [
            Evidence(citation_id=f'S{i}', source_type='document', source=f'policy-{i}.pdf',
                     content='Policy detail. ' * 2_000)
            for i in range(1, 6)
        ]
        tasks = [task('k', 'knowledge', 'Inventory policy'),
                 task('s', 'sql', 'Find overstock products', depends_on=['k'],
                      inputs=[{'task_id': 'k', 'kind': 'evidence', 'field': 'thresholds'}])]
        sql = FakeAgent(source_result('analytics', rows=[{'product_id': 7}]))

        await AgentRouter(None, FakeAgent(knowledge_result), sql, llm=FakeProvider(tasks)).run(
            AgentRequest(question='Find overstock products using the policy threshold', identity=IDENTITY))

        handoff = sql.requests[0].metadata['_predecessor_evidence']
        self.assertIn('120 days', handoff)
        self.assertIn('policy-1.pdf', handoff)
        self.assertIn('excerpt shortened', handoff)
        self.assertLess(len(handoff), 12_000)

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





    async def test_knowledge_question_with_predecessor_inputs_is_not_replaced(self):
        tasks = [task('s', 'sql', 'Top category'), task('k', 'knowledge', 'Policy for that category',
                 depends_on=['s'], inputs=[{'task_id': 's', 'kind': 'rows'}])]
        knowledge = FakeAgent(source_result('knowledge'))
        await AgentRouter(None, knowledge, FakeAgent(source_result('analytics', rows=[{'category': 'Shoes'}])),
                          llm=FakeProvider(tasks)).run(AgentRequest(question='Policy for the top category?', identity=IDENTITY))
        self.assertTrue(knowledge.requests[0].question.startswith('Policy for that category'))

    async def test_lone_knowledge_task_gets_the_users_own_question_but_followups_keep_the_rewrite(self):
        question = 'nghi phep 3 ngay thi bao truoc bao lau'
        rewrite = 'How many days before the deadline should the report be submitted?'
        knowledge = FakeAgent(source_result('knowledge'))
        router = AgentRouter(None, knowledge, FakeAgent(source_result('analytics')),
                             llm=FakeProvider([task('k', 'knowledge', rewrite)]))
        request = AgentRequest(question=question, identity=IDENTITY, conversation_id='c1')
        await router.run(request)
        self.assertEqual(knowledge.requests[0].question, question)
        # The second turn has history, so the planner's resolved follow-up is what Knowledge needs.
        await router.run(request.model_copy(update={'question': 'thế còn nghỉ 5 ngày?'}))
        self.assertEqual(knowledge.requests[1].question, rewrite)

    async def test_claim_checked_knowledge_answer_passes_through_with_its_seal(self):
        checked = {'status': 'supported', 'claim_count': 1}
        verified = AgentResult(
            answer='Cần báo trước ít nhất 5 ngày làm việc [S1].', agent='knowledge',
            evidence=[Evidence(citation_id='S1', source_type='document', source='policy.pdf',
                               content='Nghỉ theo kế hoạch nên được đề nghị ít nhất năm ngày làm việc trước ngày đầu nghỉ.')],
            metadata={'ok': True, 'insufficient_context': False, 'claim_verification': checked})
        result = await AgentRouter(None, FakeAgent(verified), None, llm=FakeProvider([task('k', 'knowledge', 'leave notice')])).run(
            AgentRequest(question='nghi phep 3 ngay thi bao truoc bao lau', identity=IDENTITY))
        self.assertIn('5 ngày làm việc', result.answer)  # the source spells it 'năm'; the claim check already passed
        self.assertFalse(result.metadata['fallback'])
        self.assertEqual(result.metadata['claim_verification'], checked)

        unchecked = verified.model_copy(update={'metadata': {'ok': True}})
        result = await AgentRouter(None, FakeAgent(unchecked), None, llm=FakeProvider([task('k', 'knowledge', 'leave notice')])).run(
            AgentRequest(question='nghi phep 3 ngay thi bao truoc bao lau', identity=IDENTITY))
        self.assertTrue(result.metadata['fallback'])  # without a claim check the number guard still applies

    async def test_knowledge_not_covered_is_its_own_answer_not_a_failure(self):
        not_covered = AgentResult(answer='Thông tin trong các tài liệu được phép truy cập chưa đủ để trả lời câu hỏi này.',
                                  agent='knowledge', metadata={'ok': False, 'insufficient_context': True})
        result = await AgentRouter(None, FakeAgent(not_covered), None, llm=FakeProvider([task('k', 'knowledge', 'laptop')])).run(
            AgentRequest(question='tui nghỉ việc thì phải trả lại laptop ko', identity=IDENTITY))
        self.assertEqual(result.answer, not_covered.answer)
        self.assertTrue(result.metadata['insufficient_context'])
        self.assertNotIn('No supported answer', result.answer)

        withheld = AgentResult(answer='Chưa thể kiểm chứng đầy đủ câu trả lời với các nguồn được trích dẫn.', agent='knowledge',
                               metadata={'ok': False, 'insufficient_context': False,
                                         'claim_verification': {'status': 'unavailable', 'reason': 'ValidationError'}})
        result = await AgentRouter(None, FakeAgent(withheld), None, llm=FakeProvider([task('k', 'knowledge', 'desk')])).run(
            AgentRequest(question='bàn ghế mua 3tr thì đưa ai duyệt', identity=IDENTITY))
        self.assertEqual(result.answer, withheld.answer)
        self.assertEqual(result.metadata['claim_verification']['status'], 'unavailable')
        self.assertNotIn('task k', result.answer)


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

    async def test_auto_followup_context_keeps_confirmed_sql_metrics(self):
        sql_result = source_result('analytics', rows=[{'revenue': 18_881_151.9}])
        sql_result.data['query_status'] = 'executed'
        sql_result.metadata['metrics'] = {'revenue': {'formula': 'SUM(revenue)'}}
        sql = FakeAgent(sql_result)

        class FollowupProvider(FakeProvider):
            def __init__(self):
                super().__init__([task('s', 'sql', 'Compare revenue for this year and last year')])
                self.followup_data = None

            async def generate(self, prompt):
                if prompt.startswith('You plan'):
                    self.prompts.append(prompt)
                    self.followup_data = json.loads(prompt.split('DATA:\n', 1)[1].split('\n\nInvalid', 1)[0])
                    return json.dumps({'objective': 'Compare revenue for this year and last year',
                                       'tasks': self.tasks})
                return json.dumps({'answer': 'Doanh thu được truy vấn thành công [S1].',
                                   'used_tasks': ['s']})

        provider = FollowupProvider()
        router = AgentRouter(None, None, sql, llm=provider)
        first = AgentRequest(question='doanh thu năm nay', conversation_id='revenue-followup', identity=IDENTITY)
        await router.run(first)
        result = await router.run(first.model_copy(update={'question': 'so với năm ngoái'}))

        self.assertEqual(provider.followup_data['follow_up_context']['prior_resolved_scope'], 'doanh thu năm nay')
        self.assertEqual(provider.followup_data['follow_up_context']['prior_confirmed_sql_metrics'], 'revenue')
        self.assertEqual(sql.requests[-1].question, 'Compare revenue for this year and last year')
        self.assertEqual(result.metadata['status'], 'complete')

    async def test_concurrent_results_do_not_depend_on_shared_destination(self):
        class Selecting(FakeProvider):
            async def generate(self, prompt):
                question = json.loads(prompt.split('DATA:\n')[1].split('\nInvalid')[0])['question']
                return json.dumps({'objective': question, 'tasks': [task('one', 'sql' if question == 'orders' else 'knowledge', question)]})
        router = AgentRouter(None, FakeAgent(source_result('knowledge')),
                             FakeAgent(source_result('analytics', rows=[{'count': 3}])), llm=Selecting([]))
        results = await asyncio.gather(*(router.run(AgentRequest(question=q, identity=IDENTITY)) for q in ['orders', 'policy']))
        self.assertEqual([r.metadata['selected_route'] for r in results], ['analytics', 'knowledge'])
