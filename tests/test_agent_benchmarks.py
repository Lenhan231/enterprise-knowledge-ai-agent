import json
import asyncio
import unittest
from pathlib import Path

from evaluation import run_agent_benchmarks
from evaluation.run_agent_benchmarks import _score, _sql_checks_match, _summary


ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = ROOT / "evaluation" / "agent_benchmarks"


class AgentBenchmarkAssetsTest(unittest.TestCase):
    def test_sql_semantic_checks_compare_rows_not_query_text(self):
        self.assertTrue(_sql_checks_match(
            [{"revenue": 52454936.2}, {"revenue": 0}],
            [{"row_count": 2}, {"field": "revenue", "equals": 52454936.2}],
        ))
        self.assertFalse(_sql_checks_match([], [{"row_count": 1}]))
        self.assertIsNone(_sql_checks_match([], []))

    def test_judge_daily_quota_defers_scores_without_retries(self):
        class LimitedMetric:
            calls = 0

            async def ascore(self, **_kwargs):
                self.calls += 1
                raise RuntimeError("429 tokens per day rate_limit_exceeded")

        metric = LimitedMetric()
        run_agent_benchmarks.JUDGE_QUOTA_EXHAUSTED = False
        try:
            scores, errors = asyncio.run(_score(
                {"faithfulness": metric}, {"question": "question"}, "response", [], "reference",
            ))
            _, deferred_errors = asyncio.run(_score(
                {"faithfulness": metric}, {"question": "question"}, "response", [], "reference",
            ))
        finally:
            run_agent_benchmarks.JUDGE_QUOTA_EXHAUSTED = False
        self.assertIsNone(scores["faithfulness"])
        self.assertIn("deferred", errors["faithfulness"])
        self.assertIn("deferred", deferred_errors["faithfulness"])
        self.assertEqual(metric.calls, 1)

    def test_scorecard_averages_available_metrics_and_reports_sql_supplement(self):
        summary = _summary([
            {"agent": "knowledge", "status": "scored", "latency_seconds": 2,
             "scores": {"faithfulness": 0.8, "answer_relevancy": 0.6, "context_precision": None}},
            {"agent": "sql", "status": "score_partial", "latency_seconds": 4,
             "scores": {"faithfulness": None}, "sql_safety_pass": True,
             "abstention_expected": True, "abstention_observed": True},
        ])
        self.assertEqual(summary["by_agent"]["knowledge"]["ragas"]["faithfulness"],
                         {"mean": 0.8, "scored_cases": 1})
        self.assertEqual(summary["sql"]["safety_pass_rate"], 1.0)
        self.assertEqual(summary["sql"]["abstention_accuracy"], 1.0)
        self.assertIsNone(summary["hallucination_rate"])

    def load(self, name):
        return json.loads((BENCHMARKS / name).read_text(encoding="utf-8"))

    def test_three_benchmark_sets_have_25_unique_cases(self):
        for name, prefix in (
            ("knowledge_agent_benchmark.json", "K"),
            ("sql_analytics_agent_benchmark.json", "S"),
            ("report_agent_benchmark.json", "R"),
        ):
            with self.subTest(name=name):
                cases = self.load(name)["cases"]
                ids = [case["id"] for case in cases]
                self.assertEqual(len(cases), 25)
                self.assertEqual(len(ids), len(set(ids)))
                self.assertEqual(ids, [f"{prefix}{index:02}" for index in range(1, 26)])

    def test_report_cases_reference_available_template_fixtures(self):
        fixtures = {item["id"] for item in self.load("report_template_fixtures.json")["templates"]}
        cases = self.load("report_agent_benchmark.json")["cases"]
        self.assertEqual(len(fixtures), 5)
        self.assertTrue(all(case["template_fixture_id"] in fixtures for case in cases))

    def test_inventory_dashboard_contract_is_present(self):
        outlines = self.load("dashboard_static_outlines.json")["outlines"]
        inventory = next(item for item in outlines if item["id"] == "inventory_control")
        self.assertIn("exception_table", {item["id"] for item in inventory["sections"]})
        self.assertEqual(inventory["filters"][0]["source"], "commerce.inventory.snapshot_date")


if __name__ == "__main__":
    unittest.main()
