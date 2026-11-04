import asyncio
import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import patch

from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.agents.report_agent import ReportAgent
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.models.agents import AgentRequest, VerifiedIdentity
from core.reports.generation import validate_narrative
from core.reports.facts import facts_from_rows
from core.reports.planning import ReportTask


def plan():
    return {'purpose': 'Stock report', 'tasks': [{
        'id': 'stock', 'question': 'stock on hand latest snapshot by category',
        'mapping': {'metrics': ['stock_on_hand'], 'dimensions': ['category'], 'time': {'mode': 'latest'}},
    }], 'sections': [{'heading': 'Category stock', 'tasks': ['stock']}]}


class Writer:
    def __init__(self, specification=None, fail=False):
        self.specification = specification or plan()
        self.fail = fail

    async def generate(self, prompt):
        if prompt.startswith('Plan a data-grounded'):
            return json.dumps(self.specification)
        if self.fail:
            raise ConnectionError('private provider error')
        heading = json.loads(prompt.split('\nHeading: ')[1].splitlines()[0])
        fact = json.loads(prompt.split('\nFacts: ')[1].splitlines()[0])[0]
        return json.dumps({'sections': {heading: f"[{fact['id']}] [{fact['evidence_id']}]"}, 'claims': [fact]})


def request(question='Report stock on hand latest snapshot by category'):
    return AgentRequest(question=question, identity=VerifiedIdentity(
        subject='analyst', permissions={'analytics:read', 'documents:read'}, document_roles={'employee'}))


class InventoryReportTest(unittest.IsolatedAsyncioTestCase):
    async def test_planning_rate_limit_is_actionable_and_does_not_retry_or_query(self):
        from openai import RateLimitError
        import httpx
        error = RateLimitError('private diagnostic text', response=httpx.Response(429,
            request=httpx.Request('POST', 'https://provider.test')), body={'code': 'rate_limit_exceeded'})
        agent, repository = self.agent()
        agent.llm.generate = AsyncMock(side_effect=error)
        result, payload, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertEqual(result.metadata['error_code'], 'provider_rate_limited')
        self.assertIn('rate limit', result.answer.lower())
        self.assertNotIn('private diagnostic', result.answer)
        self.assertEqual(payload, b'')
        self.assertEqual(agent.llm.generate.await_count, 1)
        repository.execute_approved_query.assert_not_awaited()

    async def test_transient_planning_failure_retries_once(self):
        agent, _ = self.agent()
        original = agent.llm.generate
        attempts = 0
        async def flaky(prompt):
            nonlocal attempts
            if prompt.startswith('Plan a data-grounded'):
                attempts += 1
                if attempts == 1:
                    raise ConnectionError('private connection details')
            return await original(prompt)
        agent.llm.generate = flaky
        result, _, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertEqual(attempts, 2)

    async def test_invalid_planning_output_is_repaired_once(self):
        agent, _ = self.agent()
        original = agent.llm.generate
        attempts = 0
        async def malformed_once(prompt):
            nonlocal attempts
            if prompt.startswith('Plan a data-grounded'):
                attempts += 1
                if attempts == 1:
                    return '{truncated'
            return await original(prompt)
        agent.llm.generate = malformed_once
        result, _, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertEqual(attempts, 2)

    async def test_provider_configuration_failure_is_not_user_clarification(self):
        agent, repository = self.agent()
        agent.llm.generate = AsyncMock(side_effect=ValueError('private credential configuration'))
        result, payload, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertEqual(result.metadata['error_code'], 'provider_configuration_error')
        self.assertNotIn('private credential', result.answer)
        self.assertNotIn('clarification_required', result.metadata)
        repository.execute_approved_query.assert_not_awaited()

    async def test_lowest_stock_vietnamese_request_has_valid_dated_product_ranking(self):
        question = 'Liệt kê 10 sản phẩm có tồn kho thấp nhất tại snapshot 2022-12-31, kèm mã sản phẩm và category.'
        spec = plan()
        spec['tasks'][0].update(question=question, mapping={'metrics': ['stock_on_hand'],
            'dimensions': ['product_id', 'category'], 'representation': 'product',
            'time': {'mode': 'snapshot', 'start': '2022-12-31'},
            'ranking': {'metric': 'stock_on_hand', 'direction': 'asc', 'limit': 10}})
        spec['tasks'][0]['mapping']['time']['end'] = '2022-12-31'
        agent, repository = self.agent([{'snapshot_date': '2022-12-31', 'product_id': 1, 'category': 'A', 'stock_on_hand': 0}], spec)
        agent.llm.generate = AsyncMock(wraps=agent.llm.generate)
        result, payload, _ = await agent.generate_from_template(request(question), source_mode='orchestrated')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertIn('LIMIT 10', repository.execute_approved_query.await_args.args[0])
        self.assertEqual(agent.llm.generate.await_count, 1)
        self.assertEqual(result.metadata['narrative_coverage']['Category stock']['mode'], 'deterministic_listing')

    async def test_return_rate_requests_explain_outside_inventory_scope(self):
        questions = [
            'Tạo executive brief tổng hợp tỉ lệ trả hàng của từng category trong năm 2022.',
            'Tạo báo cáo tỷ lệ trả hàng theo category trong năm 2022.',
            'Create an executive brief of return rate by product category in 2022.',
        ]
        for question in questions:
            for mode in ('analytics', 'orchestrated', 'combined'):
                with self.subTest(question=question, mode=mode):
                    agent, repository = self.agent()
                    agent.llm.generate = AsyncMock(return_value=json.dumps({'purpose': 'Return rate',
                        'tasks': [{'id': 'returns', 'question': question}],
                        'sections': [{'heading': 'Return rate', 'tasks': ['returns'], 'table_columns': ['return_rate']}]}))
                    agent.analytics_agent.llm = type('SQLProvider', (), {})()
                    agent.analytics_agent.llm.generate = AsyncMock(return_value=json.dumps({
                        'clarification': 'Should the rate count orders with returns or returned units?'}))
                    result, payload, _ = await agent.generate_from_template(request(question), source_mode=mode,
                        accept_supported_scope=True, template_choice='uploaded')
                    self.assertEqual(result.metadata['status'], 'unsupported')
                    self.assertEqual(payload, b'')
                    repository.execute_approved_query.assert_not_awaited()
                    agent.llm.generate.assert_awaited_once()
                    agent.analytics_agent.llm.generate.assert_not_awaited()
                    self.assertNotIn('commerce.order_items', result.answer)
                    self.assertNotIn('join', result.answer.casefold())

    async def test_empty_requested_snapshot_is_not_a_temporary_outage(self):
        agent, _ = self.agent([])
        result, payload, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertEqual(result.metadata['failure_type'], 'no_observations')
        self.assertEqual(payload, b'')

    async def test_entirely_unsupported_request_never_queries_data(self):
        spec = {'purpose': 'Safety stock', 'unsupported_requirements': ['No approved safety stock model']}
        agent, repository = self.agent(specification=spec)
        result, payload, _ = await agent.generate_from_template(request('Safety stock report'), source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'unsupported')
        self.assertEqual(payload, b'')
        repository.execute_approved_query.assert_not_awaited()

    async def test_master_product_count_uses_full_database_aggregate(self):
        spec = {'purpose': 'Master product count', 'tasks': [{'id': 'catalog', 'question': 'Count master product records',
            'product_columns': ['product_count']}], 'sections': [{'heading': 'Product count', 'tasks': ['catalog']}]}
        agent, repository = self.agent([{'product_count': 5000}], spec)
        result, payload, _ = await agent.generate_from_template(request('Count master product records'), source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertIn('COUNT(', repository.execute_approved_query.await_args.args[0])
        self.assertIn(b'5000 [F1]', payload)

    async def test_transient_query_failure_is_retried_without_repeating_successful_queries(self):
        agent, repository = self.agent()
        repository.execute_approved_query.side_effect = [ConnectionError(), [
            {'snapshot_date': '2022-01-31', 'category': 'A', 'stock_on_hand': 10}]]
        result, _, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertEqual(repository.execute_approved_query.await_count, 2)

    async def test_historical_comparison_and_missing_snapshot_disclosure(self):
        spec = plan(); spec['compare_periods'] = True
        task = spec['tasks'][0]
        task['question'] = 'stock on hand snapshots 2022-01-31 through 2022-02-28 by category'
        task['mapping']['time'] = {'mode': 'range', 'start': '2022-01-31', 'end': '2022-02-28'}
        rows = [{'snapshot_date': '2022-01-31', 'category': 'A', 'stock_on_hand': 10},
                {'snapshot_date': '2022-02-28', 'category': 'A', 'stock_on_hand': 15}]
        query = request('Compare stock on hand 2022-01-31 through 2022-02-28 by category')
        agent, _ = self.agent(rows, spec)
        result, payload, _ = await agent.generate_from_template(query, source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertEqual(result.metadata['facts'][-1]['operands'], ['F1', 'F2'])
        self.assertIn(b'50%', payload)
        agent, _ = self.agent(rows[:1], spec)
        result, payload, _ = await agent.generate_from_template(query, source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'partial')
        self.assertIn(b'absent snapshots are not zero', payload)

    async def test_flag_exception_report_uses_recorded_flag_without_invented_threshold(self):
        spec = {'purpose': 'Recorded exceptions', 'tasks': [{'id': 'flags',
            'question': 'stored stockout indicator latest snapshot for products',
            'mapping': {'metrics': ['stockout_indicator'], 'dimensions': ['product_id', 'product_name'],
                'representation': 'product', 'filters': [{'field': 'stockout_indicator', 'operator': 'eq', 'value': True}],
                'time': {'mode': 'latest'}}}],
            'sections': [{'heading': 'Recorded exceptions', 'tasks': ['flags']}]}
        rows = [{'snapshot_date': '2022-01-31', 'product_id': 1, 'product_name': 'A', 'stockout_indicator': True}]
        agent, _ = self.agent(rows, spec)
        result, payload, _ = await agent.generate_from_template(request('Report recorded stockout indicators latest snapshot'), source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertIn(b'true [F1]', payload)

    async def test_independent_queries_overlap_with_at_most_two_in_flight(self):
        spec = plan()
        for dimension in ('segment', 'product_id'):
            spec['tasks'].append({'id': dimension, 'question': 'stock on hand latest snapshot by '+dimension,
                'mapping': {'metrics': ['stock_on_hand'], 'dimensions': [dimension], 'time': {'mode': 'latest'}}})
            spec['sections'].append({'heading': dimension, 'tasks': [dimension]})
        agent, repository = self.agent(specification=spec)
        active = peak = 0
        both_running = asyncio.Event()
        async def query(*args):
            nonlocal active, peak
            active += 1; peak = max(peak, active)
            if active == 2: both_running.set()
            await asyncio.wait_for(both_running.wait(), 1)
            active -= 1
            return [{'snapshot_date': '2022-01-31', 'category': 'A', 'segment': 'B', 'product_id': 1, 'stock_on_hand': 10}]
        repository.execute_approved_query.side_effect = query
        result, _, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertEqual(peak, 2)
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertEqual(list(result.metadata['sections']), ['Category stock', 'segment', 'product_id'])

    async def test_expired_budget_delivers_completed_facts_without_more_provider_calls(self):
        agent, _ = self.agent()
        from core.reports.generation import collect_tasks
        async def expire_after_query(*args):
            rows = await collect_tasks(*args)
            from core.agents.runtime import deadline
            import time
            deadline.set(time.monotonic()-1)
            return rows
        with patch('core.reports.generation.collect_tasks', side_effect=expire_after_query):
            result, payload, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'partial')
        self.assertIn(b'10 [F1]', payload)

    def agent(self, rows=None, specification=None, fail=False):
        repository = type('Repository', (), {})()
        repository.execute_approved_query = AsyncMock(return_value=rows if rows is not None else [
            {'snapshot_date': '2022-01-31', 'category': 'A', 'stock_on_hand': 10}])
        return ReportAgent(AsyncMock(), SQLAnalyticsAgent(repository), llm=Writer(specification, fail)), repository

    async def test_data_aware_structure_and_fact_table_for_both_formats(self):
        for format in ('markdown', 'docx'):
            agent, repository = self.agent()
            result, payload, _ = await agent.generate_from_template(request(), source_mode='analytics', output_format=format)
            self.assertEqual(result.metadata['status'], 'complete')
            self.assertEqual(result.metadata['facts'][0]['metric'], 'stock_on_hand')
            if format == 'docx':
                rendered = Document(BytesIO(payload))
                self.assertEqual(rendered.paragraphs[0].text, 'Category stock')
                self.assertIn('10 [F1]', rendered.tables[0].rows[1].cells[2].text)
            else:
                self.assertIn(b'# Category stock', payload)
                self.assertIn(b'10 [F1] [S1]', payload)
            self.assertEqual(repository.execute_approved_query.await_count, 1)

    async def test_combined_confirmation_before_database_access(self):
        spec = plan(); spec['unsupported_requirements'] = ['Supplier lead time is unavailable']
        spec['template_mismatches'] = ['Sales template cannot express the requested inventory category findings']
        agent, repository = self.agent(specification=spec)
        result, payload, _ = await agent.generate_from_template(
            request(), 'a.md', b'# Sales', source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'confirmation_required')
        self.assertTrue(result.metadata['template_decision_required'])
        self.assertTrue(result.metadata['scope_decision_required'])
        self.assertEqual(payload, b'')
        repository.execute_approved_query.assert_not_awaited()
        result, payload, _ = await agent.generate_from_template(
            request(), 'a.md', b'# Sales', source_mode='analytics', template_choice='suggested', accept_supported_scope=True)
        self.assertEqual(result.metadata['status'], 'partial')
        self.assertIn(b'Category stock', payload)

    async def test_narrative_template_is_not_rejected_for_stylistic_differences(self):
        agent, _ = self.agent()
        result, payload, _ = await agent.generate_from_template(request(), 'a.md', b'# Summary', source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertIn(b'# Summary', payload)

    async def test_narrative_sections_overlap_without_exceeding_two(self):
        spec = plan(); spec['sections'].append({'heading': 'Overview', 'tasks': ['stock']})
        agent, _ = self.agent(specification=spec)
        active = peak = 0
        both_running = asyncio.Event()
        original = agent.llm.generate
        async def generate(prompt):
            nonlocal active, peak
            if prompt.startswith('Plan a data-grounded'):
                return await original(prompt)
            active += 1; peak = max(peak, active)
            if active == 2: both_running.set()
            await asyncio.wait_for(both_running.wait(), 1)
            result = await original(prompt)
            active -= 1
            return result
        agent.llm.generate = generate
        result, _, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertEqual(peak, 2)

    async def test_failed_writer_keeps_verified_tables(self):
        agent, _ = self.agent(fail=True)
        result, payload, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'partial')
        self.assertIn(b'10 [F1]', payload)
        self.assertNotIn(b'private provider error', payload)

    async def test_150_rows_are_not_cut_to_100(self):
        rows = [{'snapshot_date': '2022-01-31', 'category': str(i), 'stock_on_hand': i} for i in range(150)]
        agent, _ = self.agent(rows)
        result, payload, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertEqual(result.metadata['coverage']['stock']['included'], 150)
        self.assertIn(b'149 [F150]', payload)

    async def test_200_row_completeness_is_unknown(self):
        rows = [{'snapshot_date': '2022-01-31', 'category': str(i), 'stock_on_hand': i} for i in range(200)]
        for ranking in [None,{'metric':'stock_on_hand','direction':'desc','limit':None}]:
            spec=plan()
            spec['tasks'][0]['mapping']['ranking']=ranking
            agent, _ = self.agent(rows,specification=spec)
            result, _, _ = await agent.generate_from_template(request(), source_mode='analytics')
            self.assertEqual(result.metadata['status'], 'partial')
            self.assertEqual(result.metadata['coverage']['stock']['completeness'], 'unknown_at_row_limit')

    async def test_reused_task_does_not_repeat_query(self):
        spec = plan(); spec['sections'].append({'heading': 'Summary', 'tasks': ['stock']})
        agent, repository = self.agent(specification=spec)
        result, _, _ = await agent.generate_from_template(request(), source_mode='analytics')
        self.assertEqual(result.metadata['status'], 'complete')
        self.assertEqual(repository.execute_approved_query.await_count, 1)

    async def test_wrong_snapshot_and_forged_narrative_are_rejected(self):
        task = ReportTask.model_validate(plan()['tasks'][0])
        task.mapping.time.mode = 'snapshot'; task.mapping.time.start = '2022-02-28'
        with self.assertRaises(ValueError):
            facts_from_rows(task, [{'snapshot_date': '2022-01-31', 'category': 'A', 'stock_on_hand': 10}], 'S1')
        task.mapping.time.mode = 'latest'; task.mapping.time.start = None
        facts = facts_from_rows(task, [{'snapshot_date': '2022-01-31', 'category': 'A', 'stock_on_hand': 10}], 'S1')
        forged = facts[0].model_dump(); forged['dimensions'] = {'category': 'B'}
        with self.assertRaises(ValueError):
            validate_narrative({'sections': {'Summary': 'B has 10 [F1] [S1]'}, 'claims': [forged]}, 'Summary', facts, [])

    async def test_permissions_rechecked_on_confirmation(self):
        agent, repository = self.agent()
        with self.assertRaises(PermissionError):
            await agent.generate_from_template(request().model_copy(update={'identity': None}),
                source_mode='analytics', accept_supported_scope=True, template_choice='uploaded')
        repository.execute_approved_query.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
