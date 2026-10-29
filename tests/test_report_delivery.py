import os
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
