from __future__ import annotations

import json
import unittest
from pathlib import Path

import sqlglot

from core.agents.sql.metric_validation import MetricDefinitionError, validate_population_contract
from followup_adapter import adapt_followup_case
from mutation_probes_v3 import construct_mutation, mutation_catalog


HERE = Path(__file__).resolve().parent
GOLD = json.loads((HERE / "gold_sql_v3_draft.json").read_text(encoding="utf-8"))
GOLD_BY_ID = {item["id"]: item for item in GOLD["cases"]}


class MutationCatalogTests(unittest.TestCase):
    def test_required_error_categories_are_probed(self):
        categories = {item["category"] for item in mutation_catalog()}
        self.assertTrue({
            "missing_population_filter", "wrong_filter_value", "missing_time_restriction",
            "incorrect_date_boundary", "wrong_aggregation", "missing_required_grouping",
            "wrong_ranking_direction", "missing_limit", "incorrect_limit", "incorrect_join_key",
            "join_fanout_aggregation", "incorrect_null_handling", "wrong_inventory_snapshot",
            "wrong_followup_time_scope", "missing_snapshot_membership_condition", "wrong_tie_break_direction",
        } <= categories)

    def test_mutations_are_unique_and_parse_as_single_sql_statements(self):
        specs = mutation_catalog()
        self.assertGreaterEqual(len(specs), 20)
        self.assertEqual(len({item["id"] for item in specs}), len(specs))
        for spec in specs:
            with self.subTest(mutation=spec["id"]):
                mutation = construct_mutation(GOLD_BY_ID, spec)
                parsed = sqlglot.parse(mutation["sql"], read="postgres")
                self.assertTrue(mutation["construction_verified"])
                self.assertEqual(len(parsed), 1)
                self.assertIsNotNone(parsed[0])

    def test_observationally_weak_null_case_has_both_omission_and_inversion(self):
        specs = {item["id"]: item for item in mutation_catalog()}
        omitted = construct_mutation(GOLD_BY_ID, specs["M008-01-missing-nonnull-filter"])
        inverted = construct_mutation(GOLD_BY_ID, specs["M008-02-inverted-null-filter"])
        self.assertNotIn("r.return_reason IS NOT NULL", omitted["sql"])
        self.assertIn("r.return_reason IS NULL", inverted["sql"])

    def test_join_key_probe_has_explicit_approved_relationship_oracle(self):
        spec = next(item for item in mutation_catalog() if item["id"] == "M006-03-wrong-join-key")
        mutation = construct_mutation(GOLD_BY_ID, spec)
        self.assertEqual(spec["validator_oracle"], "approved_join_relationship")
        self.assertIn("g.zip = c.customer_id", mutation["sql"])

    def test_wrong_time_followups_change_only_bound_date_scope(self):
        by_id = {item["id"]: item for item in mutation_catalog()}
        gold_026 = GOLD_BY_ID["B40-026"]
        mutation = construct_mutation(GOLD_BY_ID, by_id["M026-01-wrong-inherited-year"])
        self.assertEqual(mutation["sql"], gold_026["sql"])
        self.assertEqual(mutation["parameters"], ["2025-01-01", "2026-01-01"])

    def test_delivered_population_validator_accepts_gold_and_rejects_missing_filter_mutation(self):
        case = next(item for item in json.loads((HERE / "cases_v3_draft.json").read_text())["cases"]
                    if item["id"] == "B40-027")
        question = adapt_followup_case(case).question
        gold = GOLD_BY_ID["B40-027"]
        validate_population_contract(gold["sql"], question, tuple(gold["parameters"]), ())
        spec = next(item for item in mutation_catalog() if item["id"] == "M027-01-missing-delivered-filter")
        mutation = construct_mutation(GOLD_BY_ID, spec)
        self.assertEqual(mutation["parameters"], ["2025-01-01", "2026-01-01"])
        self.assertNotIn("order_status", mutation["sql"])
        with self.assertRaises(MetricDefinitionError):
            validate_population_contract(mutation["sql"], question, tuple(mutation["parameters"]), ())

    def test_missing_city_filter_keeps_other_bound_filters(self):
        spec = next(item for item in mutation_catalog() if item["id"] == "M006-01-missing-city-filter")
        mutation = construct_mutation(GOLD_BY_ID, spec)
        self.assertNotIn("g.city =", mutation["sql"])
        self.assertIn("c.age_group = $1", mutation["sql"])
        self.assertEqual(mutation["parameters"], ["25-34", "2024-01-01", "2025-01-01"])

    def test_missing_top_n_keeps_executor_safe_row_cap(self):
        by_id = {item["id"]: item for item in mutation_catalog()}
        for mutation_id in ("M015-03-missing-limit", "M029-01-missing-top-two-limit"):
            with self.subTest(mutation=mutation_id):
                spec = by_id[mutation_id]
                mutation = construct_mutation(GOLD_BY_ID, spec)
                self.assertTrue(mutation["sql"].endswith("LIMIT 200"))
                self.assertIsNone(spec["validator_oracle"])


if __name__ == "__main__":
    unittest.main()
