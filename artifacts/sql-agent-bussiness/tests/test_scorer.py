import importlib.util
import json
import copy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sql_agent_benchmark_scorer", ROOT / "scorer.py")
SCORER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCORER)
CASE_SET = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in CASE_SET["cases"]}


def observation_from_gold(case):
    gold = case["gold"]
    return {
        "status": "executed" if case["supported"] else "clarification_required",
        "sql": gold["sql"],
        "parameters": gold["parameters"],
        "rows": gold["rows"],
        "columns": list(gold["rows"][0]) if gold["rows"] else [],
        "execution_events": [],
    }


class SQLAgentBenchmarkScorerTest(unittest.TestCase):
    def test_frozen_supported_gold_observations_score_correct(self):
        for case_id in ("P01", "P02", "P03", "P04"):
            with self.subTest(case_id=case_id):
                case = CASES[case_id]
                outcome = SCORER.score_case(case, observation_from_gold(case))
                self.assertTrue(outcome["business_end_to_end_correct"])
                self.assertTrue(outcome["strict_result_exact_match"])

    def test_delivered_order_filter_is_part_of_semantic_contract(self):
        case = CASES["P02"]
        observation = observation_from_gold(case)
        observation["sql"] = observation["sql"].replace("o.order_status = $1 AND ", "")
        observation["parameters"] = observation["parameters"][1:]
        outcome = SCORER.score_case(case, observation)
        self.assertFalse(outcome["sql_semantic_accuracy"])
        self.assertFalse(outcome["business_end_to_end_correct"])

    def test_wrong_ranking_direction_fails_even_if_reference_rows_are_copied(self):
        case = CASES["P03"]
        observation = observation_from_gold(case)
        observation["sql"] = observation["sql"].replace("units_sold DESC", "units_sold ASC")
        outcome = SCORER.score_case(case, observation)
        self.assertFalse(outcome["sql_semantic_accuracy"])
        self.assertFalse(outcome["business_end_to_end_correct"])

    def test_inclusive_date_end_is_equivalent_only_for_a_date_column(self):
        case = CASES["P03"]
        observation = observation_from_gold(case)
        observation["sql"] = observation["sql"].replace(
            "o.order_date < $3", "o.order_date <= $3"
        )
        observation["parameters"] = ["delivered", "2025-04-01", "2025-06-30"]
        self.assertTrue(SCORER.score_case(case, observation)["sql_semantic_accuracy"])

        timestamp_case = copy.deepcopy(case)
        timestamp_case["semantic"]["filters"]["date_range"]["column_type"] = "timestamp without time zone"
        self.assertFalse(SCORER.score_case(timestamp_case, observation)["sql_semantic_accuracy"])

    def test_units_alias_is_business_correct_but_not_strict_schema_exact(self):
        case = CASES["P03"]
        observation = observation_from_gold(case)
        observation["sql"] = observation["sql"].replace("AS units_sold", "AS units")
        observation["rows"] = [
            {"product_id": row["product_id"], "units": row["units_sold"]}
            for row in observation["rows"]
        ]
        observation["columns"] = ["product_id", "units"]
        outcome = SCORER.score_case(case, observation)
        self.assertTrue(outcome["business_end_to_end_correct"])
        self.assertFalse(outcome["strict_result_exact_match"])

    def test_snapshot_provenance_column_is_business_valid_but_not_strict(self):
        case = CASES["P04"]
        observation = observation_from_gold(case)
        observation["sql"] = observation["sql"].replace(
            "i.stock_on_hand FROM", "i.stock_on_hand, i.snapshot_date FROM"
        )
        observation["rows"] = [
            {**row, "snapshot_date": "2026-11-13"} for row in observation["rows"]
        ]
        observation["columns"] = ["product_id", "product_name", "stock_on_hand", "snapshot_date"]
        outcome = SCORER.score_case(case, observation)
        self.assertTrue(outcome["business_end_to_end_correct"])
        self.assertFalse(outcome["strict_result_exact_match"])

    def test_jev_recall_uses_raw_top_five_not_full_schema_fallback_coverage(self):
        case = CASES["P02"]
        observation = observation_from_gold(case)
        observation["id"] = "P02"
        observation["schema_selection"] = {
            "method": "jev_top_five", "candidate_tables": ["commerce.orders", "commerce.customers"],
            "final_selected_tables": ["commerce.orders", "commerce.customers"],
        }
        jev = SCORER.score_experiment(CASE_SET, {
            "cases": [observation if item["id"] == "P02" else {
                "id": item["id"], "status": "NOT_RUN"} for item in CASE_SET["cases"]]
        })["metrics"]
        self.assertEqual(jev["jev_table_recall_at_5"]["numerator"], 1)
        self.assertEqual(jev["jev_table_recall_at_5"]["denominator"], 1)
        self.assertEqual(jev["final_selected_schema_coverage"]["value"], 1.0)

        observation["schema_selection"] = {
            "method": "full_schema_fallback", "candidate_tables": [],
            "final_selected_tables": ["commerce.orders", "commerce.customers"],
        }
        fallback = SCORER.score_experiment(CASE_SET, {
            "cases": [observation if item["id"] == "P02" else {
                "id": item["id"], "status": "NOT_RUN"} for item in CASE_SET["cases"]]
        })["metrics"]
        self.assertIsNone(fallback["jev_table_recall_at_5"]["value"])
        self.assertEqual(fallback["final_selected_schema_coverage"]["value"], 1.0)

    def test_unsupported_scope_requires_abstention_without_sql_or_execution(self):
        case = CASES["P05"]
        observation = observation_from_gold(case)
        self.assertTrue(SCORER.score_case(case, observation)["safe_unsupported_abstention"])
        observation["sql"] = "SELECT * FROM commerce.inventory"
        self.assertFalse(SCORER.score_case(case, observation)["safe_unsupported_abstention"])

    def test_unsupported_case_calls_are_included_in_provider_totals(self):
        case = CASES["P05"]
        observation = {
            "id": "P05", "status": "clarification_required", "sql": None,
            "execution_events": [], "schema_selection": {
                "jev_status": "failed", "jev_http_status": 402,
            }, "calls": {
                "general_sql_generation": 1, "metric_interpretation": 1,
                "jev_attempts": 1, "schema_discovery": 1,
            },
        }

        scored = SCORER.score_experiment({"cases": [case]}, {"cases": [observation]})
        metrics = scored["metrics"]

        self.assertEqual(metrics["provider_calls"]["sql_generation_provider_submissions"], 1)
        self.assertEqual(metrics["provider_calls"]["metric_interpretation_provider_submissions"], 1)
        self.assertEqual(metrics["provider_calls"]["jev_requests"], 1)
        self.assertEqual(metrics["pipeline_calls"]["schema_discovery"], 1)
        report = SCORER.render_report({"cases": [case]}, scored, {
            "experiment_id": "pilot", "status": "completed", "application_revision": "abc",
            "provider": "cloudflare", "model": "test-model",
            "database_classification": "frozen-analytics-snapshot",
            "database_role_read_only": True, "dataset_fingerprint_sha256": "fingerprint",
            "dirty_worktree": True, "source_fingerprint_sha256": "source-fingerprint",
        })
        self.assertIn("Provider/model: `cloudflare` / `test-model`", report)
        self.assertIn("JEV availability: **FAILED** (HTTP 402)", report)
        self.assertIn("Worktree dirty: `True`", report)

    def test_not_run_cases_are_excluded_from_quality_denominators(self):
        data = {
            "cases": [
                {"id": case["id"], "status": "NOT_RUN", "failure_class": "environment_blocker"}
                for case in CASE_SET["cases"]
            ]
        }
        result = SCORER.score_experiment(CASE_SET, data)
        for metric in result["metrics"].values():
            if isinstance(metric, dict) and "denominator" in metric:
                self.assertEqual(metric["denominator"], 0)
        self.assertEqual(result["metrics"]["latency_ms"]["sample_count"], 0)

    def test_provider_totals_exclude_pipeline_calls_and_label_fallback_subset(self):
        data = {"cases": [{
            "id": "P01", "status": "executed",
            "calls": {
                "general_sql_generation": 2,
                "metric_interpretation": 1,
                "jev_attempts": 1,
                "local_codex_fallback_calls": 1,
                "provider_fallback_calls": 1,
                "schema_discovery": 1,
                "repository_execution": 1,
                "fixed_compiler_plans": 1,
            },
        }]}
        metrics = SCORER.score_experiment(CASE_SET, data)["metrics"]
        self.assertEqual(metrics["provider_calls"], {
            "sql_generation_provider_submissions": 2,
            "metric_interpretation_provider_submissions": 1,
            "jev_requests": 1,
            "local_codex_fallback_calls": 1,
            "total_model_calls": 5,
            "secondary_sql_provider_fallback_submissions": 1,
        })
        self.assertEqual(metrics["pipeline_calls"]["schema_discovery"], 1)
        self.assertEqual(metrics["pipeline_calls"]["repository_execution"], 1)


if __name__ == "__main__":
    unittest.main()
