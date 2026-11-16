import json
import os
import sys
import unittest
from urllib.error import HTTPError
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.streamlit_ui import (AGENT_MODES, ReportConfirmationRequired, display_result,
                                      _remote_retrieval_login, submit_chat, submit_chat_stream,
                                      submit_report, submit_sql_assistant)


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
                                              api_url="http://api.test", opener=opener,
                                              remote_retrieval_session="remote-session")
        request, timeout = captured[0]
        self.assertEqual(request.full_url, "http://api.test/api/report")
        self.assertEqual(request.get_header("X-remote-retrieval-session"), "remote-session")
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

    def test_dashboard_mode_is_selectable_and_renders_inventory_charts(self):
        class FakeStreamlit:
            def __init__(self):
                self.headings = []
                self.metrics = []
                self.charts = []
                self.tables = []
                self.captions = []

            def subheader(self, value): self.headings.append(value)
            def caption(self, value): self.captions.append(value)
            def metric(self, *args): self.metrics.append(args)
            def columns(self, count): return [self] * count
            def bar_chart(self, data, **kwargs): self.charts.append((data, kwargs))
            def dataframe(self, rows, **kwargs): self.tables.append(rows)
            def markdown(self, _value): pass

        self.assertEqual(AGENT_MODES["Inventory Dashboard"], "dashboard")
        st = FakeStreamlit()
        display_result(st, {"answer": "snapshot", "data": {"dashboard": {
            "outline_id": "inventory_control", "title": "Inventory Control & Exceptions",
            "snapshot_date": "2022-12-31", "kpis": {"sku_count": 10},
            "stockout_by_category": [{"category": "A", "stockout_rate": 2.0}],
            "inventory_flags": [{"category": "A", "stockout_flag_count": 1,
                                  "overstock_flag_count": 3, "both_flags_count": 0}],
            "exceptions": [{"product_id": "P1"}],
        }}, "evidence": [], "metadata": {}})

        self.assertIn("Inventory Control & Exceptions", st.headings)
        self.assertTrue(st.metrics)
        self.assertEqual(len(st.charts), 2)
        self.assertEqual(st.tables, [[{"product_id": "P1"}]])

    def test_submit_chat_sends_selected_mode_to_fastapi(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return _Response({"answer": "Policy result", "agent": "knowledge", "evidence": [], "data": {}})

        result = submit_chat("What does the policy say?", "knowledge", api_url="http://api.test/",
                             opener=opener, remote_retrieval_session="remote-session")

        request, timeout = requests[0]
        self.assertEqual(request.full_url, "http://api.test/api/chat")
        self.assertEqual(json.loads(request.data), {
            "question": "What does the policy say?", "agent_mode": "knowledge", "metadata": {},
        })
        self.assertEqual(request.get_header("X-remote-retrieval-session"), "remote-session")
        self.assertEqual(timeout, 135)
        self.assertEqual(result["answer"], "Policy result")

    def test_submit_chat_rejects_unknown_modes(self):
        with self.assertRaises(ValueError):
            submit_chat("question", "unknown")

    def test_streamlit_forwards_remote_retrieval_session_to_local_agent(self):
        requests = []

        class StreamResponse:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def __iter__(self):
                return iter([
                    b'event: result\n',
                    b'data: {"answer":"done"}\n',
                    b'\n',
                ])

        def opener(request, timeout):
            requests.append((request, timeout))
            return StreamResponse()

        submit_chat_stream("policy", "knowledge", api_url="http://local.test", opener=opener,
                           remote_retrieval_session="remote-session")

        self.assertEqual(requests[0][0].get_header("X-remote-retrieval-session"), "remote-session")
        self.assertEqual(requests[0][1], 300)

    def test_remote_retrieval_login_requires_matching_identity_and_returns_session(self):
        class FakeCookieJar:
            def __iter__(self):
                return iter([SimpleNamespace(name="enterprise_session", value="remote-session")])

        class FakeOpener:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return _Response({"username": "alice", "role": "employee"})

        opener = FakeOpener()
        with patch.dict(os.environ, {
            "RETRIEVAL_SERVICE_AUTH": "session",
            "RETRIEVAL_SERVICE_URL": "https://api.example/api/retrieval",
        }), patch("core.agents.streamlit_ui.CookieJar", return_value=FakeCookieJar()), \
                patch("core.agents.streamlit_ui.build_opener", return_value=opener):
            session = _remote_retrieval_login("alice", "password", {"username": "alice", "role": "employee"})

        self.assertEqual(session, "remote-session")
        self.assertEqual(opener.request.full_url, "https://api.example/api/auth/login")
        self.assertEqual(json.loads(opener.request.data), {"username": "alice", "password": "password"})

        with patch.dict(os.environ, {
            "RETRIEVAL_SERVICE_AUTH": "session",
            "RETRIEVAL_SERVICE_URL": "https://api.example/api/retrieval",
        }), patch("core.agents.streamlit_ui.CookieJar", return_value=FakeCookieJar()), \
                patch("core.agents.streamlit_ui.build_opener", return_value=opener):
            with self.assertRaisesRegex(RuntimeError, "same account and role"):
                _remote_retrieval_login("alice", "password", {"username": "alice", "role": "admin"})

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

            def warning(self, value):
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
            "metadata": {"limitations": ["Limited to current schema."], "task_trace": [
                {"id": "fallback", "agent": "sql", "status": "failed", "attempts": 1,
                 "error_type": "SQLValidationError", "error_detail": "JOIN does not match an approved relationship."}
            ]},
        }, question="thời gian giao hàng trung bình")

        self.assertEqual(st.tables[0], [{"Orders": 4}])
        self.assertEqual(st.tables[1][0]["error_type"], "SQLValidationError")
        self.assertIn("Combined answer", st.text)
        self.assertIn("**S1 · commerce.orders**", st.text)
        self.assertIn("Lưu ý: Limited to current schema.", st.text)
        self.assertEqual(st.codes, ["DELETE FROM commerce.orders", "JOIN does not match an approved relationship."])
        self.assertTrue(any("Lý do lỗi · fallback" in item for item in st.text))
        self.assertIn('Tham số: ["2026-03-01", "2026-04-01"]', st.text)
        self.assertIn("Query status: rejected", st.downloads[0][1])

    def test_unverified_metric_results_are_presented_as_readable_vietnamese_table(self):
        class Expander:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class FakeStreamlit:
            def __init__(self):
                self.tables = []
                self.text = []

            def markdown(self, value):
                self.text.append(value)

            def subheader(self, value):
                self.text.append(value)

            def warning(self, value):
                self.text.append(value)

            def caption(self, value):
                self.text.append(value)

            def dataframe(self, rows, **_kwargs):
                self.tables.append(rows)

            def expander(self, _label):
                return Expander()

        st = FakeStreamlit()
        display_result(st, {
            'answer': 'Evidence fallback — review the supported findings and gaps below.',
            'data': {'sql': {'rows': [{'product_name': 'Grid Runner', 'total_quantity_sold': 152}]}},
            'evidence': [],
            'metadata': {'fallback': True, 'limitations': [
                'Định nghĩa metric chưa được xác minh; kết quả chỉ phản ánh truy vấn.'
            ]},
        }, question='sản phẩm bán chạy nhất tháng trước')

        rendered_text = '\n'.join(st.text)
        self.assertIn('Định nghĩa metric chưa được xác minh', rendered_text)
        self.assertIn('Truy vấn đã chạy;', rendered_text)
        self.assertNotIn('Evidence fallback', rendered_text)
        self.assertIn('Kết quả truy vấn', rendered_text)
        self.assertEqual(st.tables, [[{'Tên sản phẩm': 'Grid Runner', 'Tổng lượng theo truy vấn': 152}]])


if __name__ == "__main__":
    unittest.main()
