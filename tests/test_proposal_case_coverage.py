import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_proposal_case_coverage import evaluate_coverage

ROOT = Path(__file__).resolve().parents[1]


class ProposalCaseCoverageTest(unittest.TestCase):
    def setUp(self):
        self.routes = json.loads((ROOT / "data/evaluation/proposal_business_route_cases.json").read_text())
        self.labels = json.loads((ROOT / "data/evaluation/proposal_business_case_corpus_labels.json").read_text())
        self.manifest = json.loads((ROOT / "data/vietnam_enterprises/manifest.json").read_text())

    def test_all_proposal_cases_have_manifest_backed_coverage_labels(self):
        result = evaluate_coverage(self.routes, self.labels, self.manifest)

        self.assertEqual(len(result["cases"]), 12)
        self.assertEqual(result["corpus_document_count"], 26)
        self.assertEqual(result["coverage_counts"], {"partial": 6, "supported": 2, "unsupported": 4})
        self.assertIn("VNM-AR-2024-VI", next(c for c in result["cases"] if c["id"] == "financial-report-analysis")["source_document_ids"])
        customer_service = next(c for c in result["cases"] if c["id"] == "customer-service-knowledge")
        self.assertEqual(customer_service["corpus_coverage"], "partial")
        self.assertIn("VNM-POL-RETURNS-2026-VI", customer_service["source_document_ids"])
        employee_access = next(c for c in result["cases"] if c["id"] == "internal-document-search")
        self.assertEqual(employee_access["corpus_coverage"], "partial")
        self.assertIn("VNM-CODE-2025-EN", employee_access["source_document_ids"])
        code = next(d for d in self.manifest["documents"] if d["document_id"] == "VNM-CODE-2025-EN")
        self.assertIn("employee", code["rbac"]["allowed_roles"])

    def test_unknown_source_document_is_rejected(self):
        self.labels["cases"][0]["source_document_ids"] = ["NOT-IN-MANIFEST"]

        with self.assertRaisesRegex(ValueError, "Unknown corpus source IDs"):
            evaluate_coverage(self.routes, self.labels, self.manifest)

    def test_coverage_labels_must_keep_route_case_set_in_sync(self):
        self.labels["cases"].pop()

        with self.assertRaisesRegex(ValueError, "must match"):
            evaluate_coverage(self.routes, self.labels, self.manifest)


if __name__ == "__main__":
    unittest.main()
