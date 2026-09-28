import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluate_api_load.py"
SPEC = importlib.util.spec_from_file_location("evaluate_api_load", SCRIPT)
evaluate_api_load = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate_api_load)


class ApiLoadEvaluationTest(unittest.TestCase):
    def test_percentile_uses_sorted_latency_values(self):
        self.assertEqual(evaluate_api_load.percentile([9, 1, 5], 0.5), 5)
        self.assertEqual(evaluate_api_load.percentile([1, 5, 9], 0.95), 9)

    def test_percentile_handles_empty_samples(self):
        self.assertIsNone(evaluate_api_load.percentile([], 0.95))

    def test_base_url_accepts_http_origin(self):
        self.assertEqual(evaluate_api_load.validate_base_url("http://127.0.0.1:8000/"), "http://127.0.0.1:8000")

    def test_base_url_rejects_credentials_and_paths(self):
        for value in ("ftp://localhost", "http://user:secret@localhost", "http://localhost/proxy", "http://localhost/?token=x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                evaluate_api_load.validate_base_url(value)

    def test_path_summary_keeps_route_latency_and_failures_separate(self):
        rows = [
            {"path": "/health", "status_code": 200, "latency_ms": 2.0},
            {"path": "/api/analytics", "status_code": 200, "latency_ms": 80.0},
            {"path": "/api/analytics", "status_code": 500, "latency_ms": 120.0},
        ]
        summary = evaluate_api_load.summarize_by_path(rows)
        self.assertEqual(summary["/health"]["request_count"], 1)
        self.assertEqual(summary["/api/analytics"]["failure_count"], 1)
        self.assertEqual(summary["/api/analytics"]["latency_ms"]["mean"], 100.0)


if __name__ == "__main__":
    unittest.main()
