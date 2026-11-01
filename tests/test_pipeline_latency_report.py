import importlib.util
import unittest
import json
import os
import tempfile
from unittest.mock import patch
import httpx
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts/operations/measure_pipeline_latency.py"
spec = importlib.util.spec_from_file_location("pipeline_latency_report", path)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class PipelineLatencyReportTest(unittest.TestCase):
    def test_vietstyle_runs_use_fresh_sessions_and_save_real_response_fields(self):
        sessions = []

        def handler(request):
            if request.url.path == "/api/auth/login":
                return httpx.Response(200, json={"role": "admin"}, headers={
                    "set-cookie": "enterprise_session=test-session; Secure; HttpOnly; Path=/"})
            self.assertEqual(request.headers.get("Authorization"), "Bearer test-session")
            if request.url.path == "/api/auth/me":
                return httpx.Response(200, json={"role": "admin"})
            payload = json.loads(request.content)
            self.assertEqual(payload["agent_mode"], "knowledge")
            sessions.append(payload["conversation_id"])
            ok = len(sessions) != 2
            return httpx.Response(200, json={"agent": "knowledge", "answer": "Answer [S1]",
                "evidence": [{"citation_id": "S1", "source": "EN.pdf"}],
                "metadata": {"ok": ok, "latency": {"stages_ms": {"reranking": 100}}}})

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "results.json"
            args = ["measure", "--cases", "vietstyle", "--passes", "2", "--pause", "15",
                    "--no-resource-sampling", "--output", str(output)]
            client = httpx.Client(base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(handler))
            with patch.object(report.httpx, "Client", return_value=client), \
                 patch.dict(os.environ, {"DEMO_ADMIN_USERNAME": "test", "DEMO_ADMIN_PASSWORD": "test"}), \
                 patch("sys.argv", args), patch.object(report.time, "sleep"), patch("builtins.print"):
                self.assertEqual(report.main(), 1)
            saved = json.loads(output.read_text())
            self.assertEqual(len(sessions), 12)
            self.assertEqual(len(set(sessions)), 12)
            self.assertEqual(saved["summary"]["first_pass"]["application_ok"], 5)
            self.assertEqual(saved["by_case"]["V6"]["requests"], 2)
            self.assertEqual(saved["results"][0]["answer"], "Answer [S1]")
            self.assertEqual(saved["results"][0]["citation_count"], 1)

    def test_authentication_failure_stops_before_benchmark_requests(self):
        paths = []
        def handler(request):
            paths.append(request.url.path)
            return httpx.Response(401, json={"detail": "Invalid credentials"})
        with httpx.Client(base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                report.authenticate(client, "user", "password")
        self.assertEqual(paths, ["/api/auth/login"])

    def test_skipped_stages_do_not_become_zero_latency_samples(self):
        rows = [
            {"status": 200, "http_elapsed_ms": 100, "latency": {"stages_ms": {"embedding": 20, "reranking": None}}},
            {"status": 503, "http_elapsed_ms": 200, "latency": None},
            {"status": 200, "http_elapsed_ms": 300, "latency": {"stages_ms": {"embedding": None, "reranking": None}}},
        ]
        summary = report.summarize(rows)
        self.assertEqual(summary["http_200"], 2)
        self.assertEqual(summary["http_e2e"]["median_ms"], 200)
        self.assertEqual(summary["stages"]["embedding"]["n"], 1)
        self.assertEqual(summary["stages"]["embedding"]["median_ms"], 20)
        self.assertEqual(summary["stages"]["reranking"], {"n": 0})
