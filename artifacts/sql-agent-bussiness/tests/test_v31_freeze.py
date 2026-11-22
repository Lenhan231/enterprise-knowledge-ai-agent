import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
V31 = ROOT / "artifacts/sql-agent-bussiness/40-case-v3-1"
PACKAGE_ROOT = ROOT / "artifacts/sql-agent-bussiness"
sys.path[:0] = [str(ROOT / "src"), str(PACKAGE_ROOT)]
spec = importlib.util.spec_from_file_location("sql_benchmark_runner_freeze_test", PACKAGE_ROOT / "runner.py")
RUNNER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RUNNER)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class V31FreezeRecordTests(unittest.TestCase):
    def test_consensus_is_case_complete_and_provenance_limitations_are_explicit(self):
        adjudication = json.loads(
            (V31 / "ADJUDICATION_V3_1_CONSENSUS_20261122.json").read_text(encoding="utf-8")
        )
        cases = json.loads((V31 / "cases_v3_1_draft.json").read_text(encoding="utf-8"))
        self.assertEqual(adjudication["reviewed_case_count"], 40)
        self.assertEqual(adjudication["disagreement_count"], 0)
        self.assertEqual(
            {item["case_id"] for item in adjudication["case_decisions"]},
            {item["id"] for item in cases["cases"]},
        )
        self.assertTrue(all(item["consensus"] == "APPROVE" for item in adjudication["case_decisions"]))
        self.assertFalse(adjudication["reviewer_2"]["identity_authenticated"])
        self.assertFalse(adjudication["reviewer_2"]["independence_authenticated"])

    def test_freeze_manifest_pins_exact_inputs_and_read_only_database_fingerprint(self):
        manifest = json.loads((V31 / "FREEZE_MANIFEST_V3_1_FROZEN_V1.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["freeze_status"], "FROZEN")
        self.assertTrue(manifest["database"]["role_read_only"])
        self.assertTrue(manifest["database"]["fingerprint_matches_gold"])
        self.assertEqual(manifest["review"]["consensus_approvals"], 40)
        self.assertEqual(manifest["review"]["disagreements"], 0)
        self.assertTrue(manifest["review"]["limitations_disclosed"])
        for relative, expected in manifest["artifact_paths_sha256"].items():
            self.assertEqual(sha256(ROOT / relative), expected, relative)

    def test_runner_accepts_the_committed_freeze_and_gold_inputs(self):
        manifest = json.loads((V31 / "FREEZE_MANIFEST_V3_1_FROZEN_V1.json").read_text(encoding="utf-8"))
        cases_path = V31 / "cases_v3_1_draft.json"
        gold_path = V31 / "gold_sql_v3_1_draft.json"
        reference_path = V31 / "gold_results_v3_1_provisional.json"
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        result = RUNNER.validate_v31_contract(
            cases, reference, manifest, cases_path=cases_path,
            gold_sql_path=gold_path, reference_path=reference_path,
            scorer_path=V31 / "scorer_v3_1.py",
        )
        self.assertEqual(result["distribution"]["execute"], 30)

    def test_review_page_shows_consensus_but_labels_reviewer_two(self):
        page = (V31 / "SEMANTIC_REVIEW_V3_1.html").read_text(encoding="utf-8")
        self.assertIn('fetch("FREEZE_MANIFEST_V3_1_FROZEN_V1.json"', page)
        self.assertIn("FROZEN v1", page)
        self.assertIn("Reviewer 2 user-reported", page)
        self.assertIn("chưa xác thực độc lập", page)


if __name__ == "__main__":
    unittest.main()
