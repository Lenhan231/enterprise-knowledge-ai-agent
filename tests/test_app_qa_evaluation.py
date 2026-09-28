import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluate_app_qa.py"
SPEC = importlib.util.spec_from_file_location("evaluate_app_qa", SCRIPT)
evaluate_app_qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate_app_qa)


class AppQAEvaluationTest(unittest.TestCase):
    def test_parser_accepts_case_id_filter(self):
        args = evaluate_app_qa.build_parser().parse_args(["--case-id", "employee-vinamilk-store-return-policy"])

        self.assertEqual(args.case_id, ["employee-vinamilk-store-return-policy"])

    def test_output_probe_uses_requested_parent_and_creates_output_path(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "report.json"

            prepared = evaluate_app_qa.prepare_output(output)

            self.assertEqual(prepared, output)
            self.assertTrue(prepared.parent.is_dir())
            self.assertTrue(prepared.is_file())

    def test_live_suite_can_write_a_distinct_report_without_overwriting_default(self):
        args = evaluate_app_qa.build_parser().parse_args([
            "--cases", "custom-cases.json",
            "--output", "artifacts/evaluation/retry.json",
        ])

        self.assertEqual(args.cases, Path("custom-cases.json"))
        self.assertEqual(args.output, Path("artifacts/evaluation/retry.json"))
        self.assertEqual(evaluate_app_qa.build_parser().parse_args([]).output, evaluate_app_qa._OUTPUT)

    def test_live_suite_stops_after_provider_rate_limit(self):
        self.assertTrue(evaluate_app_qa.should_stop_on_rate_limit(429))
        self.assertFalse(evaluate_app_qa.should_stop_on_rate_limit(503))

    def test_case_requires_route_facts_source_and_consistent_citations(self):
        case = {
            "id": "finance-2024", "role": "finance_analyst", "question": "Revenue?",
            "expected_agent": "report", "expected_document_id": "VNM-AR-2024-VI",
            "expected_key_facts": ["61 824", "9 453"], "expect_insufficient": False,
        }
        payload = {
            "answer": "Revenue 61,824 and profit 9,453 billion VND [Nguồn: S1]",
            "agent": "report", "insufficient_context": False,
            "citations": [{"id": "S1", "document_id": "VNM-AR-2024-VI", "page_number": 12}],
        }

        result = evaluate_app_qa.score_case(case, payload)

        self.assertTrue(result["passed"])
        self.assertTrue(all(result["checks"].values()))

    def test_case_fails_if_answer_is_uncited_or_uses_wrong_source(self):
        case = {
            "id": "finance-2024", "role": "finance_analyst", "question": "Revenue?",
            "expected_agent": "report", "expected_document_id": "VNM-AR-2024-VI",
            "expected_key_facts": ["61 824"], "expect_insufficient": False,
        }
        payload = {
            "answer": "Revenue 61,824 [S1]", "agent": "report", "insufficient_context": False,
            "citations": [{"id": "S1", "document_id": "OTHER", "page_number": 2}],
        }

        result = evaluate_app_qa.score_case(case, payload)

        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["expected_source_document"])

    def test_denial_case_requires_abstention_and_no_citations(self):
        case = {
            "id": "employee-denial", "role": "employee", "question": "Revenue?",
            "expected_agent": "hybrid", "expected_document_id": None,
            "expect_insufficient": True,
        }
        payload = {
            "answer": "Insufficient information.", "agent": "hybrid",
            "insufficient_context": True, "citations": [],
        }

        result = evaluate_app_qa.score_case(case, payload)

        self.assertTrue(result["passed"])

    def test_unsupported_retention_case_is_labeled_to_abstain(self):
        import json

        path = Path(__file__).resolve().parents[1] / "data/evaluation/vinamilk_unsupported_abstention_case.json"
        case = json.loads(path.read_text())["cases"][0]
        payload = {
            "answer": "Insufficient information in the retrieved documents.",
            "agent": "knowledge", "insufficient_context": True, "citations": [],
        }

        result = evaluate_app_qa.score_case(case, payload)

        self.assertTrue(result["passed"])

    def test_limited_policy_answer_requires_scope_disclosure(self):
        case = {
            "id": "employee-access", "role": "employee", "question": "Search for the employee access policy",
            "expected_agent": "knowledge", "expected_document_id": "VNM-CODE-2025-EN",
            "expected_key_fact_groups": [["manager and IT"]],
            "expected_disclosure_groups": [["Code of Conduct"], ["not included in the retrieved documents"]],
        }
        payload = {
            "answer": "The Code of Conduct requires manager and IT approval. The separate policy is not included in the retrieved documents [S1].",
            "agent": "knowledge", "insufficient_context": False,
            "citations": [{"id": "S1", "document_id": "VNM-CODE-2025-EN", "official_url": "https://example.com/code.pdf"}],
        }
        self.assertTrue(evaluate_app_qa.score_case(case, payload)["passed"])
        payload["answer"] = "Employees need manager and IT approval [S1]."
        self.assertFalse(evaluate_app_qa.score_case(case, payload)["checks"]["required_scope_disclosures"])


if __name__ == "__main__":
    unittest.main()
