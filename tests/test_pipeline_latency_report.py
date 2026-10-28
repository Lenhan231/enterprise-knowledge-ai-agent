import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts/operations/measure_pipeline_latency.py"
spec = importlib.util.spec_from_file_location("pipeline_latency_report", path)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class PipelineLatencyReportTest(unittest.TestCase):
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
