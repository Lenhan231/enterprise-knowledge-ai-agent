import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient
from app.main import ManualMetricRequest, _issue_token, app
from core.analytics.metric_ontology import METRIC_ONTOLOGY
from core.database.document_repository import DocumentRepository


class ManualMetricWorkflowTest(unittest.TestCase):
    def test_request_uses_canonical_metric_and_normalizes_number(self):
        request = ManualMetricRequest(
            metric_name="total_consolidated_revenue", fiscal_year=2024,
            metric_value="59.723,5", unit="billion VND",
            source_note="Checked against the audited annual report.",
            allowed_roles=["admin", "finance_analyst", "admin"],
        )
        self.assertEqual(request.metric_value, "59723.5")
        self.assertEqual(request.allowed_roles, ["admin", "finance_analyst"])

    def test_request_rejects_unknown_metric_and_empty_access_scope(self):
        base = {
            "fiscal_year": 2024, "metric_value": "59723", "unit": "billion VND",
            "source_note": "Checked against a published statement.", "allowed_roles": ["admin"],
        }
        with self.assertRaises(ValueError):
            ManualMetricRequest(metric_name="made_up_kpi", **base)
        with self.assertRaises(ValueError):
            ManualMetricRequest(metric_name="net_revenue", **{**base, "allowed_roles": []})
        with self.assertRaises(ValueError):
            ManualMetricRequest(metric_name="net_revenue", **{**base, "source_note": "            "})

    def test_manual_candidate_persists_without_fake_document_page_or_quote(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (42,)

        result = repository.create_manual_metric_candidate(
            company="Vinamilk", metric_name="net_revenue", metric_label="Net revenue",
            metric_value="59723", fiscal_year=2024, unit="billion VND",
            source_reference="Audited FY2024 report, page 8",
            source_note="Entered from the signed report; page-level OCR omitted this table.",
            allowed_roles=["admin", "finance_analyst"],
        )

        self.assertEqual(result, 42)
        query, params = cursor.execute.call_args.args
        normalized = " ".join(query.lower().split())
        self.assertIn("entry_method", normalized)
        self.assertIn("'manual'", normalized)
        self.assertNotIn("document_id", normalized)
        self.assertNotIn("page_number", normalized)
        self.assertEqual(params[0:3], ("Vinamilk", "net_revenue", "Net revenue"))
        repository.conn.transaction.assert_called_once()

    def test_manual_metric_endpoint_is_admin_only_and_queues_for_review(self):
        request = {
            "metric_name": "net_revenue", "fiscal_year": 2024,
            "metric_value": "59.723", "unit": "billion VND",
            "source_reference": "Audited FY2024 statement, page 8",
            "source_note": "Entered from the signed report; OCR did not capture this row.",
            "allowed_roles": ["admin", "finance_analyst"],
        }
        with patch("app.main.DocumentRepository") as repository_type, TestClient(app) as client:
            repository_type.return_value.create_manual_metric_candidate.return_value = 42
            client.cookies.set("enterprise_session", _issue_token("admin", "admin"))
            response = client.post("/api/metrics/manual", json=request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"id": 42, "status": "needs_review"})
            repository_type.return_value.create_manual_metric_candidate.assert_called_once()
            self.assertEqual(
                repository_type.return_value.create_manual_metric_candidate.call_args.kwargs["metric_label"],
                METRIC_ONTOLOGY["net_revenue"]["label"],
            )

            employee = TestClient(app)
            employee.cookies.set("enterprise_session", _issue_token("employee", "employee"))
            denied = employee.post("/api/metrics/manual", json=request)
            self.assertEqual(denied.status_code, 403)
            repository_type.return_value.create_manual_metric_candidate.assert_called_once()
            employee.close()

    def test_verified_manual_metric_uses_company_period_conflict_target(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {
            "id": 42, "company": "Vinamilk", "document_id": None,
            "fiscal_year": 2024, "status": "needs_review",
        }
        cursor.rowcount = 1

        self.assertTrue(repository.review_metric_candidate(
            42, "verified", 59723, "billion VND", "reviewer", "Vinamilk",
        ))
        query = " ".join(cursor.execute.call_args_list[-1].args[0].lower().split())
        self.assertIn("on conflict (company, fiscal_year, metric_name)", query)
        self.assertIn("where status = 'verified' do nothing", query)


if __name__ == "__main__":
    unittest.main()
