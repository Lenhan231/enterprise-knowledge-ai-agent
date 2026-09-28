import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/evaluate_proposal_business_cases.py"
SPEC = importlib.util.spec_from_file_location("evaluate_proposal_business_cases", SCRIPT)
evaluation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = evaluation
SPEC.loader.exec_module(evaluation)


class ProposalBusinessAppEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        routes = json.loads((ROOT / "data/evaluation/proposal_business_route_cases.json").read_text())
        labels = json.loads((ROOT / "data/evaluation/proposal_business_case_corpus_labels.json").read_text())
        manifest = json.loads((ROOT / "data/vietnam_enterprises/manifest.json").read_text())
        cls.cases = evaluation.evaluate_coverage(routes, labels, manifest)["cases"]

    def case(self, case_id):
        return next(case for case in self.cases if case["id"] == case_id)

    def test_unsupported_case_passes_only_with_abstention_and_no_citations(self):
        result = evaluation.score_case(self.case("enterprise-knowledge-management"), {
            "answer": "Insufficient information in the indexed sources.",
            "agent": "knowledge", "insufficient_context": True, "citations": [],
        })
        self.assertTrue(result["passed"])

        result = evaluation.score_case(self.case("enterprise-knowledge-management"), {
            "answer": "A retention policy applies [S1]", "agent": "knowledge",
            "insufficient_context": False,
            "citations": [{"id": "S1", "document_id": "VNM-CODE-2025-EN"}],
        })
        self.assertFalse(result["checks"]["unsupported_case_abstains"])

    def test_partial_invoice_answer_must_use_allowed_source_and_stay_narrow(self):
        case = self.case("invoice-information-retrieval")
        abstention = evaluation.score_case(case, {
            "answer": "Insufficient information in the retrieved documents.",
            "agent": "knowledge", "insufficient_context": True, "citations": [],
        })
        self.assertFalse(abstention["passed"])
        payload = {
            "answer": "The annual report says related-party amounts were payable within 60 days from invoice date [S1]. This is not an invoice document; no invoice document was found in the retrieved sources.",
            "agent": "knowledge", "insufficient_context": False,
            "citations": [{"id": "S1", "document_id": "VNM-AR-2020-VI", "page_number": 90,
                           "excerpt": "Amounts were payable within 60 days from invoice date."}],
        }
        self.assertTrue(evaluation.score_case(case, payload)["passed"])
        payload["answer"] = "An annual report says related-party amounts were payable within 60 days from invoice date [S1]."
        self.assertFalse(evaluation.score_case(case, payload)["checks"]["invoice_document_absence_is_disclosed"])
        payload["answer"] = "The annual report says related-party amounts were payable within 60 days from invoice date [S1]. This is not an invoice document; no invoice document was found in the retrieved sources."
        payload["citations"][0]["document_id"] = "VNM-AR-2024-VI"
        self.assertFalse(evaluation.score_case(case, payload)["passed"])

    def test_employee_access_case_requires_source_scope_and_missing_policy_disclosure(self):
        case = self.case("internal-document-search")
        payload = {
            "answer": (
                "The Code of Conduct says employees receive access appropriate to their duties; "
                "exceptions require manager and IT approval. It refers to a separate Information "
                "System Policy, which is not included in the retrieved documents [S1]."
            ),
            "agent": "knowledge", "insufficient_context": False,
            "citations": [{
                "id": "S1", "document_id": "VNM-CODE-2025-EN", "page_number": 28,
                "official_url": "https://example.com/code.pdf",
            }],
        }
        self.assertTrue(evaluation.score_case(case, payload)["passed"])
        payload["answer"] = "Employee access policy says access depends on duties [S1]."
        result = evaluation.score_case(case, payload)
        self.assertFalse(result["checks"]["answer_qualifies_document_type"])
        self.assertFalse(result["checks"]["dedicated_access_policy_absence_is_disclosed"])

    def test_financial_case_checks_both_values_unit_and_source(self):
        payload = {
            "answer": "Revenue was 61,824 and profit after tax was 9,453 billion VND [S1] [S2]",
            "agent": "hybrid", "insufficient_context": False,
            "citations": [
                {"id": "S1", "document_id": "VNM-AR-2024-VI", "page_number": 2,
                 "excerpt": "Total consolidated revenue 61,824 billion VND."},
                {"id": "S2", "document_id": "VNM-AR-2024-VI", "page_number": 2,
                 "excerpt": "Consolidated profit after tax 9,453 billion VND."},
            ],
        }
        self.assertTrue(evaluation.score_case(self.case("financial-report-analysis"), payload)["passed"])
        payload["answer"] = payload["answer"].replace("9,453", "945")
        self.assertFalse(evaluation.score_case(self.case("financial-report-analysis"), payload)["passed"])

        payload["answer"] = "Revenue was 61,824 and profit after tax was 9,453 billion VND [S1] [S2]"
        payload["citations"][1]["excerpt"] = "Profit after tax 945 billion VND."
        result = evaluation.score_case(self.case("financial-report-analysis"), payload)
        self.assertFalse(result["checks"]["financial_values_in_cited_evidence"])

    def test_citations_need_a_page_or_official_source_url(self):
        result = evaluation.score_case(self.case("hr-policy-consultation"), {
            "answer": "The public report states this detail [S1]", "agent": "knowledge",
            "citations": [{"id": "S1", "document_id": "VNM-AR-2020-VI", "excerpt": "text"}],
        })
        self.assertFalse(result["checks"]["citations_have_source_locations"])

    def test_financial_value_match_requires_an_exact_number_token(self):
        self.assertTrue(evaluation._has_fact("61824", "Revenue was 61,824 billion VND."))
        self.assertTrue(evaluation._has_fact("9453", "Profit was 9.453 billion VND."))
        self.assertFalse(evaluation._has_fact("61824", "Revenue was 161,824 billion VND."))
        self.assertFalse(evaluation._has_fact("9453", "Profit was 19,453 billion VND."))

    def test_business_intelligence_requires_dynamic_domain_count_rows_with_evidence(self):
        payload = {
            "answer": "The role-visible document counts are grouped by domain [S1].",
            "agent": "analytics", "insufficient_context": False,
            "citations": [
                {"id": "S1", "document_id": "VNM-AR-2024-VI", "page_number": 2},
                {"id": "S2", "document_id": "VNM-CGRULES-2026-EN", "page_number": 4},
            ],
            "data": {"results": [
                {"domain": "finance", "document_count": 7, "evidence_document_ids": ["VNM-AR-2024-VI"]},
                {"domain": "governance", "document_count": 2, "evidence_document_ids": ["VNM-CGRULES-2026-EN"]},
            ]},
        }
        result = evaluation.score_case(self.case("business-intelligence-analytics"), payload)
        self.assertTrue(result["checks"]["dynamic_domain_count_rows"])
        self.assertTrue(result["checks"]["result_rows_have_sources"])
        payload["data"]["results"][0]["doc_count"] = payload["data"]["results"][0].pop("document_count")
        result = evaluation.score_case(self.case("business-intelligence-analytics"), payload)
        self.assertTrue(result["checks"]["dynamic_domain_count_rows"])
        payload["data"]["results"][0].pop("domain")
        self.assertFalse(evaluation.score_case(self.case("business-intelligence-analytics"), payload)["passed"])


if __name__ == "__main__":
    unittest.main()
