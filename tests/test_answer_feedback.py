import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.agents import router


class AnswerFeedbackTest(unittest.TestCase):
    def setUp(self):
        self.secret = "test-only-answer-feedback-secret-32-chars"
        self.enterContext(patch.dict(os.environ, {"AUTH_SECRET_KEY": self.secret}))
        application = FastAPI()
        application.include_router(router)
        self.client = self.enterContext(TestClient(application))
        token = jwt.encode({"sub": "test-user", "role": "employee"}, self.secret, algorithm="HS256")
        self.headers = {"Authorization": "Bearer " + token}

    def test_rating_is_stored_with_the_role_from_the_token(self):
        with patch("app.agents._record_feedback") as record:
            response = self.client.post("/api/agents/feedback", headers=self.headers, json={
                "rating": "down", "question": "Hotel limit?", "answer": "Up to 2,500,000 VND [S1].",
                "agent": "knowledge", "comment": "  missing meals  ", "claim_status": "supported"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(record.call_args.kwargs, {
            "actor_role": "employee", "agent_name": "knowledge", "rating": "down", "question": "Hotel limit?",
            "answer": "Up to 2,500,000 VND [S1].", "comment": "missing meals", "claim_status": "supported"})

    def test_invalid_rating_or_extra_fields_are_rejected_and_nothing_is_stored(self):
        with patch("app.agents._record_feedback") as record:
            for body in ({"rating": "meh", "question": "q", "answer": "a"},
                         {"rating": "up", "question": "q", "answer": "a", "actor_role": "admin"}):
                self.assertEqual(self.client.post("/api/agents/feedback", headers=self.headers, json=body).status_code, 422)
        record.assert_not_called()

    def test_storage_failure_is_a_503(self):
        with patch("app.agents._record_feedback", side_effect=RuntimeError("db down")):
            response = self.client.post("/api/agents/feedback", headers=self.headers,
                                        json={"rating": "up", "question": "q", "answer": "a"})
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
