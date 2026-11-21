"""Regression checks for the versioned v3.1 benchmark; never runs the held-out SQL Agent."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "artifacts/sql-agent-bussiness/40-case-v3"
HERE = ROOT / "artifacts/sql-agent-bussiness/40-case-v3-1"


def read(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def digest(data):
    return hashlib.sha256(json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


CASES = read("cases_v3_1_draft.json")
GOLD = read("gold_sql_v3_1_draft.json")
RESULTS = read("gold_results_v3_1_provisional.json")
ORIGINAL_CASES = json.loads((OLD / "cases_v3_draft.json").read_text(encoding="utf-8"))
ORIGINAL_GOLD = json.loads((OLD / "gold_sql_v3_draft.json").read_text(encoding="utf-8"))
BY_ID = {item["id"]: item for item in CASES["cases"]}
GOLD_BY_ID = {item["id"]: item for item in GOLD["cases"]}
RESULT_BY_ID = {item["id"]: item for item in RESULTS["cases"]}
spec = importlib.util.spec_from_file_location("benchmark_scorer_v3", OLD / "scorer_v3.py")
assert spec is not None and spec.loader is not None
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


class V31ContractTests(unittest.TestCase):
    def test_distribution_references_hash_and_human_gate(self):
        self.assertEqual(len(CASES["cases"]), 40)
        self.assertEqual(len(GOLD["cases"]), 30)
        self.assertEqual(len(RESULTS["cases"]), 30)
        self.assertEqual(CASES["status"], "DRAFT_PENDING_HUMAN_REVIEW")
        self.assertEqual(GOLD["review_status"], "PENDING_TWO_INDEPENDENT_REVIEWERS")
        self.assertEqual(GOLD["independent_review_approvals"], 0)
        self.assertFalse(GOLD["human_approval_claimed"])
        self.assertFalse(RESULTS["heldout_agent_executed"])
        self.assertEqual(RESULTS["independent_review_approvals"], 0)
        self.assertEqual(digest(CASES), GOLD["case_set_sha256"])
        self.assertEqual(digest(CASES), RESULTS["case_set_sha256"])
        self.assertEqual(digest([
            {"id": g["id"], "sql": g["sql"], "parameters": g["parameters"]}
            for g in GOLD["cases"]
        ]), RESULTS["gold_sql_definition_sha256"])
        self.assertEqual(
            hashlib.sha256((HERE / "gold_sql_v3_1_draft.json").read_bytes()).hexdigest(),
            RESULTS["gold_sql_draft_file_sha256"],
        )
        self.assertEqual(
            hashlib.sha256((HERE / "cases_v3_1_draft.json").read_bytes()).hexdigest(),
            RESULTS["revised_artifact_hashes"]["cases_v3_1_draft_sha256"],
        )

    def test_all_stored_gold_rows_match_revised_contract(self):
        self.assertEqual(sum(i["row_count"] for i in RESULTS["cases"]), 404)
        self.assertEqual(set(GOLD_BY_ID), set(RESULT_BY_ID))
        for ident, case in BY_ID.items():
            self.assertEqual(case["review_status"], "PENDING_TWO_INDEPENDENT_REVIEWERS")
            if case["expected_behavior"] != "execute":
                self.assertNotIn(ident, GOLD_BY_ID)
                continue
            self.assertIn(ident, RESULT_BY_ID)
            r, g = RESULT_BY_ID[ident], GOLD_BY_ID[ident]
            self.assertEqual(r["sql"], g["sql"])
            self.assertEqual(r["parameters"], g["parameters"])
            self.assertEqual(r["columns"], case["output_contract"]["columns"])
            self.assertEqual(r["row_count"], len(r["rows"]))
            self.assertTrue(all(list(row) == r["columns"] for row in r["rows"]))
            self.assertEqual(r["result_sha256"], digest({"columns": r["columns"], "rows": r["rows"]}))

    def test_unrequested_columns_removed_without_changing_questions(self):
        exclusions = {
            "B40-002": "completed_shipment_count",
            "B40-021": "observed_product_count",
            "B40-024": "observed_products",
        }
        old_by_id = {c["id"]: c for c in ORIGINAL_CASES["cases"]}
        for ident, col in exclusions.items():
            self.assertEqual(BY_ID[ident]["question"], old_by_id[ident]["question"])
            self.assertNotIn(col, BY_ID[ident]["output_contract"]["columns"])
            self.assertNotIn(col, GOLD_BY_ID[ident]["sql"])
            self.assertNotIn(col, RESULT_BY_ID[ident]["columns"])

    def test_stale_metadata_is_repaired(self):
        self.assertIn("Hai Phong", BY_ID["B40-006"]["required_metric_or_intent"])
        self.assertIn("25-34", BY_ID["B40-006"]["required_metric_or_intent"])
        self.assertIn("commerce.geography.city", BY_ID["B40-006"]["required_columns"])
        self.assertNotIn("commerce.geography.region", BY_ID["B40-006"]["required_columns"])
        self.assertIn("no year grouping", BY_ID["B40-017"]["required_metric_or_intent"])
        self.assertIn("top two", BY_ID["B40-029"]["required_metric_or_intent"])
        self.assertEqual(BY_ID["B40-029"]["top_n"], 2)

    def test_only_explicit_rankings_are_order_sensitive(self):
        expected = {"B40-011", "B40-012", "B40-013", "B40-014",
                    "B40-015", "B40-029", "B40-030"}
        actual = {c["id"] for c in CASES["cases"]
                  if c["expected_behavior"] == "execute" and c["output_contract"]["ordered"]}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 7)
        self.assertEqual(sum(c["output_contract"]["ordered"] for c in ORIGINAL_CASES["cases"]
                             if c["expected_behavior"] == "execute"), 26)

    def test_aliases_have_no_collisions(self):
        for case in CASES["cases"]:
            if case["expected_behavior"] != "execute":
                continue
            seen = {c.casefold() for c in case["output_contract"]["columns"]}
            for canonical, alts in case["column_aliases"].items():
                self.assertIn(canonical, case["output_contract"]["columns"])
                for alias in alts:
                    self.assertNotIn(alias.casefold(), seen)
                    seen.add(alias.casefold())

    def test_shuffled_unranked_case_passes_and_explicit_rank_fails(self):
        for ident, expected in (("B40-001", True), ("B40-012", False)):
            row = RESULT_BY_ID[ident]
            compared = scorer.compare_business_results(
                BY_ID[ident], row["rows"],
                {"columns": row["columns"], "rows": list(reversed(row["rows"]))},
            )
            self.assertEqual(compared["business_rows_match"], expected)

    def test_synonym_alias_passes_business_match_but_not_strict_alias_diagnostic(self):
        row = RESULT_BY_ID["B40-004"]
        altered = [{"month": r["month"], "aov": r["average_order_value"]} for r in row["rows"]]
        compared = scorer.compare_business_results(
            BY_ID["B40-004"], row["rows"],
            {"columns": ["month", "aov"], "rows": altered},
        )
        self.assertTrue(compared["business_rows_match"])
        self.assertFalse(compared["strict_schema_match"])

    def test_wrong_values_and_missing_required_columns_fail(self):
        row = RESULT_BY_ID["B40-021"]
        incorrect = [dict(x) for x in row["rows"]]
        incorrect[0]["stockout_product_count"] = 97
        compared = scorer.compare_business_results(
            BY_ID["B40-021"], row["rows"], {"columns": row["columns"], "rows": incorrect},
        )
        self.assertFalse(compared["business_rows_match"])
        missing = scorer.compare_business_results(
            BY_ID["B40-021"], row["rows"],
            {"columns": ["category"], "rows": [{"category": r["category"]} for r in row["rows"]]},
        )
        self.assertFalse(missing["business_rows_match"])

    def test_old_gold_artifacts_preserved_for_independent_review(self):
        original_by_id = {x["id"]: x for x in ORIGINAL_GOLD["cases"]}
        for ident in set(GOLD_BY_ID) - {"B40-002", "B40-021", "B40-024"}:
            self.assertEqual(GOLD_BY_ID[ident]["sql"], original_by_id[ident]["sql"])
            self.assertEqual(GOLD_BY_ID[ident]["parameters"], original_by_id[ident]["parameters"])


if __name__ == "__main__":
    unittest.main()
