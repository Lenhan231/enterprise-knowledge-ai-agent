"""Knowledge messages distinguish access denial, no matches and insufficient evidence."""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.agents import router
from app.security import ACCESS_DENIED_MESSAGE
from core.agents.knowledge_agent import KnowledgeAgent
from core.models.agents import AgentRequest, VerifiedIdentity
from core.prompts.Knowledge import INSUFFICIENT_ANSWER, NO_MATCHING_DOCUMENTS_ANSWER
from core.rag.rag_service import RAGService


class KnowledgeOutcomeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rag = RAGService.__new__(RAGService)
        self.rag.llm = Mock()
        self.contexts = [{"source_id": "S1", "document_name": "policy.pdf", "chunk_index": 0,
                          "content": "Authorized policy text", "metadata": {"document_id": "DOC-1"}}]

    def test_no_matches_returns_message_without_calling_llm(self):
        result = self.rag.generate_from_contexts("policy?", [])
        self.assertEqual(result.answer, NO_MATCHING_DOCUMENTS_ANSWER)
        self.assertTrue(result.insufficient_context)
        self.assertEqual(result.source_ids, [])
        self.rag.llm.generate.assert_not_called()

    def test_existing_evidence_can_be_insufficient(self):
        self.rag.llm.generate.return_value = INSUFFICIENT_ANSWER
        result = self.rag.generate_from_contexts("policy?", self.contexts)
        self.assertEqual(result.answer, INSUFFICIENT_ANSWER)
        self.assertEqual(result.contexts, self.contexts)
        self.assertTrue(result.insufficient_context)
        self.assertIn(INSUFFICIENT_ANSWER, self.rag.llm.generate.call_args.args[0])

    def test_supported_answer_still_requires_valid_citations(self):
        self.rag.llm.generate.return_value = "Policy text [S1]"
        result = self.rag.generate_from_contexts("policy?", self.contexts)
        self.assertFalse(result.insufficient_context)
        self.assertEqual(result.source_ids, ["S1"])
        for answer in ("Unsupported answer", "Unknown source [S99]"):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                self.rag.llm.generate.return_value = answer
                self.rag.generate_from_contexts("policy?", self.contexts)

    async def test_knowledge_propagates_both_empty_outcomes(self):
        identity = VerifiedIdentity(subject="viewer", permissions={"documents:read"}, document_roles={"employee"})
        for contexts in ([], self.contexts):
            with self.subTest(has_context=bool(contexts)):
                self.rag.llm.generate.return_value = INSUFFICIENT_ANSWER
                outcome = self.rag.generate_from_contexts("policy?", contexts)
                service = Mock()
                service.generate_answer.return_value = outcome
                result = await KnowledgeAgent(service).run(AgentRequest(question="policy?", identity=identity))
                self.assertEqual(result.answer, outcome.answer)
                self.assertTrue(result.metadata["insufficient_context"])
                self.assertEqual(result.evidence, [])
                service.generate_answer.assert_called_once_with(
                    "policy?", roles=["employee"], retrieval_method="translated_hybrid_rerank",
                )


class KnowledgeAccessMessageTest(unittest.TestCase):
    def setUp(self):
        self.secret = "test-only-knowledge-message-secret-32-chars"
        self.enterContext(patch.dict(os.environ, {"AUTH_SECRET_KEY": self.secret}))
        application = FastAPI()
        application.include_router(router)
        self.client = self.enterContext(TestClient(application))

    def headers(self, role):
        token = jwt.encode({"sub": "test-user", "role": role}, self.secret, algorithm="HS256")
        return {"Authorization": "Bearer " + token}

    def test_missing_feature_permission_is_403_without_running_knowledge(self):
        with patch("app.agents._get_runtime", new_callable=AsyncMock) as runtime:
            response = self.client.post("/api/agents/chat", headers=self.headers("document_uploader"),
                                        json={"question": "policy?", "agent_mode": "knowledge"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], ACCESS_DENIED_MESSAGE)
        runtime.assert_not_called()

    def test_runtime_permission_denial_uses_the_same_message(self):
        runtime = Mock()
        runtime.run_mode = AsyncMock(side_effect=PermissionError("private diagnostic"))
        with patch("app.agents._get_runtime", new_callable=AsyncMock, return_value=runtime), \
             patch("app.agents._record_agent_run"):
            response = self.client.post("/api/agents/chat", headers=self.headers("employee"),
                                        json={"question": "policy?", "agent_mode": "knowledge"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], ACCESS_DENIED_MESSAGE)
        self.assertNotIn("private diagnostic", response.text)

    def test_missing_session_still_returns_401(self):
        response = self.client.post("/api/agents/chat", json={"question": "policy?", "agent_mode": "knowledge"})
        self.assertEqual(response.status_code, 401)
