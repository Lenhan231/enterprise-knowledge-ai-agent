import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.streamlit_ui import display_result, submit_chat


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class StreamlitClientTest(unittest.TestCase):
    def test_submit_chat_sends_selected_mode_to_fastapi(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return _Response({"answer": "Policy result", "agent": "knowledge", "evidence": [], "data": {}})

        result = submit_chat("What does the policy say?", "knowledge", api_url="http://api.test/", opener=opener)

        request, timeout = requests[0]
        self.assertEqual(request.full_url, "http://api.test/api/chat")
        self.assertEqual(json.loads(request.data), {"question": "What does the policy say?", "agent_mode": "knowledge"})
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
