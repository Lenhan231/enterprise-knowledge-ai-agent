import importlib.util
import unittest
from pathlib import Path


SCORER = Path(__file__).resolve().parents[1] / "40-case-v3-1/scorer_v3_4.py"
spec = importlib.util.spec_from_file_location("format_rescore", SCORER)
rescore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rescore)


class FormatRescoreTest(unittest.TestCase):
    def test_only_exact_utc_month_starts_are_normalized(self):
        case = {"output_contract": {"columns": ["month"]}}
        expected = [{"month": "2024-02-01"}]
        rows = [{"month": "2024-02-01T00:00:00+00:00"},
                {"month": "2024-02-01T00:00:01+00:00"},
                {"month": "2024-02-01T00:00:00+01:00"},
                {"month": "2024-02-02T00:00:00+00:00"}]
        observed = {"columns": ["month"], "rows": rows}
        normalized = rescore.normalize_month_starts(case, expected, observed)
        self.assertEqual(normalized["rows"], [expected[0], *rows[1:]])
        self.assertEqual(observed["rows"][0]["month"], "2024-02-01T00:00:00+00:00")
        self.assertIs(rescore.normalize_month_starts(case, [{"month": 2}], observed), observed)

    def test_alias_review_is_bound_to_observed_sql_parameters_and_semantic_pass(self):
        case = {"id": "c", "output_contract": {"columns": ["return_count"]}}
        observation = {"id": "c", "sql": "SELECT COUNT(*) AS returns FROM commerce.returns",
                       "parameters": [2025], "columns": ["returns"]}
        review = {"case_id": "c", "query_sha256": rescore.query_sha256(observation),
                  "aliases": {"returns": "return_count"}, "evidence": "The source has one row per return."}
        revised = rescore.with_reviewed_aliases(case, observation, review, semantic_pass=True)
        self.assertEqual(revised["column_aliases"], {"return_count": ["returns"]})
        self.assertIs(rescore.with_reviewed_aliases(case, observation, review, semantic_pass=False), case)
        changed = {**observation, "parameters": [2024]}
        self.assertIs(rescore.with_reviewed_aliases(case, changed, review, semantic_pass=True), case)
        self.assertNotIn("column_aliases", case)
