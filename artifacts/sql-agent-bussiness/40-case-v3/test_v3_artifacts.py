from __future__ import annotations

import hashlib
import json
import unittest
from decimal import Decimal
from pathlib import Path

from dataset_validator import validate_dataset, validate_gold_sql_drafts


HERE = Path(__file__).resolve().parent
V2 = HERE.parent / "40-case-preparation"
CASES = json.loads((HERE / "cases_v3_draft.json").read_text(encoding="utf-8"))
GOLD = json.loads((HERE / "gold_sql_v3_draft.json").read_text(encoding="utf-8"))
PREFLIGHT = json.loads((HERE / "database_preflight_v3.json").read_text(encoding="utf-8"))
PROFILE = json.loads((HERE / "candidate_selectivity_v3.json").read_text(encoding="utf-8"))
GOLD_RESULTS = json.loads((HERE / "gold_results_v3_provisional.json").read_text(encoding="utf-8"))
MUTATIONS = json.loads((HERE / "mutation_results_v3_1.json").read_text(encoding="utf-8"))
MUTATIONS_V3_0_PATH = HERE / "mutation_results.json"
MANIFEST = json.loads((HERE / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))
BY_ID = {case["id"]: case for case in CASES["cases"]}
GOLD_BY_ID = {item["id"]: item for item in GOLD["cases"]}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value) -> str:
    def json_value(item):
        if isinstance(item, Decimal):
            return str(item)
        raise TypeError(type(item).__name__)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=json_value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class V3ArtifactTests(unittest.TestCase):
    def test_v2_inputs_are_preserved_byte_for_byte(self):
        self.assertEqual(
            file_sha256(V2 / "cases_v2_draft.json"),
            "6036477937037c12dd90c10a1b00c90735ec8d48ba08ebbb8775f217f8a01677",
        )
        self.assertEqual(
            file_sha256(V2 / "gold_sql_draft.json"),
            "422d82e809b646477af4295e3e01561b27c08ed3e505f4bafa2928fe3ea45e6d",
        )
        self.assertEqual(
            file_sha256(V2 / "gold_results_provisional.json"),
            "56dbddbf953d411c538bb0b7eef3db15cbb23358a5d56221463f50decd9b60bb",
        )

    def test_case_distribution_and_gold_structure_pass(self):
        case_validation = validate_dataset(CASES, PREFLIGHT)
        gold_validation = validate_gold_sql_drafts(CASES, GOLD, PREFLIGHT)
        self.assertEqual(case_validation["status"], "PASS_STRUCTURAL_DRAFT")
        self.assertEqual(gold_validation["status"], "PASS_STRUCTURAL_DRAFT")
        self.assertEqual(case_validation["case_count"], 40)
        self.assertEqual(case_validation["expected_behavior_counts"], {
            "execute": 30,
            "clarify": 5,
            "abstain_without_query": 5,
        })
        self.assertEqual(gold_validation["validated_count"], 30)

    def test_fingerprint_matches_reviewed_v2_snapshot_and_read_only_role(self):
        self.assertEqual(PREFLIGHT["status"], "VERIFIED_READ_ONLY_PREFLIGHT")
        self.assertTrue(PREFLIGHT["database_role_read_only"])
        self.assertEqual(
            PREFLIGHT["fingerprint_sha256"],
            "dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028",
        )
        self.assertEqual(PROFILE["database_fingerprint_sha256"], PREFLIGHT["fingerprint_sha256"])

    def test_b40_002_missing_delivery_date_is_material(self):
        profile = PROFILE["checks"]["shipments_2025"][0]
        self.assertEqual(profile["missing_delivery_date"], 7)
        self.assertGreater(profile["recorded_delivery_date"], 0)
        self.assertIn("missing_delivery_date_count", BY_ID["B40-002"]["output_contract"]["columns"])
        self.assertEqual(GOLD_BY_ID["B40-002"]["parameters"], ["2025-01-01", "2026-01-01"])

    def test_b40_006_both_filters_are_selective(self):
        profile = PROFILE["checks"]["customer_profile_selectivity"][0]
        self.assertEqual(profile["all_2024_signups"], 711)
        self.assertEqual(profile["hai_phong"], 79)
        self.assertEqual(profile["age_25_34"], 143)
        self.assertEqual(profile["intersection"], 17)
        sql = GOLD_BY_ID["B40-006"]["sql"]
        self.assertIn("g.city = $1", sql)
        self.assertIn("c.age_group = $2", sql)

    def test_b40_015_limit_reduces_four_categories_to_three(self):
        self.assertEqual(len(PROFILE["checks"]["delivered_categories_2025"]), 4)
        self.assertEqual(BY_ID["B40-015"]["top_n"], 3)
        self.assertTrue(GOLD_BY_ID["B40-015"]["sql"].endswith("LIMIT 3"))

    def test_b40_017_period_has_repeated_source_rows(self):
        profile = PROFILE["checks"]["returns_repeated_products_2023_2025"][0]
        self.assertEqual(profile["repeated_product_groups"], 56)
        self.assertGreater(profile["max_source_rows"], 1)
        self.assertEqual(BY_ID["B40-017"]["time_scope"]["start"], "2023-01-01")
        self.assertEqual(GOLD_BY_ID["B40-017"]["parameters"], ["2023-01-01", "2026-01-01"])

    def test_b40_020_does_not_claim_null_shipping_fee_coverage(self):
        profile = PROFILE["checks"]["shipping_fee_nulls_2025"][0]
        self.assertEqual(profile["shipment_rows"], 728)
        self.assertEqual(profile["missing_shipping_fee"], 0)
        self.assertIn("no claim", BY_ID["B40-020"]["provenance"]["change_note"])

    def test_b40_008_records_non_null_reason_limitation(self):
        profile = PROFILE["checks"]["return_reason_nulls_2023_2025"]
        self.assertEqual(sum(row["null_reason"] for row in profile), 0)
        self.assertIn("cannot test the NULL exclusion", BY_ID["B40-008"]["provenance"]["change_note"])

    def test_b40_021_requires_true_not_merely_non_null(self):
        profile = PROFILE["checks"]["stockout_boolean_2026_11_13"][0]
        self.assertEqual(profile["true_rows"], 17)
        self.assertEqual(profile["false_rows"], 80)
        self.assertTrue(any(
            "stockout_flag = TRUE" in item for item in BY_ID["B40-021"]["required_filters"]
        ))
        self.assertIn("i.stockout_flag = TRUE", GOLD_BY_ID["B40-021"]["sql"])

    def test_b40_023_records_equal_snapshot_membership_limitation(self):
        profile = PROFILE["checks"]["snapshot_overlap_2025_09_30_2025_10_31"]
        self.assertEqual(profile["before_products"], 97)
        self.assertEqual(profile["after_products"], 97)
        self.assertEqual(profile["common_products"], 97)
        self.assertEqual(profile["before_only"], 0)
        self.assertEqual(profile["after_only"], 0)
        self.assertIn("observationally redundant", BY_ID["B40-023"]["provenance"]["change_note"])

    def test_b40_027_uses_2025_and_14_non_delivered_orders(self):
        statuses = {item["order_status"]: item["order_count"] for item in PROFILE["checks"]["order_status_2025"]}
        self.assertEqual(statuses["delivered"], 719)
        self.assertEqual(sum(statuses.values()), 733)
        self.assertEqual(GOLD_BY_ID["B40-027"]["parameters"], ["delivered", "2025-01-01", "2026-01-01"])
        self.assertIn("year=2025", BY_ID["B40-027"]["required_filters"][0])

    def test_b40_028_is_aligned_monthly_pair_with_null_preservation(self):
        case = BY_ID["B40-028"]
        gold_sql = GOLD_BY_ID["B40-028"]["sql"]
        self.assertEqual(case["output_contract"]["columns"], [
            "month", "gross_profit_2023", "gross_profit_2024", "difference_2024_minus_2023",
        ])
        self.assertIn("GROUP BY EXTRACT(YEAR FROM s.date), EXTRACT(MONTH FROM s.date)", gold_sql)
        self.assertIn("FILTER (WHERE m.sales_year = 2023)", gold_sql)
        self.assertIn("FILTER (WHERE m.sales_year = 2024)", gold_sql)
        self.assertNotIn("COALESCE", gold_sql.upper())
        self.assertIn("return NULL", case["null_policy"])

    def test_b40_029_top_two_is_stricter_than_three_available_reasons(self):
        self.assertEqual(len(PROFILE["checks"]["return_reasons_2024"]), 3)
        self.assertEqual(BY_ID["B40-029"]["top_n"], 2)
        self.assertTrue(GOLD_BY_ID["B40-029"]["sql"].endswith("LIMIT 2"))

    def test_b40_033_clarification_covers_product_snapshot_and_realtime(self):
        expected = BY_ID["B40-033"]["expected_clarification_or_abstention"].casefold()
        for phrase in ("product_id", "snapshot", "thời gian thực", "real-time"):
            self.assertIn(phrase.casefold(), expected)
        self.assertEqual(BY_ID["B40-033"]["expected_behavior"], "clarify")
        self.assertNotIn("B40-033", GOLD_BY_ID)

    def test_no_independent_approval_is_claimed(self):
        self.assertIs(GOLD["human_approval_claimed"], False)
        self.assertEqual(GOLD["review_status"], "PENDING_TWO_INDEPENDENT_REVIEWERS")
        self.assertEqual(GOLD["independent_review_approvals"], 0)
        self.assertFalse(CASES["heldout_agent_executed"])

    def test_provisional_gold_results_match_all_30_draft_queries(self):
        self.assertEqual(GOLD_RESULTS["status"], "PROVISIONAL_COMPLETE_NOT_APPROVED")
        self.assertEqual(GOLD_RESULTS["execution_count"], 30)
        self.assertEqual(GOLD_RESULTS["execution_failures"], [])
        self.assertFalse(GOLD_RESULTS["heldout_agent_executed"])
        self.assertEqual(GOLD_RESULTS["sql_agent_generation_calls"], 0)
        self.assertTrue(GOLD_RESULTS["database_role_read_only"])
        self.assertEqual(GOLD_RESULTS["database_fingerprint_sha256"], PREFLIGHT["fingerprint_sha256"])
        for relative_path, expected_sha256 in GOLD_RESULTS["source_hashes"].items():
            with self.subTest(source=relative_path):
                self.assertEqual(file_sha256(HERE.parents[2] / relative_path), expected_sha256)
        results = {item["id"]: item for item in GOLD_RESULTS["cases"]}
        self.assertEqual(set(results), set(GOLD_BY_ID))
        for case_id, gold in GOLD_BY_ID.items():
            with self.subTest(case=case_id):
                result = results[case_id]
                self.assertEqual(result["sql"], gold["sql"])
                self.assertEqual(result["parameters"], gold["parameters"])
                self.assertEqual(result["columns"], BY_ID[case_id]["output_contract"]["columns"])
                self.assertEqual(result["row_count"], len(result["rows"]))
                self.assertIn(result["status"], {"PROVISIONAL_NOT_APPROVED", "PROVISIONAL_EMPTY_NOT_APPROVED"})
                self.assertEqual(result["human_review"]["reviewer_1"], "PENDING")
                self.assertEqual(result["human_review"]["reviewer_2"], "PENDING")
                self.assertEqual(result["result_sha256"], canonical_sha256({
                    "columns": result["columns"], "rows": result["rows"],
                }))

    def test_mutation_evidence_is_complete_read_only_and_keeps_equivalent_variants_visible(self):
        self.assertEqual(MUTATIONS["status"], "COMPLETE_NOT_APPROVED")
        self.assertEqual(MUTATIONS["protocol_version"], "3.1.0")
        self.assertEqual(MUTATIONS["mutations_attempted"], 28)
        self.assertEqual(MUTATIONS["failures"], [])
        self.assertEqual(MUTATIONS["database_fingerprint_sha256"], PREFLIGHT["fingerprint_sha256"])
        self.assertTrue(MUTATIONS["database_role_read_only"])
        self.assertEqual(MUTATIONS["database_write_attempts"], 0)
        self.assertFalse(MUTATIONS["heldout_agent_executed"])
        self.assertEqual(MUTATIONS["sql_agent_generation_calls"], 0)
        self.assertEqual(MUTATIONS["result_based_mutation_detection"]["numerator"], 23)
        self.assertEqual(MUTATIONS["result_based_mutation_detection"]["denominator"], 26)
        self.assertEqual(MUTATIONS["observationally_equivalent"], 3)
        self.assertEqual(len(MUTATIONS["mutations"]), 28)
        self.assertEqual(sum(item["status"] == "VALIDATOR_REJECTED" for item in MUTATIONS["mutations"]), 2)
        self.assertEqual(MUTATIONS["validator_detection"]["business_semantic_validator"]["numerator"], 1)
        self.assertEqual(MUTATIONS["validator_detection"]["business_semantic_validator"]["denominator"], 1)
        self.assertTrue(MUTATIONS["captured_at_utc"])
        self.assertTrue(MUTATIONS["run_id"])
        for relative_path, expected_sha256 in MUTATIONS["source_hashes"].items():
            with self.subTest(source=relative_path):
                self.assertEqual(file_sha256(HERE.parents[2] / relative_path), expected_sha256)

    def test_previous_mutation_evidence_remains_byte_for_byte_preserved(self):
        self.assertEqual(
            file_sha256(MUTATIONS_V3_0_PATH),
            "da21a3176d3a6bf57cc58a1dbaa1f495fa3a10c70e2e666623c8c2b68b535a78",
        )
        self.assertEqual(json.loads(MUTATIONS_V3_0_PATH.read_text(encoding="utf-8"))["protocol_version"], "3.0.0")

    def test_freeze_manifest_is_explicitly_draft_and_hashes_review_artifacts(self):
        self.assertEqual(MANIFEST["status"], "PENDING_INDEPENDENT_REVIEW")
        self.assertEqual(MANIFEST["freeze_status"], "DRAFT_NOT_FROZEN")
        self.assertTrue(MANIFEST["readiness"]["ready_for_independent_human_review"])
        self.assertFalse(MANIFEST["readiness"]["ready_for_40_case_execution"])
        self.assertFalse(MANIFEST["cohort"]["heldout_sql_agent_executed"])
        self.assertEqual(MANIFEST["oracle"]["independent_review_approvals"], 0)
        self.assertNotIn("artifacts/sql-agent-bussiness/40-case-v3/FREEZE_MANIFEST.json",
                         MANIFEST["artifact_hashes_excluding_this_manifest"])
        # The v3 manifest predates the AI-review links appended to REVIEW_CHECKLIST.md.
        # Verify its recorded digest against the exact historical bytes, preserved
        # from Git commit 281aed8, rather than rewriting the old manifest or
        # incorrectly treating the current checklist as the original snapshot.
        historical_checklist = (
            "artifacts/sql-agent-bussiness/40-case-v3/REVIEW_CHECKLIST.md"
        )
        archived_checklist = (
            HERE.parent / "40-case-v3-1" / "historical"
            / "REVIEW_CHECKLIST_at_v3_manifest.md"
        )
        for relative_path, expected_sha256 in MANIFEST["artifact_hashes_excluding_this_manifest"].items():
            with self.subTest(artifact=relative_path):
                source = (
                    archived_checklist
                    if relative_path == historical_checklist
                    else HERE.parents[2] / relative_path
                )
                self.assertEqual(file_sha256(source), expected_sha256)

        current_checklist = (HERE / "REVIEW_CHECKLIST.md").read_text(encoding="utf-8")
        self.assertIn("AI_ASSISTED_SEMANTIC_REVIEW_2026-11-21.md", current_checklist)
        self.assertIn("human", current_checklist.casefold())


if __name__ == "__main__":
    unittest.main()
