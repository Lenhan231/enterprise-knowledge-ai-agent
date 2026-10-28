import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.streamlit_ui import AGENT_MODES, display_result, submit_chat, submit_report


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
    def test_submit_report_uploads_template_and_returns_matching_file(self):
        captured = []

        def opener(request, timeout):
            captured.append((request, timeout))
            return _BinaryResponse(b"# Report\n", "text/markdown; charset=utf-8")

        payload, content_type = submit_report("Create report", "template.md", b"# Report\n",
                                              api_url="http://api.test", opener=opener)
        request, timeout = captured[0]
        self.assertEqual(request.full_url, "http://api.test/api/report")
        self.assertIn(b'name="question"', request.data)
        self.assertIn(b'name="template"; filename="template.md"', request.data)
        self.assertIn(b"# Report\n", request.data)
        self.assertEqual(timeout, 180)
        self.assertEqual((payload, content_type), (b"# Report\n", "text/markdown; charset=utf-8"))

    def test_submit_report_rejects_unsafe_filename(self):
        with self.assertRaises(ValueError):
            submit_report("question", 'bad".md', b"# Report")

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

        result = submit_chat("What does the policy say?", "knowledge", api_url="http://api.test/", opener=opener)

        request, timeout = requests[0]
        self.assertEqual(request.full_url, "http://api.test/api/chat")
        self.assertEqual(json.loads(request.data), {
            "question": "What does the policy say?", "agent_mode": "knowledge", "metadata": {},
        })
        self.assertEqual(timeout, 90)
        self.assertEqual(result["answer"], "Policy result")

    def test_submit_chat_rejects_unknown_modes(self):
        with self.assertRaises(ValueError):
            submit_chat("question", "auto")

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
                              "parameters": [], "query_status": "rejected"}},
            "evidence": [{"citation_id": "S1", "source": "commerce.orders"}],
            "metadata": {"limitations": ["Limited to current schema."]},
        })

        self.assertEqual(st.tables, [[{"orders": 4}]])
        self.assertIn("Combined answer", st.text)
        self.assertIn("**S1 · commerce.orders**", st.text)
        self.assertIn("Limitation: Limited to current schema.", st.text)
        self.assertEqual(st.codes, ["DELETE FROM commerce.orders"])
        self.assertIn("Query status: rejected", st.downloads[0][1])


if __name__ == "__main__":
    unittest.main()
