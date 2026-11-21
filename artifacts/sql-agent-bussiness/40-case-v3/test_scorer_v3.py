from __future__ import annotations

import unittest

from scorer_v3 import compare_business_results, score


def case(case_id="A", behavior="execute", **extra):
    return {
        "id": case_id,
        "expected_behavior": behavior,
        "output_contract": {"columns": ["customer_id", "revenue"], "ordered": False},
        "numeric_tolerance": {"identifiers_and_counts": 0, "absolute": 0.01, "relative": 0},
        **extra,
    }


def experiment(case_id, status, **extra):
    return {"id": case_id, "status": status, **extra}


class ScorerV3Tests(unittest.TestCase):
    def test_answerable_executed_correctly(self):
        cases = {"cases": [case()]}
        reference = {"cases": [{"id": "A", "rows": [{"customer_id": 7, "revenue": "10.00"}]}]}
        result = score(cases, reference, {"cases": [experiment(
            "A", "executed", sql="SELECT ...", sql_semantic_valid=True,
            columns=["customer_id", "revenue"], rows=[{"customer_id": 7, "revenue": "10.004"}],
        )]})
        self.assertEqual(result["metrics"]["supported_business_end_to_end_accuracy"], {
            "numerator": 1, "denominator": 1, "value": 1.0,
        })
        self.assertEqual(result["metrics"]["business_result_accuracy"]["value"], 1.0)

    def test_answerable_clarification_is_false_clarification(self):
        result = score(
            {"cases": [case()]},
            {"cases": [{"id": "A", "rows": []}]},
            {"cases": [experiment("A", "clarification_required", sql=None)]},
        )
        self.assertEqual(result["metrics"]["false_clarification_abstention"]["numerator"], 1)
        self.assertEqual(result["metrics"]["supported_noncompletion"]["numerator"], 1)

    def test_validation_failure_is_noncompletion_not_false_clarification(self):
        result = score(
            {"cases": [case()]},
            {"cases": [{"id": "A", "rows": []}]},
            {"cases": [experiment("A", "failed", error_type="SQLValidationError")]},
        )
        self.assertEqual(result["metrics"]["false_clarification_abstention"]["numerator"], 0)
        self.assertEqual(result["metrics"]["validation_blocked_supported"]["numerator"], 1)
        self.assertEqual(result["metrics"]["supported_noncompletion"]["numerator"], 1)

    def test_repair_exhaustion_does_not_count_as_recovery(self):
        result = score(
            {"cases": [case()]},
            {"cases": [{"id": "A", "rows": []}]},
            {"cases": [experiment("A", "failed", repair_count=2, error_type="SQLValidationError")]},
        )
        self.assertEqual(result["metrics"]["repair_recovery"], {
            "numerator": 0, "denominator": 1, "value": 0.0,
        })

    def test_wrong_business_rows_fail_e2e_and_result_accuracy(self):
        result = score(
            {"cases": [case()]},
            {"cases": [{"id": "A", "rows": [{"customer_id": 7, "revenue": "10.00"}]}]},
            {"cases": [experiment(
                "A", "executed", sql_semantic_valid=True,
                columns=["customer_id", "revenue"],
                rows=[{"customer_id": 7, "revenue": "40.00"}],
            )]},
        )
        self.assertEqual(result["metrics"]["supported_business_end_to_end_accuracy"]["numerator"], 0)
        self.assertEqual(result["metrics"]["business_result_accuracy"]["numerator"], 0)

    def test_unsupported_safe_abstention_is_separate_success(self):
        result = score(
            {"cases": [case("U", "abstain_without_query")]},
            {"cases": [{"id": "U", "rows": []}]},
            {"cases": [experiment(
                "U", "abstained", answer="The approved schema does not support this request.", sql=None,
            )]},
        )
        self.assertEqual(result["metrics"]["valid_clarification_abstention"]["value"], 1.0)
        self.assertEqual(result["metrics"]["overall_task_success_rate"]["value"], 1.0)

    def score_unsupported_response(self, **fields):
        return score(
            {"cases": [case("U", "clarify")]},
            {"cases": [{"id": "U", "rows": []}]},
            {"cases": [experiment("U", "clarification_required", **fields)]},
        )["metrics"]["valid_clarification_abstention"]

    def test_valid_clarification_without_choices(self):
        metric = self.score_unsupported_response(
            answer="Warehouse inventory is not available in the approved schema.", sql=None,
        )
        self.assertEqual(metric, {"numerator": 1, "denominator": 1, "value": 1.0})

    def test_valid_clarification_with_one_or_three_choices(self):
        answer = "Which available scope would you like?"
        for choices in (["Product snapshot"], ["Product snapshot", "Current stock", "Cancel"]):
            with self.subTest(choices=choices):
                self.assertEqual(
                    self.score_unsupported_response(
                        answer=answer, sql=None, metadata={"clarification_options": choices},
                    )["value"],
                    1.0,
                )

    def test_invalid_clarification_choices_are_not_valid_abstentions(self):
        answer = "Please choose an available data scope."
        for choices in (
            ["one", "two", "three", "four"],
            [""],
            ["valid", 7],
            [{"label": "nested"}],
        ):
            with self.subTest(choices=choices):
                metric = self.score_unsupported_response(
                    answer=answer, sql=None, metadata={"clarification_options": choices},
                )
                self.assertEqual(metric["numerator"], 0)

    def test_missing_answer_sql_or_execution_invalidates_unsupported_response(self):
        cases = (
            {"answer": "  ", "sql": None},
            {"answer": "Unsupported fields.", "sql": "SELECT * FROM unavailable"},
            {"answer": "Unsupported fields.", "sql": None, "execution_events": [{"kind": "approved"}]},
            {"answer": "Unsupported fields.", "sql": None, "execution_events": {"kind": "approved"}},
            {"answer": "Unsupported fields.", "sql": None, "metadata": []},
        )
        for fields in cases:
            with self.subTest(fields=fields):
                metric = self.score_unsupported_response(**fields)
                self.assertEqual(metric["numerator"], 0)

    def test_provider_failure_is_not_valid_unsupported_abstention(self):
        metric = self.score_unsupported_response(
            answer="Provider unavailable.", sql=None, failure_class="provider",
        )
        self.assertEqual(metric["numerator"], 0)

    def test_failed_invalid_unsupported_clarification_is_not_valid_abstention(self):
        result = score(
            {"cases": [case("U", "clarify")]},
            {"cases": [{"id": "U", "rows": []}]},
            {"cases": [experiment("U", "failed", answer="Please clarify.",
                                   error_type="SQLValidationError")]},
        )
        self.assertEqual(result["metrics"]["valid_clarification_abstention"]["numerator"], 0)

    def test_provider_failure_is_separate_from_semantic_refusal(self):
        result = score(
            {"cases": [case()]},
            {"cases": [{"id": "A", "rows": []}]},
            {"cases": [experiment("A", "failed", error_type="ProviderTimeout")]},
        )
        self.assertEqual(result["metrics"]["provider_network_failure_count"]["count"], 1)
        self.assertEqual(result["metrics"]["false_clarification_abstention"]["numerator"], 0)

    def test_not_run_cases_are_excluded_and_zero_denominator_is_null(self):
        result = score(
            {"cases": [case()]},
            {"cases": [{"id": "A", "rows": []}]},
            {"cases": [experiment("A", "NOT RUN")]},
        )
        self.assertEqual(result["metrics"]["supported_business_end_to_end_accuracy"], {
            "numerator": 0, "denominator": 0, "value": None,
        })
        self.assertEqual(result["not_run_case_ids"], ["A"])

    def test_alias_and_exact_allowed_provenance_column_are_business_valid(self):
        item = case(
            column_aliases={"customer_id": ["buyer"]},
            allowed_provenance_columns={"snapshot_date": "2026-11-13"},
        )
        comparison = compare_business_results(
            item,
            [{"customer_id": 7, "revenue": "10.00"}],
            {
                "columns": ["buyer", "revenue", "snapshot_date"],
                "rows": [{"buyer": 7, "revenue": "10.00", "snapshot_date": "2026-11-13"}],
            },
        )
        self.assertTrue(comparison["business_rows_match"])
        self.assertFalse(comparison["strict_schema_match"])

    def test_unapproved_extra_column_fails_business_result(self):
        comparison = compare_business_results(
            case(),
            [{"customer_id": 7, "revenue": "10.00"}],
            {
                "columns": ["customer_id", "revenue", "debug"],
                "rows": [{"customer_id": 7, "revenue": "10.00", "debug": "x"}],
            },
        )
        self.assertFalse(comparison["business_rows_match"])
        self.assertEqual(comparison["unexpected_extra_columns"], ["debug"])

    def test_null_is_not_equal_to_zero(self):
        comparison = compare_business_results(
            case(),
            [{"customer_id": 7, "revenue": None}],
            {
                "columns": ["customer_id", "revenue"],
                "rows": [{"customer_id": 7, "revenue": 0}],
            },
        )
        self.assertFalse(comparison["business_rows_match"])

    def test_selector_recall_uses_successful_raw_top_five_only(self):
        cases = {"cases": [
            case("A", required_source_tables=["commerce.orders", "commerce.order_items"]),
            case("B", required_source_tables=["commerce.inventory"]),
        ]}
        result = score(
            cases,
            {"cases": []},
            {"cases": [
                experiment("A", "executed", schema_selection={
                    "schema_selector_status": "available",
                    "candidate_tables": ["commerce.orders", "commerce.products", "commerce.order_items"],
                }),
                experiment("B", "executed", schema_selection={
                    "schema_selector_status": "failed",
                    "candidate_tables": ["commerce.inventory"],
                }),
            ]},
        )
        self.assertEqual(result["metrics"]["schema_selector_raw_recall_at_5"], {
            "numerator": 2, "denominator": 2, "value": 1.0,
            "applicable_cases": 1, "status": "MEASURABLE",
        })

    def test_latency_and_provider_calls_exclude_not_run_and_do_not_double_count_fallback(self):
        result = score(
            {"cases": [case("A"), case("B"), case("C")]},
            {"cases": []},
            {"cases": [
                experiment("A", "executed", latency_ms=100, calls={
                    "general_sql_generation": 2, "provider_fallback_calls": 1,
                    "metric_interpretation": 1, "schema_selector_attempts": 2,
                    "local_codex_fallback_calls": 1,
                }),
                experiment("B", "failed", latency_ms=300, calls={"general_sql_generation": 1}),
                experiment("C", "NOT RUN", latency_ms=1, calls={"general_sql_generation": 100}),
            ]},
        )
        metrics = result["metrics"]
        self.assertEqual(metrics["latency_ms"], {
            "p50_nearest_rank": 100.0, "p95_nearest_rank": 300.0,
            "sample_count": 2, "denominator": 2,
        })
        self.assertEqual(metrics["provider_calls"], {
            "sql_generation_provider_submissions": 3,
            "metric_interpretation_provider_submissions": 1,
            "schema_selection_provider_requests": 2,
            "local_codex_fallback_calls": 1,
            "total_model_calls": 7,
            "secondary_sql_provider_fallback_submissions": 1,
        })
        self.assertEqual(metrics["pipeline_calls"]["general_sql_generation"], 3)

    def test_selector_recall_is_not_measurable_when_provider_failed(self):
        result = score(
            {"cases": [case("A", required_source_tables=["commerce.sales"])]},
            {"cases": []},
            {"cases": [experiment("A", "executed", schema_selection={
                "schema_selector_status": "failed",
                "candidate_tables": ["commerce.sales"],
            })]},
        )
        metric = result["metrics"]["schema_selector_raw_recall_at_5"]
        self.assertIsNone(metric["value"])
        self.assertEqual(metric["status"], "NOT MEASURABLE")


if __name__ == "__main__":
    unittest.main()
