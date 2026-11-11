import asyncio
import os
import time
import unittest
from unittest.mock import patch

from core.agents.knowledge_agent import KnowledgeAgent
from core.agents.runtime import deadline, remaining, run_sync
from core.models.agents import AgentRequest, VerifiedIdentity
from core.rag.rag_service import RAGResult


class KnowledgeTimeoutTest(unittest.IsolatedAsyncioTestCase):
    def request(self):
        return AgentRequest(question="Policy?", identity=VerifiedIdentity(
            subject="test", permissions={"documents:read"}, document_roles={"employee"}))

    async def test_multiquery_gets_90_seconds_and_legacy_keeps_60(self):
        for flag, seconds in (("0", 60), ("1", 90)):
            observed = []

            class Rag:
                def generate_answer(self, question, **kwargs):
                    observed.append((remaining(1000), kwargs))
                    return RAGResult(answer="No evidence", insufficient_context=True)

            with self.subTest(flag=flag), patch.dict(os.environ, {"KNOWLEDGE_MULTIQUERY_ENABLED": flag}), \
                 patch("core.agents.runtime.asyncio.wait_for", wraps=asyncio.wait_for) as wait:
                await KnowledgeAgent(Rag()).run(self.request())
                self.assertAlmostEqual(wait.await_args.args[1], seconds, delta=0.5)
            self.assertAlmostEqual(observed[0][0], seconds, delta=0.5)
            self.assertEqual(observed[0][1]["decompose"], flag == "1")
            self.assertEqual(observed[0][1]["roles"], ["employee"])
            self.assertNotIn("_timeout", observed[0][1])
            self.assertIsNone(deadline.get())

    async def test_multiquery_never_extends_parent_deadline_and_restores_it_on_error(self):
        parent = time.monotonic() + 5
        token = deadline.set(parent)
        observed = []

        class Rag:
            def generate_answer(self, *args, **kwargs):
                observed.append(remaining(1000))
                raise ConnectionError("service disconnected")

        try:
            with patch.dict(os.environ, {"KNOWLEDGE_MULTIQUERY_ENABLED": "1"}):
                with self.assertRaises(ConnectionError):
                    await KnowledgeAgent(Rag()).run(self.request())
            self.assertGreater(observed[0], 0)
            self.assertLessEqual(observed[0], 5)
            self.assertEqual(deadline.get(), parent)
        finally:
            deadline.reset(token)

    async def test_other_sync_callers_keep_default_wait(self):
        with patch("core.agents.runtime.asyncio.wait_for", wraps=asyncio.wait_for) as wait:
            self.assertEqual(await run_sync(lambda: "OK"), "OK")
        self.assertEqual(wait.await_args.args[1], 60)
