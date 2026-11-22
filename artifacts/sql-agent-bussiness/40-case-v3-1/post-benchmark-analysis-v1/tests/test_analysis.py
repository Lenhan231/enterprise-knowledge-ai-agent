"""Synthetic regression tests for the offline post-benchmark analysis helpers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ANALYSIS_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sql_post_benchmark_analysis", ANALYSIS_DIR / "analyze.py")
analysis = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(analysis)


class StrictMonthNormalizationTests(unittest.TestCase):
    def test_only_exact_utc_month_boundary_is_normalized(self):
        self.assertEqual(
            analysis._strict_month_value("2025-03-01T00:00:00+00:00"),
            ("2025-03-01", "normalized_exact_utc_month_start"),
        )

    def test_rejects_naive_non_utc_non_midnight_and_non_boundary_timestamps(self):
        cases = {
            "2025-03-01T00:00:00": "timezone_missing",
            "2025-03-01T00:00:00-05:00": "non_utc_offset",
            "2025-03-01T01:00:00+00:00": "not_month_boundary",
            "2025-03-02T00:00:00+00:00": "not_month_boundary",
        }
        for value, expected_state in cases.items():
            with self.subTest(value=value):
                self.assertEqual(analysis._strict_month_value(value), (value, expected_state))

    def test_date_and_non_date_columns_must_both_match(self):
        expected = [{"month": "2025-03-01", "sessions": 9}]
        equivalent = [{"month": "2025-03-01T00:00:00Z", "sessions": 9}]
        wrong_value = [{"month": "2025-03-01T00:00:00Z", "sessions": 10}]
        self.assertTrue(analysis.compare_rows_multiset(expected, equivalent, date_column="month")["matched"])
        self.assertFalse(analysis.compare_rows_multiset(expected, wrong_value, date_column="month")["matched"])

    def test_row_multiset_preserves_duplicate_multiplicity(self):
        expected = [{"month": "2025-03-01"}, {"month": "2025-03-01"}]
        actual = [{"month": "2025-03-01"}]
        self.assertFalse(analysis.compare_rows_multiset(expected, actual)["matched"])

    def test_null_is_not_zero(self):
        self.assertTrue(analysis.compare_rows_multiset([{"metric": None}], [{"metric": None}])["matched"])
        self.assertFalse(analysis.compare_rows_multiset([{"metric": None}], [{"metric": 0}])["matched"])

    def test_numeric_tolerance_is_bounded(self):
        expected = [{"average": 100}]
        self.assertTrue(analysis.compare_rows_multiset(
            expected, [{"average": "100.01"}], tolerance={"absolute": "0.01"}
        )["matched"])
        self.assertFalse(analysis.compare_rows_multiset(
            expected, [{"average": "100.011"}], tolerance={"absolute": "0.01"}
        )["matched"])


class ExplicitAliasMappingTests(unittest.TestCase):
    def test_observed_alias_maps_only_with_explicit_directional_mapping(self):
        expected = [{"return_count": 4}]
        actual = [{"return_records": 4}]
        self.assertFalse(analysis.compare_rows_multiset(expected, actual)["matched"])
        self.assertTrue(analysis.compare_rows_multiset(
            expected, actual, aliases={"return_records": "return_count"}
        )["matched"])
        self.assertFalse(analysis.compare_rows_multiset(
            expected, [{"return_records": 5}], aliases={"return_records": "return_count"}
        )["matched"])


class RankingContractTests(unittest.TestCase):
    SQL = """SELECT p.product_id AS product_id, p.cogs AS catalog_cogs
FROM commerce.products AS p
ORDER BY p.cogs DESC, p.product_id ASC
LIMIT 5;"""

    def test_frozen_ranking_contract_passes(self):
        result = analysis.verify_b011_ranking_sql(self.SQL)
        self.assertTrue(result["passed"], result)
        self.assertTrue(all(result["checks"].values()))

    def test_wrong_metric_direction_tie_limit_and_population_fail(self):
        mutations = {
            "wrong metric": self.SQL.replace("p.cogs", "p.price", 1),
            "wrong direction": self.SQL.replace("DESC", "ASC"),
            "wrong tie break": self.SQL.replace("p.product_id ASC", "p.product_id DESC"),
            "wrong top n": self.SQL.replace("LIMIT 5", "LIMIT 10"),
            "extra filter": self.SQL.replace("ORDER BY", "WHERE p.is_active = TRUE\nORDER BY"),
            "extra join": self.SQL.replace(
                "ORDER BY", "LEFT JOIN commerce.orders AS o ON o.customer_id = p.product_id\nORDER BY"
            ),
            "extra output": self.SQL.replace(
                "p.cogs AS catalog_cogs", "p.cogs AS catalog_cogs, p.brand AS brand"
            ),
            "grouping changes grain": self.SQL.replace(
                "ORDER BY", "GROUP BY p.product_id, p.cogs\nORDER BY"
            ),
        }
        for label, sql in mutations.items():
            with self.subTest(label=label):
                self.assertFalse(analysis.verify_b011_ranking_sql(sql)["passed"])


class UnsupportedShapeAndRepairTests(unittest.TestCase):
    def test_shape_valid_clarification_can_still_be_semantically_wrong(self):
        case = {"expected_behavior": "clarify"}
        observation = {
            "status": "clarification_required",
            "answer": "Choose whether to use the unavailable campaign_spend field.",
            "metadata": {"clarification_options": ["Use campaign_spend"]},
            "execution_events": [],
        }
        self.assertTrue(analysis._valid_unsupported_shape(case, observation))

    def test_provider_failure_and_repository_execution_are_not_valid_abstentions(self):
        case = {"expected_behavior": "clarify"}
        base = {
            "status": "clarification_required",
            "answer": "The requested dimension is unavailable in the approved schema.",
            "metadata": {"clarification_options": []},
            "execution_events": [],
        }
        self.assertFalse(analysis._valid_unsupported_shape(
            case, {**base, "status": "provider_error", "failure_class": "provider_failure"}
        ))
        self.assertFalse(analysis._valid_unsupported_shape(
            case, {**base, "execution_events": [{"status": "executed", "security_validated": True}]}
        ))

    def test_repair_denominator_excludes_unsupported_cases(self):
        data = {
            "cases": {
                "supported_recovered": {"expected_behavior": "execute"},
                "supported_failed": {"expected_behavior": "execute"},
                "unsupported": {"expected_behavior": "abstain_without_query"},
            },
            "observations": {
                "supported_recovered": {"calls": {"sql_repair": 1}},
                "supported_failed": {"calls": {"sql_repair": 2}},
                "unsupported": {"calls": {"sql_repair": 1}},
            },
            "comparisons": {
                "supported_recovered": {"business_end_to_end": {"decision": "PASS"}},
                "supported_failed": {"business_end_to_end": {"decision": "FAIL"}},
            },
            "scores": {"metrics": {"repair_recovery": {"numerator": 0, "denominator": 0}}},
        }
        result = analysis.repair_analysis(data)
        self.assertEqual(result["runner_reported_repair_count"], 3)
        self.assertEqual(result["supported_repair_denominator"], 2)
        self.assertEqual(result["e2e_recovered_case_ids"], ["supported_recovered"])
        self.assertEqual(result["repaired_unsupported_cases_excluded"], ["unsupported"])


class ReproducibilityManifestTests(unittest.TestCase):
    @staticmethod
    def manifest(version, score=10):
        return (json.dumps({"python_version": version, "score": score},
                           ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")

    def test_runtime_version_is_provenance_only(self):
        name = "REPRODUCIBILITY_MANIFEST.json"
        baseline = self.manifest("3.11.16")
        self.assertTrue(analysis.matches_generated_artifact(name, baseline, self.manifest("3.11.17")))
        self.assertFalse(analysis.matches_generated_artifact(name, baseline, self.manifest("3.11.17", 11)))
        self.assertFalse(analysis.matches_generated_artifact(name, self.manifest("invalid"), baseline))
        self.assertFalse(analysis.matches_generated_artifact(name, b"not JSON", baseline))
        self.assertFalse(analysis.matches_generated_artifact("ERROR_ANALYSIS_REPORT.md", baseline,
                                                            self.manifest("3.11.17")))


if __name__ == "__main__":
    unittest.main()
