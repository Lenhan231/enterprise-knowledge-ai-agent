import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.main import (
    BusinessMetricCandidateRequest,
    CORPUS_COMPANY,
    CandidateReviewRequest,
    create_business_metric_candidate,
    review_business_metric,
)


class BusinessMetricFlowTest(unittest.TestCase):
    def test_admin_candidate_route_saves_source_linked_metric(self):
        repository = Mock()
        repository.create_business_metric_candidate.return_value = 19
        request = BusinessMetricCandidateRequest(**{
            "metric_name": "farmer_raw_milk_purchased",
            "fiscal_year": 2025,
            "metric_value": "225778.211",
            "unit": "tonnes",
            "scope": "Group farmer purchases, converted from kilograms",
            "source_document_id": "VNM-SR-2025-EN",
            "page_number": 112,
            "source_quote": "225,778,211 kg of milk purchased from farmers in 2025",
            "source_url": "https://example.org/report.pdf",
            "allowed_roles": ["executive", "sustainability_analyst"],
        })
        with patch("app.main.DocumentRepository", return_value=repository):
            response = create_business_metric_candidate(request, {"sub": "admin-test"})

        self.assertEqual(response, {"id": 19, "status": "needs_review"})
        kwargs = repository.create_business_metric_candidate.call_args.kwargs
        self.assertEqual(kwargs["company"], CORPUS_COMPANY)
        self.assertEqual(kwargs["metric"]["domain"], "milk_supply")
        self.assertEqual(kwargs["fiscal_year"], 2025)
        self.assertEqual(kwargs["entered_by"], "admin-test")

    def test_admin_review_publishes_verified_observation(self):
        repository = Mock()
        repository.review_business_metric.return_value = True
        request = CandidateReviewRequest(status="verified", normalized_value="225.778,211", unit="tonnes")
        with patch("app.main.DocumentRepository", return_value=repository):
            response = review_business_metric(19, request, {"sub": "admin-test"})
        self.assertEqual(response, {"id": 19, "status": "verified"})
        repository.review_business_metric.assert_called_once_with(
            19, "verified", 225778.211, "tonnes", "admin-test", CORPUS_COMPANY,
        )

    def test_metric_source_must_use_https(self):
        from app.main import BusinessMetricCandidateRequest
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            BusinessMetricCandidateRequest(
                metric_name="farmer_raw_milk_purchased", fiscal_year=2025,
                metric_value="225778.211", unit="tonnes",
                scope="Group farmer purchases", source_document_id="VNM-SR-2025-EN",
                page_number=112, source_quote="225,778,211 kg purchased from farmers",
                source_url="http://example.org/report.pdf", allowed_roles=["executive"],
            )


if __name__ == "__main__":
    unittest.main()
