"""Offline contract checks for the 15-case Commerce SQL ground-truth suite."""

import json
from pathlib import Path
import unittest

from sqlglot import exp, parse_one


SUITE = Path(__file__).parent / "fixtures" / "commerce_15_tables_hard_v1.json"


class HardGroundTruthSuiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(SUITE.read_text(encoding="utf-8"))

    def test_suite_has_unique_ids_and_complete_case_contracts(self):
        cases = self.data["cases"]
        ids = [case["id"] for case in cases]
        self.assertEqual(self.data["suite"], "commerce_15_tables_hard_v1")
        self.assertEqual(len(cases), 15)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {f"E{i:02d}" for i in range(1, 16)})
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["question"].strip())
                self.assertTrue(case["expected_tables"])
                self.assertIn(case["expected_behavior"], {"answer_with_sql", "abstain_or_qualify"})
                self.assertIsInstance(case["expected_result"], (list, dict))

    def test_sql_cases_have_parseable_read_queries_and_abstentions_have_no_sql(self):
        for case in self.data["cases"]:
            with self.subTest(case=case["id"]):
                if case["expected_behavior"] == "answer_with_sql":
                    self.assertTrue((case["gold_sql"] or "").strip())
                    query = parse_one(case["gold_sql"], read="postgres")
                    self.assertEqual(query.key, "select")
                    used_tables = {
                        f"{table.db}.{table.name}".casefold()
                        for table in query.find_all(exp.Table)
                        if table.db
                    }
                    self.assertLessEqual(used_tables, {table.casefold() for table in case["expected_tables"]})
                    self.assertEqual(case["expected_row_count"], len(case["expected_result"]))
                else:
                    self.assertFalse((case["gold_sql"] or "").strip())
                    self.assertEqual(case["expected_result"].get("verdict"), "not_identifiable")
                    self.assertEqual(case["expected_row_count"], 0)


if __name__ == "__main__":
    unittest.main()
