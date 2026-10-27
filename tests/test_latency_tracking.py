import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.latency import latency_events, measure, snapshot


class LatencyTrackingTest(unittest.IsolatedAsyncioTestCase):
    async def test_chat_preserves_threaded_retrieval_timings_without_cited_evidence(self):
        from app.agents import AgentChatRequest, agent_chat
        from core.agents.knowledge_agent import KnowledgeAgent
        from core.agents.router import AgentRouter
        from core.rag.rag_service import RAGService
        from core.retrieval.retrieval_service import RetrievalService

        embeddings = Mock()
        embeddings.embed_query.return_value = [1.0]
        repository = Mock()
        repository.similarity_search.return_value = []
        rag = RAGService(RetrievalService(embeddings, repository), llm=Mock())
        runtime = AgentRouter(None, KnowledgeAgent(rag), None)
        with patch("app.agents._get_runtime", new=AsyncMock(return_value=runtime)), \
                patch("app.agents._record_agent_run"):
            result = await agent_chat(
                AgentChatRequest(question="Missing evidence", agent_mode="knowledge", retrieval_method="dense"),
                Mock(), user={"role": "admin", "sub": "latency-test"},
            )
        timing = result.metadata["latency"]
        stages = timing["stages_ms"]
        self.assertGreaterEqual(timing["request_total_ms"], stages["agent_workflow"])
        self.assertGreaterEqual(stages["agent_workflow"], stages["retrieval_total"])
        self.assertGreaterEqual(stages["retrieval_total"], stages["embedding"])
        self.assertIsNone(stages["reranking"])
        self.assertIsNone(stages["answer_generation"])
        self.assertEqual(result.metadata["selected_route"], "knowledge")
        self.assertEqual(result.evidence, [])
        self.assertIsNone(latency_events.get())

    async def test_parallel_requests_and_thread_workers_keep_separate_timings(self):
        @measure("embedding")
        def embed():
            return [1.0]

        async def request():
            events = []
            token = latency_events.set(events)
            try:
                self.assertEqual(await asyncio.to_thread(embed), [1.0])
                return events
            finally:
                latency_events.reset(token)

        first, second = await asyncio.gather(request(), request())
        self.assertIsNot(first, second)
        self.assertEqual([e["stage"] for e in first], ["embedding"])
        self.assertEqual([e["stage"] for e in second], ["embedding"])
        self.assertIsNone(latency_events.get())

    async def test_failed_stages_are_recorded_without_swallowing_errors(self):
        token = latency_events.set([])
        try:
            with patch("core.latency.perf_counter", side_effect=[1.0, 1.025]):
                with self.assertRaisesRegex(ValueError, "bad vector"):
                    with measure("embedding"):
                        raise ValueError("bad vector")
            data = snapshot()
            self.assertAlmostEqual(data["stages_ms"]["embedding"], 25.0)
            self.assertIsNone(data["stages_ms"]["reranking"])
            self.assertEqual(data["events"][0]["status"], "failed")
        finally:
            latency_events.reset(token)

    async def test_repeated_calls_sum_without_losing_individual_events(self):
        token = latency_events.set([])
        try:
            with patch("core.latency.perf_counter", side_effect=[1, 1.01, 2, 2.02]):
                with measure("answer_generation"):
                    pass
                with measure("answer_generation"):
                    pass
            data = snapshot()
            self.assertAlmostEqual(data["stages_ms"]["answer_generation"], 30.0)
            self.assertEqual(len(data["events"]), 2)
        finally:
            latency_events.reset(token)
