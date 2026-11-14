import json
import sys
import unittest
from urllib.error import HTTPError
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.streamlit_ui import (AGENT_MODES, ReportConfirmationRequired, display_result,
                                      submit_chat, submit_report, submit_sql_assistant)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class _BinaryResponse(_Response):
    def __init__(self, payload, content_type):
        self.payload = payload
        self.headers = {"Content-Type": content_type}

    def read(self):
        return self.payload


class StreamlitClientTest(unittest.TestCase):
    def test_report_confirmation_is_preserved_for_explicit_resubmission(self):
        detail = {'status': 'confirmation_required', 'confirmation_required': True,
                  'scope_decision_required': True, 'unsupported_requirements': ['Supplier lead time missing']}
        def opener(request, timeout):
            raise HTTPError(request.full_url, 409, 'Conflict', {}, BytesIO(json.dumps({'detail': detail}).encode()))
        with self.assertRaises(ReportConfirmationRequired) as caught:
            submit_report('Inventory report', opener=opener)
        self.assertEqual(caught.exception.detail, detail)
        def accepted(request, timeout):
            self.assertIn(b'name="template_choice"\r\n\r\nsuggested', request.data)
            self.assertIn(b'name="accept_supported_scope"\r\n\r\ntrue', request.data)
            return _BinaryResponse(b'report', 'text/markdown')
        submit_report('Inventory report', template_choice='suggested', accept_supported_scope=True, opener=accepted)

    def test_report_clarification_displays_actual_question(self):
        def opener(request, timeout):
            body = json.dumps({"detail": {"code": "clarification_required",
                "clarification": "Refunded amount or returned units?"}}).encode()
            raise HTTPError(request.full_url, 422, "Unprocessable Entity", {}, BytesIO(body))
        with self.assertRaisesRegex(RuntimeError, "Clarification needed: Refunded amount or returned units"):
            submit_report("Returns report", source_mode="combined", opener=opener)

    def test_submit_report_uploads_template_and_returns_matching_file(self):
        captured = []

        def opener(request, timeout):
            captured.append((request, timeout))
            return _BinaryResponse(b"# Report\n", "text/markdown; charset=utf-8")

        payload, content_type, status = submit_report("Create report", "template.md", b"# Report\n",
                                              api_url="http://api.test", opener=opener)
        request, timeout = captured[0]
        self.assertEqual(request.full_url, "http://api.test/api/report")
        self.assertIn(b'name="question"', request.data)
        self.assertIn(b'name="template"; filename="template.md"', request.data)
        self.assertIn(b"# Report\n", request.data)
        self.assertEqual(timeout, 600)
        self.assertEqual((payload, content_type), (b"# Report\n", "text/markdown; charset=utf-8"))
        self.assertEqual(status, "complete")

    def test_submit_report_without_template_retains_partial_status(self):
        def opener(request, timeout):
            self.assertNotIn(b'name="template"', request.data)
            self.assertIn(b"combined", request.data)
            response = _BinaryResponse(b"partial report", "text/markdown")
            response.headers["X-Report-Status"] = "partial"
            return response
        self.assertEqual(submit_report("Report", source_mode="combined", opener=opener),
                         (b"partial report", "text/markdown", "partial"))

    def test_submit_report_rejects_unsafe_filename(self):
        with self.assertRaises(ValueError):
            submit_report("question", 'bad".md', b"# Report")

    def test_report_auto_sources_send_separate_conversation_id(self):
        def opener(request, timeout):
            self.assertIn(b'orchestrated', request.data)
            self.assertIn(b'name="conversation_id"', request.data)
            self.assertIn(b'report-session', request.data)
            return _BinaryResponse(b'# Report', 'text/markdown')
        submit_report('Report', source_mode='orchestrated', conversation_id='report-session', opener=opener)

    def test_dashboard_mode_renders_all_chart_types_and_source_table(self):
        class FakeStreamlit:
            def __init__(self):
                self.charts, self.tables = [], []
            def subheader(self, value): pass
            def caption(self, value): pass
            def markdown(self, value): pass
            def vega_lite_chart(self, **kwargs): self.charts.append(kwargs)
            def dataframe(self, rows, **kwargs): self.tables.append(rows)

        self.assertEqual(AGENT_MODES['Dashboard'], 'dashboard')
        for kind, mark in [('line', 'line'), ('bar', 'bar'), ('donut', 'arc')]:
            st = FakeStreamlit()
            rows = [{'category': 'A', 'sessions': 10}, {'category': 'B', 'sessions': 20}]
            chart = {'type': kind, 'title': 'Sessions', 'categories': ['A', 'B'],
                     'series': [{'name': 'Sessions', 'values': [10, 20]}], 'unit': 'sessions',
                     'x_label': 'Source', 'y_label': 'Sessions', 'temporal': False, 'scope': {}}
            display_result(st, {'answer': 'done', 'data': {'rows': rows, 'visualization': chart}}, key_prefix='turn')
            self.assertEqual(len(st.charts), 1)
            self.assertEqual(st.charts[0]['spec']['mark']['type'], mark)
            self.assertEqual(st.tables, [rows])
            self.assertEqual(st.charts[0]['key'], 'turn:chart')
            self.assertEqual(len(st.charts[0]['spec']['data']['values']), 2)

    def test_dashboard_chat_runs_in_streamlit_with_real_chart_and_table(self):
        from streamlit.testing.v1 import AppTest
        import streamlit as st
        from unittest.mock import MagicMock, patch
        response = MagicMock()
        chart = {'type': 'donut', 'title': 'Sessions during 2022', 'categories': ['A', 'B'],
                 'series': [{'name': 'Sessions', 'values': [10, 20]}], 'unit': 'sessions',
                 'x_label': 'Source', 'y_label': 'Sessions', 'scope': {}}
        response.__enter__.return_value.read.return_value = json.dumps({
            'answer': 'done', 'agent': 'dashboard', 'data': {
                'rows': [{'source': 'A', 'sessions': 10}], 'visualization': chart}}).encode()
        with patch.dict('os.environ', {'API_AGENT_PREFIX': '/api'}), \
                patch('urllib.request.urlopen', return_value=response) as submit, \
                patch.object(st, 'vega_lite_chart', wraps=st.vega_lite_chart) as render:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/core/agents/streamlit_ui.py'),
                                    default_timeout=15).run()
            app.selectbox(key='agent_mode').select('Dashboard').run()
            app.chat_input[0].set_value('Donut of session share during 2022').run()
            self.assertFalse(app.exception)
            self.assertEqual(json.loads(submit.call_args.args[0].data)['agent_mode'], 'dashboard')
            self.assertTrue(app.dataframe)
            self.assertTrue(render.called)

    def test_submit_chat_sends_selected_mode_to_fastapi(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return _Response({"answer": "Policy result", "agent": "knowledge", "evidence": [], "data": {}})

        result = submit_chat("What does the policy say?", "knowledge", api_url="http://api.test/", opener=opener)

        request, timeout = requests[0]
        self.assertEqual(request.full_url, "http://api.test/api/chat")
        self.assertEqual(json.loads(request.data), {
            "question": "What does the policy say?", "agent_mode": "knowledge", "metadata": {},
        })
        self.assertEqual(timeout, 135)
        self.assertEqual(result["answer"], "Policy result")

    def test_submit_chat_rejects_unknown_modes(self):
        with self.assertRaises(ValueError):
            submit_chat("question", "unknown")

    def test_sql_assistant_sends_draft_and_approved_requests_to_dedicated_route(self):
        requests = []
        def opener(request, timeout):
            requests.append((request, timeout))
            return _Response({"status": "approval_required"})
        submit_sql_assistant("List products", api_url="http://api.test", opener=opener)
        submit_sql_assistant("List products", mode="execute", sql="SELECT 1 LIMIT 1",
                             parameters=[], opener=opener)
        self.assertEqual([request.full_url for request, _ in requests], [
            "http://api.test/api/sql/assistant", "http://127.0.0.1:8000/api/sql/assistant",
        ])
        self.assertEqual(json.loads(requests[0][0].data), {"question": "List products", "mode": "draft"})
        self.assertEqual(json.loads(requests[1][0].data), {
            "question": "List products", "mode": "execute", "sql": "SELECT 1 LIMIT 1", "parameters": [],
        })
        self.assertTrue(all(timeout == 135 for _, timeout in requests))

    def test_auto_is_single_default_and_conversation_is_transmitted(self):
        self.assertEqual(next(iter(AGENT_MODES.values())), 'auto')
        self.assertNotIn('agentic', AGENT_MODES.values())
        def opener(request, timeout):
            self.assertEqual(json.loads(request.data)['conversation_id'], 'session-1')
            self.assertEqual(json.loads(request.data)['agent_mode'], 'auto')
            return _Response({'answer': 'done'})
        submit_chat('Follow up', 'auto', conversation_id='session-1', opener=opener)

    def test_display_result_renders_nested_sql_rows_and_sources(self):
        class Expander:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class FakeStreamlit:
            def __init__(self):
                self.tables = []
                self.text = []
                self.codes = []
                self.downloads = []

            def markdown(self, value):
                self.text.append(value)

            def subheader(self, value):
                self.text.append(value)

            def dataframe(self, rows, **_kwargs):
                self.tables.append(rows)

            def expander(self, _label):
                return Expander()

            def caption(self, value):
                self.text.append(value)

            def code(self, value, **_kwargs):
                self.codes.append(value)

            def download_button(self, *args, **_kwargs):
                self.downloads.append(args)

        st = FakeStreamlit()
        display_result(st, {
            "answer": "Combined answer",
            "data": {"sql": {"rows": [{"orders": 4}], "attempted_sql": "DELETE FROM commerce.orders",
                              "parameters": ["2026-03-01", "2026-04-01"], "query_status": "rejected"}},
            "evidence": [{"citation_id": "S1", "source": "commerce.orders"}],
            "metadata": {"limitations": ["Limited to current schema."]},
        })

        self.assertEqual(st.tables, [[{"orders": 4}]])
        self.assertIn("Combined answer", st.text)
        self.assertIn("**S1 · commerce.orders**", st.text)
        self.assertIn("Limitation: Limited to current schema.", st.text)
        self.assertEqual(st.codes, ["DELETE FROM commerce.orders"])
        self.assertIn('Parameters: ["2026-03-01", "2026-04-01"]', st.text)
        self.assertIn("Query status: rejected", st.downloads[0][1])


if __name__ == "__main__":
    unittest.main()
