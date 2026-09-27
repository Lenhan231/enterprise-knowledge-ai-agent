import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluate_app_qa.py"
SPEC = importlib.util.spec_from_file_location("evaluate_app_qa", SCRIPT)
evaluate_app_qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate_app_qa)


class AppQAEvaluationTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
