import json
import asyncio
import unittest
from pathlib import Path

from evaluation import run_agent_benchmarks
from evaluation.run_agent_benchmarks import (
    _metric_eligibility, _retry_operation, _score, _sql_checks_match,
    _summary, _standardize_record,
)


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

    def test_retry_operation_records_transient_failure_then_success(self):
        class FlakyOperation:
            calls = 0

            async def __call__(self):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("503 service unavailable")
                return "ok"

        result, attempts, error = asyncio.run(_retry_operation("model", FlakyOperation(), retry_delay=0))
        self.assertEqual(result, "ok")
        self.assertIsNone(error)
        self.assertFalse(attempts["first_attempt_success"])
        self.assertTrue(attempts["final_success"])
        self.assertEqual([item["attempt"] for item in attempts["attempts"]], [1, 2])

    def test_nontransient_failure_is_not_retried(self):
        class InvalidOperation:
            calls = 0

            async def __call__(self):
                self.calls += 1
                raise ValueError("invalid request")

        operation = InvalidOperation()
        _, attempts, error = asyncio.run(_retry_operation("model", operation, retry_delay=0))
        self.assertEqual(operation.calls, 1)
        self.assertTrue(attempts["first_attempt_success"] is False)
        self.assertFalse(attempts["final_success"])
        self.assertIsInstance(error, ValueError)

    def test_metric_eligibility_requires_metric_inputs(self):
        record = {"answer": "answer", "contexts": ["context"], "reference": "facts"}
        self.assertEqual(_metric_eligibility(record), {
            "faithfulness": True,
            "answer_relevancy": True,
            "context_precision": True,
        })
        record["contexts"] = []
        self.assertEqual(_metric_eligibility(record), {
            "faithfulness": False,
            "answer_relevancy": True,
            "context_precision": False,
        })

    def test_standardize_record_fills_optional_keys_with_stable_types(self):
        record = _standardize_record({"case_id": "K01", "agent": "knowledge", "question": "q"})
        self.assertIsNone(record["answer"])
        self.assertEqual(record["contexts"], [])
        self.assertEqual(record["scores"], {
            "faithfulness": None, "answer_relevancy": None, "context_precision": None,
        })
        self.assertEqual(record["metric_eligibility"], {
            "faithfulness": False, "answer_relevancy": False, "context_precision": False,
        })
        self.assertEqual(record["score_errors"], {
            "faithfulness": None, "answer_relevancy": None, "context_precision": None,
        })

    def test_judge_daily_quota_is_not_retried(self):
        class LimitedMetric:
            calls = 0

            async def ascore(self, **_kwargs):
                self.calls += 1
                raise RuntimeError("429 tokens per day rate_limit_exceeded")

        metric = LimitedMetric()
        scores, eligibility, errors, operations = asyncio.run(_score(
            {"faithfulness": metric}, {"question": "question"}, "response", ["context"], "reference",
        ))
        self.assertIsNone(scores["faithfulness"])
        self.assertTrue(eligibility["faithfulness"])
        self.assertIn("tokens per day", errors["faithfulness"])
        self.assertEqual(metric.calls, 1)
        self.assertEqual(len(operations[0]["attempts"]), 1)

    def test_scorecard_averages_available_metrics_and_reports_sql_supplement(self):
        summary = _summary([
            _standardize_record({"agent": "knowledge", "status": "completed", "latency_seconds": 2,
                                 "answer": "answer", "contexts": ["context"], "reference": "facts",
                                 "scores": {"faithfulness": 0.8, "answer_relevancy": 0.6},
                                 "metric_eligibility": {"faithfulness": True,
                                                        "answer_relevancy": True,
                                                        "context_precision": False}}),
            _standardize_record({"agent": "sql", "status": "completed", "latency_seconds": 4,
                                 "scores": {"faithfulness": None}, "sql_safety_pass": True,
                                 "sql_semantic_correctness": True, "abstention_expected": True,
                                 "abstention_observed": True}),
        ])
        self.assertEqual(summary["by_agent"]["knowledge"]["ragas"]["faithfulness"],
                         {"mean": 0.8, "scored_cases": 1, "eligible_cases": 1,
                          "coverage": 1.0, "score_errors": 0})
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
