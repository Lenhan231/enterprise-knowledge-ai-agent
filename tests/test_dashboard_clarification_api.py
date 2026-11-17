import tempfile
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dashboards import router, get_store, get_conversations, principal
from core.agents.conversation_context import ConversationStore
from core.dashboards.models import QueryResult
from core.dashboards.store import DashboardStore
from test_dashboard_documents import document


class DashboardClarificationApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = DashboardStore(self.temp.name)
        self.user = {'sub': 'alice', 'role': 'admin'}
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_store] = lambda: self.store
        self.app.dependency_overrides[principal] = lambda: self.user
        self.time = [0.0]
        self.conversations = ConversationStore(max_turns=1, max_chars=40_000, clock=lambda: self.time[0])
        self.app.dependency_overrides[get_conversations] = lambda: self.conversations
        self.client = TestClient(self.app)
        self.question = 'Would you like the monthly trend or the overall total?'
        self.sql = SimpleNamespace(_provider=Mock(side_effect=AssertionError('No extra dashboard model')),
            run_payload=AsyncMock(return_value={'ok': False, 'query_status': 'clarification_required', 'answer': self.question}))
        self.runtime = patch('app.dashboards._get_runtime', AsyncMock(return_value=SimpleNamespace(
            analytics_agent=SimpleNamespace(sql_agent=self.sql))))
        self.runtime.start()
        self.addCleanup(self.runtime.stop)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def start(self):
        return self.client.post('/api/dashboards', json={
            'description': 'Web traffic dashboard with total sessions and monthly session trends in 2026',
            'scope': 'January through December 2026'})

    def complete(self):
        self.sql.run_payload.return_value = {'ok': True, 'query_status': 'executed',
            'sql': "SELECT DATE_TRUNC('month', w.date) AS month, SUM(w.sessions) AS sessions FROM commerce.web_traffic w GROUP BY 1 LIMIT 200",
            'rows': [{'month': '2026-01-01', 'sessions': 10}, {'month': '2026-02-01', 'sessions': 20}]}

    def test_partial_bundle_saves_and_reopens_success_and_failure(self):
        self.complete()
        success = self.sql.run_payload.return_value
        self.sql.run_payload.return_value = {'datasets': [
            {'question': 'Total sessions', 'payload': {'ok': False, 'query_status': 'error',
                'answer': 'Source query could not complete.', 'attempted_sql': 'SELECT SUM(sessions) FROM commerce.web_traffic LIMIT 1'}},
            {'question': 'Monthly sessions', 'payload': success}]}
        response = self.start()
        self.assertEqual(201, response.status_code, response.text)
        doc = response.json()['dashboard']
        self.assertEqual('partial', doc['status'])
        self.assertEqual(['failed', 'complete'], [result['status'] for result in doc['results']])
        self.assertEqual(['q0', 'q1'], [tile['query_id'] for tile in doc['tiles']])
        reopened = self.client.get('/api/dashboards/' + doc['id'])
        self.assertEqual(200, reopened.status_code)
        self.assertEqual(doc, reopened.json()['dashboard'])
        self.assertEqual(1, len(self.store.list('alice')))

    def test_completed_sql_with_incompatible_chart_asks_before_save_then_accepts_table(self):
        self.sql.run_payload.return_value = {'ok': True, 'query_status': 'executed',
            'sql': "SELECT DATE_TRUNC('month', w.date) AS month, SUM(w.sessions) AS sessions, SUM(w.page_views) AS page_views, SUM(w.unique_visitors) AS visitors, AVG(w.bounce_rate) AS bounce_rate, AVG(w.avg_session_duration_sec) AS duration FROM commerce.web_traffic w GROUP BY 1 LIMIT 200",
            'rows': [{'month': '2026-01-01', 'sessions': 10, 'page_views': 20, 'visitors': 7, 'bounce_rate': 0.2, 'duration': 30},
                     {'month': '2026-02-01', 'sessions': 15, 'page_views': 30, 'visitors': 9, 'bounce_rate': 0.3, 'duration': 40}]}
        pending = self.client.post('/api/dashboards', json={
            'description': 'Generate a line chart of monthly traffic performance', 'scope': '2026'}).json()
        self.assertEqual('clarification_required', pending.get('status'), pending)
        self.assertIn('SQL completed', pending['message'])
        self.assertIn('table', pending['message'].lower())
        self.assertIn('four', pending['message'])
        self.assertIn('Supported with these results: table.', pending['message'])
        self.assertNotIn('dashboard', pending)
        self.assertEqual([], self.store.list('alice'))
        response = self.client.post('/api/dashboards', json={
            'description': 'Use a table instead', 'conversation_id': pending['conversation_id']})
        self.assertEqual(201, response.status_code, response.text)
        doc = response.json()['dashboard']
        self.assertEqual(['table'], [t['kind'] for t in doc['tiles']])
        self.assertEqual('complete', doc['status'])
        self.assertEqual('2026', doc['scope'])
        self.sql._provider.assert_not_called()

    def test_declared_chart_choices_reuse_the_result_without_measure_drift(self):
        for measure in ('product_count', 'observed_items'):
            for reply, kind in [('display it all in a table', 'table'), ('Use a bar chart', 'bar')]:
                with self.subTest(measure=measure, reply=reply):
                    self.sql.run_payload.reset_mock()
                    payload = {'ok': True, 'query_status': 'executed',
                        'sql': f'SELECT p.category, COUNT(DISTINCT p.product_id) AS {measure} FROM commerce.products p GROUP BY 1 LIMIT 200',
                        'rows': [{'category': 'A', measure: 2}, {'category': 'B', measure: 3}],
                        'metadata': {'dashboard_outputs': [{'id': 'output0', 'kind': 'donut', 'query': 0,
                            'dimension': 'category', 'measures': [measure]}]}}
                    self.sql.run_payload.return_value = payload
                    pending = self.client.post('/api/dashboards', json={'description': 'Donut of distinct products by category'}).json()
                    self.assertEqual('clarification_required', pending['status'])
                    original = json.loads(json.dumps(payload))
                    # A second generation would be able to drift; it must never happen.
                    self.sql.run_payload.return_value = {'ok': False, 'answer': 'Unexpected requery'}
                    completed = self.client.post('/api/dashboards', json={'description': reply, 'conversation_id': pending['conversation_id']})
                    self.assertEqual(201, completed.status_code, completed.text)
                    doc = completed.json()['dashboard']
                    self.assertEqual('complete', doc['status'])
                    self.assertEqual(kind, doc['tiles'][0]['kind'])
                    self.assertEqual(original['sql'], doc['results'][0]['payload']['sql'])
                    self.assertEqual(original['rows'], doc['results'][0]['payload']['rows'])
                    if kind == 'bar': self.assertEqual([measure], doc['tiles'][0]['measures'])
                    self.sql.run_payload.assert_awaited_once()

    def test_explicit_measure_change_requeries_and_honors_choice_with_declared_outputs(self):
        def payload(measure, expression, source):
            return {'ok': True, 'query_status': 'executed',
                'sql': f'SELECT t.category, {expression} AS {measure} FROM {source} t GROUP BY 1 LIMIT 200',
                'rows': [{'category': 'A', measure: 2}, {'category': 'B', measure: 3}],
                'metadata': {'dashboard_outputs': [{'id': 'output0', 'kind': 'donut', 'query': 0,
                    'dimension': 'category', 'measures': [measure]}]}}
        self.sql.run_payload.side_effect = [payload('product_count', 'COUNT(DISTINCT t.product_id)', 'commerce.products'),
            payload('stock_on_hand', 'SUM(t.stock_on_hand)', 'commerce.inventory')]
        pending = self.client.post('/api/dashboards', json={'description': 'Donut of distinct products by category'}).json()
        completed = self.client.post('/api/dashboards', json={'description': 'stock on hand in a bar chart',
            'conversation_id': pending['conversation_id']})
        self.assertEqual(201, completed.status_code, completed.text)
        tile = completed.json()['dashboard']['tiles'][0]
        self.assertEqual(('bar', ['stock_on_hand']), (tile['kind'], tile['measures']))
        self.assertEqual(2, self.sql.run_payload.await_count)

    def test_large_presentation_result_does_not_create_an_unusable_conversation(self):
        self.sql.run_payload.return_value = {'ok': True, 'query_status': 'executed',
            'sql': 'SELECT p.category, COUNT(DISTINCT p.product_id) AS n FROM commerce.products p GROUP BY 1 LIMIT 200',
            'rows': [{'category': str(i) + 'x' * 250, 'n': i + 1} for i in range(200)],
            'metadata': {'dashboard_outputs': [{'id': 'output0', 'kind': 'donut', 'query': 0, 'dimension': 'category', 'measures': ['n']}]}}
        response = self.client.post('/api/dashboards', json={'description': 'Donut of products by category'}).json()
        self.assertEqual('failed', response['status'])
        self.assertFalse(response['can_reply'])
        self.assertIsNone(response['conversation_id'])
        self.assertIn('too large', response['message'])
        self.assertEqual([], self.store.list('alice'))

    def test_request_for_multiple_outputs_does_not_force_both_into_a_table(self):
        payload = {'ok': True, 'query_status': 'executed',
            'sql': 'SELECT p.category, COUNT(DISTINCT p.product_id) AS n FROM commerce.products p GROUP BY 1 LIMIT 200',
            'rows': [{'category': 'A', 'n': 2}, {'category': 'B', 'n': 3}],
            'metadata': {'dashboard_outputs': [{'id': 'output0', 'kind': 'donut', 'query': 0, 'dimension': 'category', 'measures': ['n']}]}}
        self.sql.run_payload.return_value = payload
        pending = self.client.post('/api/dashboards', json={'description': 'Donut of distinct products by category'}).json()
        changed = json.loads(json.dumps(payload))
        changed['metadata']['dashboard_outputs'] = [
            {'id': 'output0', 'kind': 'bar', 'query': 0, 'dimension': 'category', 'measures': ['n']},
            {'id': 'output1', 'kind': 'table', 'query': 0, 'dimension': None, 'measures': []}]
        self.sql.run_payload.return_value = changed
        response = self.client.post('/api/dashboards', json={'description': 'Use a bar chart and a table', 'conversation_id': pending['conversation_id']})
        self.assertEqual(201, response.status_code, response.text)
        self.assertEqual(['bar', 'table'], [t['kind'] for t in response.json()['dashboard']['tiles']])
        self.assertEqual(2, self.sql.run_payload.await_count)

    def test_refresh_chart_mismatch_changes_only_selected_tile_after_reply(self):
        old = document()
        old.description = old.queries[0].question = 'Line chart of revenue by category'
        old.tiles[0].kind, old.tiles[0].dimension = 'line', 'category'
        old.tiles[0].title = 'Keep my title'
        old = self.store.create('alice', old)
        self.sql.run_payload.return_value = {'ok': True, 'query_status': 'executed',
            'sql': 'SELECT s.category, SUM(s.revenue) AS revenue FROM commerce.sales s GROUP BY 1 LIMIT 200',
            'rows': [{'category': 'A', 'revenue': 10}, {'category': 'B', 'revenue': 20}]}
        pending = self.client.post(f'/api/dashboards/{old.id}/refresh', json={'revision': 1}).json()
        self.assertEqual('clarification_required', pending['status'])
        self.assertIn('bar chart', pending['message'])
        self.assertEqual(1, self.store.get('alice', old.id).revision)
        response = self.client.post('/api/dashboards', json={'description': 'Use a bar chart',
                                   'conversation_id': pending['conversation_id']})
        self.assertEqual(200, response.status_code, response.text)
        saved = response.json()['dashboard']
        self.assertEqual(old.id, saved['id'])
        self.assertEqual('bar', saved['tiles'][0]['kind'])
        self.assertEqual('Keep my title', saved['tiles'][0]['title'])
        self.assertEqual('complete', saved['status'])
        self.sql.run_payload.assert_awaited_once()

    def test_two_chart_clarifications_keep_each_previous_choice(self):
        payload = {'ok': True, 'query_status': 'executed',
            'sql': 'SELECT category, SUM(revenue) AS revenue FROM commerce.sales GROUP BY 1 LIMIT 200',
            'rows': [{'category': 'A', 'revenue': 10}, {'category': 'B', 'revenue': 20}],
            'metadata': {'dashboard_outputs': [{'id': 'output0', 'kind': 'line', 'query': 0,
                'dimension': 'category', 'measures': ['revenue']}]}}
        self.sql.run_payload.return_value = {'datasets': [
            {'question': 'Line chart of revenue by category', 'payload': payload},
            {'question': 'Line chart of revenue by another category', 'payload': payload}]}
        pending = self.start().json()
        self.assertEqual('clarification_required', pending['status'])
        pending = self.client.post('/api/dashboards', json={'description': 'Use a table',
                                   'conversation_id': pending['conversation_id']}).json()
        self.assertEqual('clarification_required', pending['status'])
        response = self.client.post('/api/dashboards', json={'description': 'Use a bar chart',
                                   'conversation_id': pending['conversation_id']})
        self.assertEqual(201, response.status_code, response.text)
        self.assertEqual(['table', 'bar'], [t['kind'] for t in response.json()['dashboard']['tiles']])
        self.sql.run_payload.assert_awaited_once()

    def test_cached_presentation_results_remain_private_and_expire(self):
        self.sql.run_payload.return_value = {'ok': True, 'query_status': 'executed',
            'sql': 'SELECT p.category, COUNT(DISTINCT p.product_id) AS n FROM commerce.products p GROUP BY 1 LIMIT 200',
            'rows': [{'category': 'A', 'n': 2}, {'category': 'B', 'n': 3}],
            'metadata': {'dashboard_outputs': [{'id': 'output0', 'kind': 'donut', 'query': 0, 'dimension': 'category', 'measures': ['n']}]}}
        pending = self.client.post('/api/dashboards', json={'description': 'Donut of distinct products by category'}).json()
        self.assertNotIn('presentation_document', pending)
        body = {'description': 'Use a table', 'conversation_id': pending['conversation_id']}
        self.user = {'sub': 'bob', 'role': 'admin'}
        self.assertEqual(409, self.client.post('/api/dashboards', json=body).status_code)
        self.user = {'sub': 'alice', 'role': 'admin'}
        self.time[0] += 1801
        self.assertEqual(409, self.client.post('/api/dashboards', json=body).status_code)
        self.sql.run_payload.assert_awaited_once()
        self.assertEqual([], self.store.list('alice'))

    def test_mixed_chart_request_resumes_after_date_clarification(self):
        description = 'a line chart of traffic session and a bar chart of traffic page views'
        pending = self.client.post('/api/dashboards', json={'description': description}).json()
        self.assertEqual('clarification_required', pending['status'])
        self.sql.run_payload.return_value = {'ok': True, 'query_status': 'executed',
            'sql': "SELECT DATE_TRUNC('month', w.date) AS month, SUM(w.sessions) AS sessions, SUM(w.page_views) AS page_views FROM commerce.web_traffic w GROUP BY 1 LIMIT 200",
            'rows': [{'month': '2026-01-01', 'sessions': 10, 'page_views': 20},
                     {'month': '2026-02-01', 'sessions': 15, 'page_views': 40}],
            'metadata': {'request_contract': {'columns': ['month', 'sessions', 'page_views'], 'dimensions': ['month'],
                'chart_type': None, 'charts': [
                    {'type': 'line', 'dimension': 'month', 'measures': ['sessions']},
                    {'type': 'bar', 'dimension': 'month', 'measures': ['page_views']}]}}}
        response = self.client.post('/api/dashboards', json={'description': 'month for the charts and time period is Jan to May 2026',
                                   'conversation_id': pending['conversation_id']})
        self.assertEqual(201, response.status_code, response.text)
        doc = response.json()['dashboard']
        self.assertEqual('complete', doc['status'])
        self.assertEqual(['line', 'bar'], [tile['kind'] for tile in doc['tiles']])
        self.assertEqual([['sessions'], ['page_views']], [tile['measures'] for tile in doc['tiles']])
        self.assertEqual(1, len(doc['queries']))
        self.assertEqual(2, self.sql.run_payload.await_count)
        self.sql._provider.assert_not_called()

    def test_unmapped_multiple_charts_ask_in_chat_instead_of_http_error(self):
        self.complete()
        pending = self.client.post('/api/dashboards', json={
            'description': 'A line chart of revenue and a bar chart of costs'}).json()
        self.assertEqual('clarification_required', pending['status'])
        self.assertIn('chart mapping', pending['message'])
        self.assertEqual([], self.store.list('alice'))
        response = self.client.post('/api/dashboards', json={
            'description': 'Use a table', 'conversation_id': pending['conversation_id']})
        self.assertEqual(201, response.status_code, response.text)
        self.assertEqual(['table'], [t['kind'] for t in response.json()['dashboard']['tiles']])

    def test_declared_chart_kpi_and_summary_persist_and_refresh_independently(self):
        from core.agents.sql.agent import SQLAnalyticsAgent
        from test_dashboard_requirements import response as planned_response
        planned = planned_response()
        provider = SimpleNamespace(generate=Mock(return_value=json.dumps(planned)))
        rows = [[{'month': '2026-01-01', 'revenue': 10}, {'month': '2026-02-01', 'revenue': 20}], [{'revenue': 300}]]
        async def execute(statement, *parameters):
            return rows[0] if 'GROUP BY' in statement.upper() else rows[1]
        repo = SimpleNamespace(execute_approved_query=AsyncMock(side_effect=execute))
        real = SQLAnalyticsAgent(repo, llm=provider, inventory_only=False)
        with patch('app.dashboards._get_runtime', AsyncMock(return_value=SimpleNamespace(analytics_agent=SimpleNamespace(sql_agent=real)))):
            result = self.client.post('/api/dashboards', json={
                'description': 'Monthly revenue in 2026 with a line chart, total revenue KPI and statistical summary'})
            self.assertEqual(201, result.status_code, result.text)
            saved = result.json()['dashboard']
            self.assertCountEqual(['line', 'summary', 'kpi'], [tile['kind'] for tile in saved['tiles']])
            self.assertEqual(1, provider.generate.call_count)
            reopened = self.client.get('/api/dashboards/' + saved['id']).json()['dashboard']
            self.assertEqual(saved, reopened)
            provider.generate.side_effect = lambda prompt, **kwargs: json.dumps(
                planned['queries'][1] if planned['queries'][1]['question'] in prompt else planned['queries'][0])
            refreshed = self.client.post('/api/dashboards/' + saved['id'] + '/refresh', json={'revision': saved['revision']})
            self.assertEqual(200, refreshed.status_code, refreshed.text)
            self.assertIn('dashboard', refreshed.json(), refreshed.text)
            self.assertEqual(saved['tiles'], refreshed.json()['dashboard']['tiles'])
            self.assertEqual('complete', refreshed.json()['dashboard']['status'])
            self.assertLessEqual(provider.generate.call_count, 3)  # At most one generation per refresh dataset; compilers may avoid it.

    def test_bad_requirement_mapping_stays_in_chat_without_executing(self):
        from core.agents.sql.agent import SQLAnalyticsAgent
        from test_dashboard_requirements import response as planned_response
        planned = planned_response()
        planned['outputs'][1]['query'] = 0
        provider = SimpleNamespace(generate=Mock(return_value=json.dumps(planned)))
        repo = SimpleNamespace(execute_approved_query=AsyncMock())
        real = SQLAnalyticsAgent(repo, llm=provider, inventory_only=False)
        with patch('app.dashboards._get_runtime', AsyncMock(return_value=SimpleNamespace(analytics_agent=SimpleNamespace(sql_agent=real)))):
            result = self.client.post('/api/dashboards', json={
                'description': 'Monthly revenue in 2026 with line chart, total revenue KPI and statistical summary'})
        self.assertEqual(200, result.status_code)
        self.assertEqual('failed', result.json()['status'])
        self.assertIn('An overall KPI needs a separate overall aggregate query', result.json()['message'])
        self.assertIsNone(result.json()['conversation_id'])
        self.assertEqual(2, provider.generate.call_count)
        self.assertEqual([], self.store.list('alice'))
        repo.execute_approved_query.assert_not_awaited()

    def test_count_contract_saves_three_kpis_with_one_dataset(self):
        from core.agents.sql.agent import SQLAnalyticsAgent
        from test_count_runtime import response as count_response, QUESTION
        provider = SimpleNamespace(generate=Mock(return_value=json.dumps(count_response())))
        repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[
            {'snapshot_date': '2026-05-31', 'sku_count': 3, 'out_count': 2, 'over_count': 2}]))
        real = SQLAnalyticsAgent(repo, llm=provider, inventory_only=False)
        with patch('app.dashboards._get_runtime', AsyncMock(return_value=SimpleNamespace(analytics_agent=real))):
            result = self.client.post('/api/dashboards', json={'description': QUESTION})
        self.assertEqual(201, result.status_code, result.text)
        dashboard = result.json()['dashboard']
        self.assertEqual(['kpi'] * 3, [tile['kind'] for tile in dashboard['tiles']])
        self.assertEqual(1, len(dashboard['queries']))
        provider.generate.assert_called_once()
        repo.execute_approved_query.assert_awaited_once()

    def test_generated_flag_grain_failure_does_not_open_clarification(self):
        from core.agents.sql.agent import SQLAnalyticsAgent
        from test_count_runtime import QUESTION
        provider = SimpleNamespace(generate=Mock(return_value=json.dumps({
            'metrics': ['observed_product_count', 'stockout_indicator', 'overstock_indicator'],
            'representation': 'aggregate', 'time': {'mode': 'latest'}})))
        repo = SimpleNamespace(execute_approved_query=AsyncMock())
        real = SQLAnalyticsAgent(repo, llm=provider, inventory_only=False)
        with patch('app.dashboards._get_runtime', AsyncMock(return_value=SimpleNamespace(analytics_agent=real))):
            result = self.client.post('/api/dashboards', json={'description': QUESTION})
        body = result.json()
        self.assertEqual('failed', body['status'])
        self.assertIsNone(body['conversation_id'])
        self.assertIn('Stored product values require product-level output', body['message'])
        self.assertNotIn('Please specify the inventory measure', body['message'])
        self.assertEqual([], self.store.list('alice'))
        repo.execute_approved_query.assert_not_awaited()

    def test_latest_count_clarification_adds_period_without_changing_to_all_snapshots(self):
        from core.agents.sql.agent import SQLAnalyticsAgent
        from test_count_runtime import response as count_response, QUESTION
        planned = count_response()
        planned['count_query']['time'] = {'mode': 'latest', 'start': '2026-01-01', 'end': '2026-12-31'}
        provider = SimpleNamespace(generate=Mock(side_effect=[
            json.dumps({'clarification': 'Which date field should define the latest inventory snapshot?'}), json.dumps(planned)]))
        repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[
            {'snapshot_date': '2026-11-13', 'sku_count': 97, 'out_count': 4, 'over_count': 6}]))
        real = SQLAnalyticsAgent(repo, llm=provider, inventory_only=False)
        with patch('app.dashboards._get_runtime', AsyncMock(return_value=SimpleNamespace(analytics_agent=real))):
            first = self.client.post('/api/dashboards', json={'description': QUESTION}).json()
            self.assertEqual('clarification_required', first['status'])
            repo.execute_approved_query.assert_not_awaited()
            completed = self.client.post('/api/dashboards', json={
                'description': 'Jan to Dec 2026', 'conversation_id': first['conversation_id']})
        self.assertEqual(201, completed.status_code, completed.text)
        dashboard = completed.json()['dashboard']
        self.assertEqual(QUESTION, dashboard['description'])
        self.assertEqual(['kpi'] * 3, [tile['kind'] for tile in dashboard['tiles']])
        count = dashboard['results'][0]['payload']['metadata']['count_query']
        self.assertEqual('latest', count['time']['mode'])
        self.assertEqual('snapshot_date', count['time']['field'])
        self.assertEqual('2026-01-01', count['time']['start'])
        self.assertEqual(2, provider.generate.call_count)
        repo.execute_approved_query.assert_awaited_once()

    def test_clarification_stays_transient_then_reply_builds_once_with_original_scope(self):
        response = self.start()
        self.assertEqual(200, response.status_code)
        pending = response.json()
        self.assertEqual('clarification_required', pending['status'])
        self.assertEqual(self.question, pending['message'])
        self.assertNotIn('dashboard', pending)
        self.assertEqual([], self.store.list('alice'))
        self.complete()
        response = self.client.post('/api/dashboards', json={
            'description': 'The monthly trend only, please.', 'conversation_id': pending['conversation_id']})
        self.assertEqual(201, response.status_code, response.text)
        doc = response.json()['dashboard']
        self.assertEqual('January through December 2026', doc['scope'])
        self.assertEqual(['line'], [tile['kind'] for tile in doc['tiles']])
        self.assertEqual(1, len(self.store.list('alice')))
        query = self.sql.run_payload.call_args.args[0].question
        self.assertIn('Web traffic dashboard', query)
        self.assertEqual(self.question, self.sql.run_payload.call_args.args[0].metadata['_dashboard_clarifications'][0]['question'])
        self.assertNotIn(self.question, query)
        self.assertIn('The monthly trend only', query)
        self.assertEqual(2, self.sql.run_payload.await_count)
        self.sql._provider.assert_not_called()

    def test_foreign_and_completed_conversations_cannot_be_reused(self):
        pending = self.start().json()
        self.sql.run_payload.reset_mock()
        self.user = {'sub': 'bob', 'role': 'admin'}
        body = {'description': 'Monthly only', 'conversation_id': pending['conversation_id']}
        self.assertEqual(409, self.client.post('/api/dashboards', json=body).status_code)
        self.sql.run_payload.assert_not_called()
        self.user = {'sub': 'alice', 'role': 'admin'}
        self.complete()
        self.assertEqual(201, self.client.post('/api/dashboards', json=body).status_code)
        self.sql.run_payload.reset_mock()
        self.assertEqual(409, self.client.post('/api/dashboards', json=body).status_code)
        self.sql.run_payload.assert_not_called()

    def test_provider_failure_does_not_create_a_dashboard(self):
        self.sql.run_payload.return_value = {'ok': False, 'query_status': 'error', 'answer': 'Data service unavailable'}
        response = self.start()
        self.assertEqual(200, response.status_code)
        self.assertEqual('failed', response.json()['status'])
        self.assertNotIn('dashboard', response.json())
        self.assertEqual([], self.store.list('alice'))

    def test_expiry_and_role_change_invalidate_pending_context_before_sql(self):
        pending = self.start().json()
        self.sql.run_payload.reset_mock()
        self.time[0] += 1801
        body = {'description': 'Monthly only', 'conversation_id': pending['conversation_id']}
        self.assertEqual(409, self.client.post('/api/dashboards', json=body).status_code)
        self.sql.run_payload.assert_not_called()
        pending = self.start().json()
        self.sql.run_payload.reset_mock()
        self.user = {'sub': 'alice', 'role': 'finance_analyst'}
        body['conversation_id'] = pending['conversation_id']
        self.assertEqual(409, self.client.post('/api/dashboards', json=body).status_code)
        self.sql.run_payload.assert_not_called()

    def test_round_limit_stops_without_saving_a_clarification_dashboard(self):
        pending = self.start().json()
        for _ in range(3):
            pending = self.client.post('/api/dashboards', json={
                'description': 'Can you explain the choice?', 'conversation_id': pending['conversation_id']}).json()
        self.assertFalse(pending['can_reply'])
        self.assertIsNone(pending['conversation_id'])
        self.assertEqual([], self.store.list('alice'))
        self.assertEqual(4, self.sql.run_payload.await_count)

    def test_old_saved_clarification_opens_as_chat_without_query_and_replaces_same_revision(self):
        old = self.store.create('alice', document(results=[QueryResult(
            id='sales', question='Revenue', status='clarification_required', message=self.question)]))
        pending = self.client.get(f'/api/dashboards/{old.id}').json()
        self.assertEqual('clarification_required', pending['status'])
        self.assertNotIn('html', pending)
        self.sql.run_payload.assert_not_called()
        self.complete()
        response = self.client.post('/api/dashboards', json={
            'description': 'Monthly only', 'conversation_id': pending['conversation_id']})
        self.assertEqual(200, response.status_code, response.text)
        saved = response.json()['dashboard']
        self.assertEqual(old.id, saved['id'])
        self.assertEqual(2, saved['revision'])
        self.assertEqual(1, len(self.store.list('alice')))

    def test_stale_target_and_scope_tampering_do_not_run_sql(self):
        old = self.store.create('alice', document(results=[QueryResult(
            id='sales', question='Revenue', status='clarification_required', message=self.question)]))
        pending = self.client.get(f'/api/dashboards/{old.id}').json()
        body = {'description': 'Monthly only', 'conversation_id': pending['conversation_id'], 'scope': 'changed'}
        self.assertEqual(422, self.client.post('/api/dashboards', json=body).status_code)
        self.store.save('alice', old, expected_revision=1)
        body.pop('scope')
        self.assertEqual(409, self.client.post('/api/dashboards', json=body).status_code)
        self.sql.run_payload.assert_not_called()

    def test_real_sql_stack_resumes_traffic_request_with_one_generation_per_user_turn(self):
        from core.sql_agent.agent import SQLAnalyticsAgent
        statement = ("SELECT DATE_TRUNC('month', w.date) AS month, SUM(w.sessions) AS sessions "
            'FROM commerce.web_traffic w WHERE w.date >= $1 AND w.date < $2 GROUP BY 1 ORDER BY 1 LIMIT 200')
        provider = SimpleNamespace(generate=Mock(side_effect=[json.dumps({'clarification': self.question}),
            json.dumps({'sql': statement, 'parameters': ['2026-01-01', '2027-01-01'],
                        'outputs': [{'kind': 'line', 'query': 0, 'dimension': 'month', 'measures': ['sessions']}]})]))
        repo = SimpleNamespace(execute_approved_query=AsyncMock(return_value=[
            {'month': '2026-01-01', 'sessions': 10}, {'month': '2026-02-01', 'sessions': 20}]))
        real = SQLAnalyticsAgent(repo, llm=provider, inventory_only=False)
        with patch('app.dashboards._get_runtime', AsyncMock(return_value=SimpleNamespace(analytics_agent=SimpleNamespace(sql_agent=real)))):
            pending = self.start().json()
            self.assertEqual('clarification_required', pending['status'])
            repo.execute_approved_query.assert_not_called()
            response = self.client.post('/api/dashboards', json={
                'description': 'Monthly trend only', 'conversation_id': pending['conversation_id']})
        self.assertEqual(201, response.status_code, response.text)
        self.assertEqual(['line'], [tile['kind'] for tile in response.json()['dashboard']['tiles']])
        self.assertEqual(2, provider.generate.call_count)
        self.assertIn(self.question, provider.generate.call_args.args[0])
        self.assertIn('Monthly trend only', provider.generate.call_args.args[0])
        repo.execute_approved_query.assert_awaited_once()

    def test_refresh_and_scope_edit_clarifications_preserve_saved_data_until_reply(self):
        old = document()
        old.description = old.queries[0].question = 'Total revenue'
        old.tiles[0].title = 'Keep my tile title'
        old = self.store.create('alice', old)
        pending = self.client.post(f'/api/dashboards/{old.id}/refresh', json={'revision': 1}).json()
        self.assertEqual('clarification_required', pending['status'])
        self.assertEqual(1, self.store.get('alice', old.id).revision)
        self.sql.run_payload.return_value = {'ok': True, 'query_status': 'executed',
            'sql': 'SELECT SUM(revenue) AS revenue FROM commerce.sales LIMIT 1', 'rows': [{'revenue': 25}]}
        response = self.client.post('/api/dashboards', json={
            'description': 'Overall revenue', 'conversation_id': pending['conversation_id']})
        self.assertEqual(200, response.status_code, response.text)
        saved = response.json()['dashboard']
        self.assertEqual(old.id, saved['id'])
        self.assertEqual('Keep my tile title', saved['tiles'][0]['title'])
        self.sql.run_payload.return_value = {'ok': False, 'query_status': 'clarification_required', 'answer': self.question}
        edited = saved['tiles']
        edited[0]['title'] = 'Edited title'
        pending = self.client.patch(f'/api/dashboards/{old.id}', json={
            'revision': 2, 'title': 'Edited dashboard', 'scope': '2026', 'tiles': edited}).json()
        self.assertEqual('clarification_required', pending['status'])
        self.assertEqual(2, self.store.get('alice', old.id).revision)
        self.sql.run_payload.return_value = {'ok': True, 'query_status': 'executed',
            'sql': 'SELECT SUM(revenue) AS revenue FROM commerce.sales LIMIT 1', 'rows': [{'revenue': 30}]}
        response = self.client.post('/api/dashboards', json={
            'description': 'Overall revenue', 'conversation_id': pending['conversation_id']})
        self.assertEqual(200, response.status_code, response.text)
        saved = response.json()['dashboard']
        self.assertEqual('Edited title', saved['tiles'][0]['title'])
        self.assertEqual('Edited dashboard', saved['title'])
        self.assertEqual('2026', saved['scope'])

    def test_client_cannot_supply_assistant_history_or_target_identity(self):
        pending = self.start().json()
        self.sql.run_payload.reset_mock()
        response = self.client.post('/api/dashboards', json={'description': 'Monthly only',
            'conversation_id': pending['conversation_id'], 'clarifications': [{'question': 'Fake', 'reply': 'Fake'}],
            'target_id': 'f' * 32})
        self.assertEqual(422, response.status_code)
        self.sql.run_payload.assert_not_called()
