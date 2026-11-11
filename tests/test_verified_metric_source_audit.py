import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/analytics/audit_verified_financial_metrics.py"
SPEC = importlib.util.spec_from_file_location("audit_verified_financial_metrics", SCRIPT)
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


class VerifiedMetricSourceAuditTest(unittest.TestCase):
    def test_accepts_value_label_year_and_reported_unit_on_page(self):
        observation = {
            "metric_name": "total_consolidated_revenue", "fiscal_year": 2020,
            "metric_value": 59723, "unit": "billion VND",
        }

        result = audit_module.score_observation(
            observation,
            "Consolidated net revenue 2020 reached VND 59,723 billion.",
        )

        self.assertTrue(result["passed"])

    def test_rejects_wrong_unit_or_missing_metric_label(self):
        observation = {
            "metric_name": "profit_after_tax", "fiscal_year": 2020,
            "metric_value": 11236, "unit": "billion VND",
        }

        result = audit_module.score_observation(observation, "Consolidated revenue: 11,236 million VND in 2020")

        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["metric_label"])
        self.assertFalse(result["checks"]["unit"])

    def test_source_must_match_the_official_manifest_url(self):
        manifest = {"documents": [{
            "document_id": "VNM-AR-2021-VI",
            "source_url": "https://reports.example.test/annual.pdf",
        }]}

        self.assertTrue(audit_module._is_manifest_source(
            "VNM-AR-2021-VI", "https://reports.example.test/annual.pdf", manifest,
        ))
        self.assertFalse(audit_module._is_manifest_source(
            "VNM-AR-2021-VI", "https://attacker.example.test/annual.pdf", manifest,
        ))
        self.assertFalse(audit_module._is_manifest_source(
            "VNM-AR-2021-VI", "http://reports.example.test/annual.pdf", manifest,
        ))


if __name__ == "__main__":
    unittest.main()
