import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/agents/evaluate_app_qa.py"
SPEC = importlib.util.spec_from_file_location("evaluate_app_qa", SCRIPT)
evaluate_app_qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate_app_qa)


class AppQAEvaluationTest(unittest.TestCase):
    def test_parser_accepts_case_id_filter(self):
        args = evaluate_app_qa.build_parser().parse_args(["--case-id", "INV-01"])

        self.assertEqual(args.case_id, ["INV-01"])

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
            "id": "INV-01", "role": "analyst", "question": "How should inventory be planned across locations?",
            "expected_agent": "report", "expected_document_id": "SHOPIFY-MULTI-LOCATION-INVENTORY-2026",
            "expected_key_facts": ["location", "inventory"], "expect_insufficient": False,
        }
        payload = {
            "answer": "Shopify describes reviewing inventory by location before planning [Nguồn: S1]",
            "agent": "report", "insufficient_context": False,
            "citations": [{"id": "S1", "document_id": "SHOPIFY-MULTI-LOCATION-INVENTORY-2026", "source_url": "https://help.shopify.com/"}],
        }

        result = evaluate_app_qa.score_case(case, payload)

        self.assertTrue(result["passed"])
        self.assertTrue(all(result["checks"].values()))

    def test_case_fails_if_answer_is_uncited_or_uses_wrong_source(self):
        case = {
            "id": "INV-01", "role": "analyst", "question": "How should inventory be planned across locations?",
            "expected_agent": "report", "expected_document_id": "SHOPIFY-MULTI-LOCATION-INVENTORY-2026",
            "expected_key_facts": ["location"], "expect_insufficient": False,
        }
        payload = {
            "answer": "Review inventory by location [S1]", "agent": "report", "insufficient_context": False,
            "citations": [{"id": "S1", "document_id": "OTHER", "source_url": "https://example.com/"}],
        }

        result = evaluate_app_qa.score_case(case, payload)

        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["expected_source_document"])

    def test_denial_case_requires_abstention_and_no_citations(self):
        case = {
            "id": "analyst-abstention", "role": "analyst", "question": "Should stock be transferred without location-level evidence?",
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
        case = {
            "id": "LOG-03", "role": "analyst",
            "question": "Which carrier should be selected for a new network design?",
            "expected_agent": "report", "expected_document_id": None,
            "expect_insufficient": True,
        }
        payload = {
            "answer": "Insufficient information in the retrieved documents.",
            "agent": "report", "insufficient_context": True, "citations": [],
        }

        result = evaluate_app_qa.score_case(case, payload)

        self.assertTrue(result["passed"])

    def test_limited_policy_answer_requires_scope_disclosure(self):
        case = {
            "id": "commerce-policy-scope", "role": "analyst",
            "question": "What operating policy should Commerce Demo use for supplier delivery capacity?",
            "expected_agent": "knowledge", "expected_document_id": "WMT-GFR-SUPPLIER-ONBOARDING-2025",
            "expected_key_fact_groups": [["facilities", "daily capacity"]],
            "expected_disclosure_groups": [["Walmart"], ["not Commerce Demo policy"]],
        }
        payload = {
            "answer": "Walmart's supplier checklist asks for facilities and daily capacity; it is not Commerce Demo policy [S1].",
            "agent": "knowledge", "insufficient_context": False,
            "citations": [{"id": "S1", "document_id": "WMT-GFR-SUPPLIER-ONBOARDING-2025", "source_url": "https://corporate.walmart.com/content/dam/corporate/documents/suppliers/apply-to-be-a-supplier/supplier-checklist.pdf"}],
        }
        self.assertTrue(evaluate_app_qa.score_case(case, payload)["passed"])
        payload["answer"] = "Use the Walmart checklist as our own policy [S1]."
        self.assertFalse(evaluate_app_qa.score_case(case, payload)["checks"]["required_scope_disclosures"])


if __name__ == "__main__":
    unittest.main()
