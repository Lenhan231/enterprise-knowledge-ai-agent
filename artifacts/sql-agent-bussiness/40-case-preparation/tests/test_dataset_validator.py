import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataset_validator import (
    EXPECTED_CATEGORY_COUNTS,
    EXPECTED_BEHAVIOR_COUNTS,
    validate_dataset,
    validate_gold_results,
    validate_gold_sql_drafts,
)


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _dataset():
    categories = [category for category, count in EXPECTED_CATEGORY_COUNTS.items()
                  for _ in range(count)]
    behaviors = (["execute"] * EXPECTED_BEHAVIOR_COUNTS["execute"]
                 + ["clarify"] * EXPECTED_BEHAVIOR_COUNTS["clarify"]
                 + ["abstain_without_query"] * EXPECTED_BEHAVIOR_COUNTS["abstain_without_query"])
    cases = []
    for index, (category, behavior) in enumerate(zip(categories, behaviors), start=1):
        case = {
            "id": f"B40-{index:03d}", "question": f"Unique test question {index}",
            "category": category, "language": "en", "difficulty": "medium",
            "expected_behavior": behavior, "required_metric_or_intent": "test metric",
            "required_population": [], "required_filters": [], "time_scope": {"kind": "all"},
            "grouping_grain": [], "ranking": [], "top_n": None,
            "required_source_tables": [], "required_columns": [], "required_joins": [],
            "provenance": {"source": "test-only fixture"},
            "output_contract": {"columns": ["value"], "max_rows": 1},
            "numeric_tolerance": {"identifiers_and_counts": 0, "relative": 0},
            "null_policy": "preserve NULL",
            "oracle_status": "PENDING_HUMAN_REVIEW",
            "review_status": "PENDING_TWO_INDEPENDENT_REVIEWERS",
            "gold_sql": None, "gold_parameters": None, "gold_result": None,
            "expected_clarification_or_abstention": None if behavior == "execute" else "Ask a defined question.",
            "semantic_review": {"pilot_overlap": {"status": "reviewed_no_direct_overlap"}},
        }
        if category == "sql_followup_context":
            state = {"metric": "revenue", "time_scope": "2024"}
            case["conversation_setup"] = {
                "mode": "frozen_context_injection", "prior_user_question": "Total revenue in 2024?",
                "semantic_context": state, "semantic_context_sha256": _hash(state),
                "assistant_output_injected": False,
            }
        cases.append(case)
    return {"format_version": "test", "cases": cases}


class DatasetValidatorTests(unittest.TestCase):
    def test_minimal_40_case_draft_passes(self):
        result = validate_dataset(_dataset())
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["case_count"], 40)

    def test_duplicate_id_is_rejected(self):
        data = _dataset()
        data["cases"][1]["id"] = data["cases"][0]["id"]
        self.assertTrue(any("IDs must be unique" in item for item in validate_dataset(data)["errors"]))

    def test_missing_approved_column_is_rejected(self):
        data = _dataset()
        data["cases"][0]["required_columns"] = ["commerce.orders.email"]
        self.assertTrue(any("not in the application allowlist" in item
                            for item in validate_dataset(data)["errors"]))

    def test_unapproved_join_is_rejected(self):
        data = _dataset()
        data["cases"][0]["required_joins"] = ["commerce.orders.email=commerce.customers.email"]
        self.assertTrue(any("not approved" in item for item in validate_dataset(data)["errors"]))

    def test_followup_context_hash_and_fabricated_assistant_output_are_rejected(self):
        data = _dataset()
        case = next(item for item in data["cases"] if item["category"] == "sql_followup_context")
        case["conversation_setup"]["semantic_context_sha256"] = "0" * 64
        case["conversation_setup"]["assistant_output_injected"] = True
        errors = validate_dataset(data)["errors"]
        self.assertTrue(any("context hash mismatch" in item for item in errors))
        self.assertTrue(any("invented prior assistant results" in item for item in errors))

    def test_wrong_expected_behavior_distribution_is_rejected(self):
        data = _dataset()
        data["cases"][0]["expected_behavior"] = "clarify"
        self.assertTrue(any("expected-behavior distribution mismatch" in item
                            for item in validate_dataset(data)["errors"]))

    def test_unavailable_snapshot_is_rejected(self):
        data = _dataset()
        data["cases"][0]["time_scope"] = {"kind": "snapshot", "snapshot_dates": ["2026-11-12"]}
        preflight = {"database_role_read_only": True, "fingerprint_sha256": "f" * 64,
                     "schema": {"tables": {}, "primary_keys": {}, "foreign_keys": []},
                     "targeted_checks": {"inventory_null_counts_by_snapshot": [
                         {"snapshot_date": "2026-11-13"}]}}
        self.assertTrue(any("was not observed" in item for item in validate_dataset(data, preflight)["errors"]))

    def test_snapshot_range_requires_both_exact_endpoints(self):
        data = _dataset()
        data["cases"][0]["time_scope"] = {
            "kind": "snapshot_range", "start": "2025-09-30", "end_inclusive": "2025-11-30",
            "date_field": "commerce.inventory.snapshot_date",
        }
        preflight = {
            "database_role_read_only": True, "fingerprint_sha256": "f" * 64,
            "date_columns": ["commerce.inventory.snapshot_date"],
            "schema": {"tables": {}, "primary_keys": {}, "foreign_keys": []},
            "targeted_checks": {"inventory_null_counts_by_snapshot": [
                {"snapshot_date": "2025-09-30"}, {"snapshot_date": "2025-10-31"},
            ]},
        }
        errors = validate_dataset(data, preflight)["errors"]
        self.assertTrue(any("endpoints must both be observed" in item for item in errors))

    def test_time_field_must_be_a_live_date_column(self):
        data = _dataset()
        data["cases"][0]["time_scope"] = {
            "kind": "calendar_range", "date_field": "commerce.orders.not_a_date",
            "start": "2025-01-01", "end_exclusive": "2026-01-01",
        }
        preflight = {
            "database_role_read_only": True, "fingerprint_sha256": "f" * 64,
            "date_columns": ["commerce.orders.order_date"],
            "schema": {"tables": {}, "primary_keys": {}, "foreign_keys": []},
            "targeted_checks": {"inventory_null_counts_by_snapshot": []},
        }
        self.assertTrue(any("not a live DATE column" in item
                            for item in validate_dataset(data, preflight)["errors"]))

    def test_invalid_top_n_is_rejected(self):
        data = _dataset()
        data["cases"][0]["top_n"] = 201
        self.assertTrue(any("top_n must be null or" in item for item in validate_dataset(data)["errors"]))

    def test_all_thirty_authored_gold_drafts_pass_structural_contract(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "cases_v2_draft.json").read_text(encoding="utf-8"))
        gold = json.loads((root / "gold_sql_draft.json").read_text(encoding="utf-8"))
        self.assertTrue(gold["author_identity"])
        self.assertFalse(gold["human_approval_claimed"])
        result = validate_gold_sql_drafts(dataset, gold)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["status"], "PASS_STRUCTURAL_DRAFT")
        self.assertEqual(result["validated_count"], 30)

    def test_corrected_candidates_preserve_question_scope_and_followup_context(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "cases_v2_draft.json").read_text(encoding="utf-8"))
        gold = json.loads((root / "gold_sql_draft.json").read_text(encoding="utf-8"))
        cases = {item["id"]: item for item in dataset["cases"]}
        sql = {item["id"]: item for item in gold["cases"]}

        aov = cases["B40-004"]
        self.assertEqual(aov["time_scope"]["start"], "2025-01-01")
        self.assertIn("2025-01-01", sql["B40-004"]["parameters"])
        self.assertIn("2026-01-01", sql["B40-004"]["parameters"])

        refund = cases["B40-008"]
        self.assertEqual(refund["output_contract"]["columns"], ["return_reason", "refund_amount"])
        self.assertNotIn("return_id", refund["required_columns"])
        self.assertNotIn("COUNT(", sql["B40-008"]["sql"].upper())

        inventory = cases["B40-009"]
        self.assertIn("Outdoor", inventory["question"])
        self.assertEqual(sql["B40-009"]["parameters"][1], "Outdoor")

        rating = cases["B40-018"]
        self.assertEqual(rating["output_contract"]["columns"], ["category", "avg_rating"])
        self.assertNotIn("COUNT(", sql["B40-018"]["sql"].upper())

        monthly = cases["B40-028"]["conversation_setup"]
        self.assertIn("tháng", monthly["prior_user_question"].casefold())
        self.assertIn("calendar month", monthly["semantic_context"]["grouping"])
        ranking = cases["B40-029"]["conversation_setup"]
        self.assertIn("xếp hạng", ranking["prior_user_question"].casefold())
        self.assertIn("return_reason", ranking["semantic_context"]["grouping"])

    def test_provisional_reference_rows_match_current_gold_and_frozen_snapshot(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "cases_v2_draft.json").read_text(encoding="utf-8"))
        gold = json.loads((root / "gold_sql_draft.json").read_text(encoding="utf-8"))
        results = json.loads((root / "gold_results_provisional.json").read_text(encoding="utf-8"))
        preflight = json.loads((root / "database_preflight_candidate_checks_621d9984.json").read_text(encoding="utf-8"))
        result = validate_gold_results(dataset, gold, results, preflight)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["status"], "PASS_PROVISIONAL_REFERENCE")
        self.assertEqual(result["validated_count"], 30)

    def test_reference_results_reject_heldout_agent_calls_and_stale_case_hash(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "cases_v2_draft.json").read_text(encoding="utf-8"))
        gold = json.loads((root / "gold_sql_draft.json").read_text(encoding="utf-8"))
        results = json.loads((root / "gold_results_provisional.json").read_text(encoding="utf-8"))
        preflight = json.loads((root / "database_preflight_candidate_checks_621d9984.json").read_text(encoding="utf-8"))
        results["sql_agent_generation_calls"] = 1
        results["case_set_sha256"] = "0" * 64
        errors = validate_gold_results(dataset, gold, results, preflight)["errors"]
        self.assertTrue(any("must remain unexecuted" in error for error in errors))
        self.assertTrue(any("does not match the current candidate set" in error for error in errors))

    def test_reference_rows_match_snapshot_data_integrity_checks(self):
        root = Path(__file__).resolve().parents[1]
        cases = json.loads((root / "gold_results_provisional.json").read_text(encoding="utf-8"))
        preflight = json.loads((root / "database_preflight_candidate_checks_621d9984.json").read_text(encoding="utf-8"))
        rows = {item["id"]: item["rows"] for item in cases["cases"]}
        checks = preflight["targeted_checks"]

        self.assertGreater(checks["sales_profit_filter_checks_2024"]["cogs_gt_revenue_days"], 0)
        self.assertGreater(rows["B40-007"][0]["cogs"], rows["B40-007"][0]["revenue"])
        outdoor = next(row for row in checks["inventory_units_sold_by_category_2025_10_31"]
                       if row["category"] == "Outdoor")
        self.assertEqual(rows["B40-009"][0]["units_sold"], outdoor["units_sold"])
        self.assertEqual(rows["B40-010"][0]["order_count"], checks["paid_search_mobile_orders_2025"])
        self.assertEqual(sum(row["returned_units"] for row in rows["B40-016"]),
                         sum(row["returned_units"] for row in rows["B40-017"]))
        shipment = checks["shipment_geography_coverage_2025"]
        self.assertEqual(shipment["unmapped_zip_rows"], 0)
        self.assertEqual(sum(row["fee_observation_count"] for row in rows["B40-020"]),
                         shipment["shipping_fee_observations"])

        snapshots = {row["snapshot_date"]: row for row in checks["inventory_null_counts_by_snapshot"]}
        self.assertEqual(len(rows["B40-022"]), len(snapshots))
        for row in rows["B40-022"]:
            source = snapshots[row["snapshot_date"]]
            self.assertEqual(row["products_with_days_of_supply"], source["nonnull_days_of_supply"])
            self.assertEqual(row["products_without_days_of_supply"], source["null_days_of_supply"])
        self.assertTrue(all(row["stock_delta"] == row["stock_after"] - row["stock_before"]
                            for row in rows["B40-023"]))
        self.assertTrue(all(row["observed_products"] == 97 for row in rows["B40-024"]))

        nulls = {row["category"]: row for row in checks["null_days_of_supply_by_category_2025_10_31"]}
        for row in rows["B40-025"]:
            source = nulls[row["category"]]
            self.assertIsNone(row["average_days_of_supply"])
            self.assertEqual(row["nonnull_product_count"], source["nonnull_count"])
            self.assertEqual(row["null_product_count"], source["null_count"])

    def test_gold_query_security_violation_is_rejected(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "cases_v2_draft.json").read_text(encoding="utf-8"))
        gold = json.loads((root / "gold_sql_draft.json").read_text(encoding="utf-8"))
        gold["cases"][0]["sql"] = "DELETE FROM commerce.sales WHERE revenue > 0"
        result = validate_gold_sql_drafts(dataset, gold)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("SQL validation failed" in item and "SELECT" in item
                            for item in result["errors"]))

    def test_gold_query_parameter_contract_is_enforced(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "cases_v2_draft.json").read_text(encoding="utf-8"))
        gold = json.loads((root / "gold_sql_draft.json").read_text(encoding="utf-8"))
        gold["cases"][0]["parameters"] = ["2024-01-01"]
        result = validate_gold_sql_drafts(dataset, gold)
        self.assertTrue(any("placeholders" in item and "supplied values" in item
                            for item in result["errors"]))

    def test_gold_date_predicates_must_match_declared_calendar_scope(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "cases_v2_draft.json").read_text(encoding="utf-8"))
        gold = json.loads((root / "gold_sql_draft.json").read_text(encoding="utf-8"))
        item = next(row for row in gold["cases"] if row["id"] == "B40-004")
        item["sql"] = item["sql"].replace("o.order_date >= $2", "o.order_date >= $3")
        item["sql"] = item["sql"].replace("o.order_date < $3", "o.order_date < $2")
        result = validate_gold_sql_drafts(dataset, gold)
        self.assertTrue(any("do not preserve declared scope" in error for error in result["errors"]))

    def test_gold_ordering_and_top_n_must_match_candidate_contract(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "cases_v2_draft.json").read_text(encoding="utf-8"))
        gold = json.loads((root / "gold_sql_draft.json").read_text(encoding="utf-8"))
        item = next(row for row in gold["cases"] if row["id"] == "B40-005")
        item["sql"] = item["sql"].replace("ORDER BY refund_amount DESC, month ASC", "ORDER BY month ASC, refund_amount DESC")
        item["sql"] = item["sql"].replace("LIMIT 1", "LIMIT 2")
        errors = validate_gold_sql_drafts(dataset, gold)["errors"]
        self.assertTrue(any("does not match ranking contract" in error for error in errors))
        self.assertTrue(any("does not match TOP-N contract" in error for error in errors))

    def test_gold_query_output_contract_is_enforced(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "cases_v2_draft.json").read_text(encoding="utf-8"))
        gold = json.loads((root / "gold_sql_draft.json").read_text(encoding="utf-8"))
        gold["cases"][0]["sql"] = gold["cases"][0]["sql"].replace("AS sessions", "AS visitors")
        result = validate_gold_sql_drafts(dataset, gold)
        self.assertTrue(any("output columns" in item for item in result["errors"]))

    def test_gold_ids_must_cover_all_supported_cases(self):
        root = Path(__file__).resolve().parents[1]
        dataset = json.loads((root / "cases_v2_draft.json").read_text(encoding="utf-8"))
        gold = json.loads((root / "gold_sql_draft.json").read_text(encoding="utf-8"))
        gold["cases"].pop()
        result = validate_gold_sql_drafts(dataset, gold)
        self.assertTrue(any("match exactly the execute" in item for item in result["errors"]))


if __name__ == "__main__":
    unittest.main()
