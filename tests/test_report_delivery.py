import os
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.agents import router
from core.agents.main import create_app
from core.models.agents import AgentResult, VerifiedIdentity

SECRET = "test-report-auth-secret-at-least-32-characters"


class ReportDeliveryTest(unittest.TestCase):
    def test_download_summary_reports_section_states_and_narrative_omissions(self):
        from core.reports.http import report_response
        result = AgentResult(answer='Partial', agent='report', metadata={
            'status': 'partial', 'sections': {'A': 'complete', 'B': 'unavailable', 'C': 'failed'},
            'narrative_coverage': {'A': {'facts_omitted': 4, 'documents_omitted': 1}},
            'issues': {'B': 'no_observations_for_requested_scope'},
        })
        response = report_response(result, b'report', 'text/markdown')
        summary = json.loads(response.headers['X-Report-Summary'])
        self.assertEqual((summary['complete'], summary['failed'], summary['unavailable']), (1, 1, 1))
        self.assertEqual(summary['omitted_from_narrative'], 5)
        self.assertIn('no observations for requested scope', summary['reasons'])

    def test_both_apis_return_combined_confirmation_and_forward_choices(self):
        detail = {'ok': False, 'status': 'confirmation_required', 'confirmation_required': True,
                  'mismatch_reasons': ['Template lacks category columns'],
                  'unsupported_requirements': ['Supplier lead time unavailable'],
                  'suggested_structure': [{'heading': 'Category stock'}],
                  'template_decision_required': True, 'scope_decision_required': True}
        identity = VerifiedIdentity(subject='analyst', permissions={'documents:read', 'analytics:read'}, document_roles={'employee'})
        for production in (False, True):
            report = SimpleNamespace(generate_from_template=AsyncMock(return_value=(
                AgentResult(answer='Review report', agent='report', metadata=detail), b'', 'text/markdown')))
            if production:
                app = FastAPI(); app.include_router(router)
                app.state.agent_router = SimpleNamespace(report_agent=report)
                path = '/api/agents/report'
            else:
                app = create_app(chat_agent=object(), report_agent=report, identity_resolver=lambda _: identity)
                path = '/api/report'
            token = jwt.encode({'sub': 'analyst', 'role': 'admin', 'exp': 4102444800}, SECRET, algorithm='HS256')
            with patch.dict(os.environ, {'AUTH_SECRET_KEY': SECRET}), patch('app.agents._record_agent_run'), TestClient(app) as client:
                response = client.post(path, data={'question': 'Inventory report', 'template_choice': 'suggested',
                    'accept_supported_scope': 'true'}, headers={'Authorization': 'Bearer '+token})
            self.assertEqual(response.status_code, 409)
            self.assertTrue(response.json()['detail']['scope_decision_required'])
            self.assertEqual(report.generate_from_template.await_args.kwargs['template_choice'], 'suggested')
            self.assertIs(report.generate_from_template.await_args.kwargs['accept_supported_scope'], True)

    def test_both_apis_return_actionable_clarification_instead_of_503(self):
        clarification = "Do you mean refunded amount, returned units, or return rate?"
        for production in (False, True):
            with self.subTest(production=production):
                report = SimpleNamespace(generate_from_template=AsyncMock(return_value=(
                    AgentResult(answer=clarification, agent="report", metadata={
                        "ok": False, "status": "clarification_required", "clarification_required": True,
                        "limitations": [clarification]}), b"", "text/markdown")))
                if production:
                    app = FastAPI()
                    app.include_router(router)
                    app.state.agent_router = SimpleNamespace(report_agent=report)
                    path = "/api/agents/report"
                else:
                    identity = VerifiedIdentity(subject="reader", permissions={"documents:read"},
                                                document_roles={"employee"})
                    app = create_app(chat_agent=object(), report_agent=report, identity_resolver=lambda _: identity)
                    path = "/api/report"
                token = jwt.encode({"sub": "reader", "role": "employee"}, SECRET, algorithm="HS256")
                with patch.dict(os.environ, {"AUTH_SECRET_KEY": SECRET}), patch("app.agents._record_agent_run"), TestClient(app) as client:
                    response = client.post(path, data={"question": "report"}, headers={"Authorization": f"Bearer {token}"})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"]["clarification"], clarification)
                self.assertNotIn("Content-Disposition", response.headers)

    def test_both_apis_preserve_partial_and_refuse_failed_downloads(self):
        for production in (False, True):
            for status in ("complete", "partial", "failed"):
                with self.subTest(production=production, status=status):
                    report = SimpleNamespace(generate_from_template=AsyncMock(return_value=(
                        AgentResult(answer="done", agent="report", metadata={
                            "status": status, "ok": status == "complete", "limitations": ["Section missing"]}),
                        b"report" if status != "failed" else b"", "text/markdown")))
                    if production:
                        app = FastAPI()
                        app.include_router(router)
                        app.state.agent_router = SimpleNamespace(report_agent=report)
                        path = "/api/agents/report"
                    else:
                        identity = VerifiedIdentity(subject="reader", permissions={"documents:read"},
                                                    document_roles={"employee"})
                        app = create_app(chat_agent=object(), report_agent=report,
                                         identity_resolver=lambda _: identity)
                        path = "/api/report"
                    token = jwt.encode({"sub": "reader", "role": "employee"}, SECRET, algorithm="HS256")
                    with patch.dict(os.environ, {"AUTH_SECRET_KEY": SECRET}), patch("app.agents._record_agent_run"), TestClient(app) as client:
                        response = client.post(path, data={"question": "report"}, headers={"Authorization": f"Bearer {token}"})
                    self.assertEqual(response.status_code, 422 if status == "failed" else 200)
                    if status != "failed":
                        self.assertEqual(response.headers["X-Report-Status"], status)
                        self.assertIn("report.md", response.headers["Content-Disposition"])
                    else:
                        self.assertNotIn("Content-Disposition", response.headers)
                        self.assertEqual(response.json()["detail"]["status"], "failed")

    def test_employee_cannot_select_analytics_or_forge_roles(self):
        app = FastAPI()
        app.include_router(router)
        report = AsyncMock()
        app.state.agent_router = SimpleNamespace(report_agent=report)
        token = jwt.encode({"sub": "reader", "role": "employee"}, SECRET, algorithm="HS256")
        with patch.dict(os.environ, {"AUTH_SECRET_KEY": SECRET}), patch("app.agents._record_agent_run"), TestClient(app) as client:
            denied = client.post("/api/agents/report", data={
                "question": "report", "source_mode": "combined", "roles": "admin"},
                headers={"Authorization": f"Bearer {token}"})
            anonymous = client.post("/api/agents/report", data={"question": "report"})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(anonymous.status_code, 401)
        report.generate_from_template.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
