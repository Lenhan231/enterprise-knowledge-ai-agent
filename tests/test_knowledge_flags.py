"""Env-gated Knowledge changes: off keeps the pre-change prompt, on adds rule 11 and a larger top-k."""
import os
import unittest
from unittest.mock import patch

from core.rag.rag_service import RAGService
from core.retrieval.retrieval import RankedChunk, RetrievalResponse, SourceLocation, make_chunk_id


class FakeRetrieval:  # test_rag's fakes cannot be imported (that module targets a removed response cache)
    def __init__(self):
        self.calls = []

    def retrieve(self, request, company=None, roles=None, method=None):
        self.calls.append(request)
        results = [RankedChunk(rank=i, chunk_id=make_chunk_id(f"D{i}", 0), document_id=f"D{i}", text="Nội dung.", score=0.5,
                               source="policy.pdf", location=SourceLocation(chunk_index=0),
                               metadata={"document_id": f"D{i}"}, retrieval_method="hybrid")
                   for i in range(1, request.top_k + 1)]
        return RetrievalResponse(query=request.query, latency_ms=0, results=results)


class FakeLLM:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, **_):
        self.calls.append(prompt)
        return "Câu trả lời [S1]."


class KnowledgeFlagTest(unittest.TestCase):
    def run_once(self, env):
        llm, retrieval = FakeLLM(), FakeRetrieval()
        with patch.dict(os.environ, env):
            RAGService(retrieval, llm).generate_answer("Hỏi?", roles=["employee"])
        return llm.calls[0], retrieval.calls[0].top_k

    def test_defaults_keep_previous_behaviour(self):
        prompt, top_k = self.run_once({"KNOWLEDGE_COMPLETENESS_RULE": "0", "KNOWLEDGE_TOP_K": "5"})
        self.assertNotIn("11. Nếu câu hỏi có nhiều ý", prompt)
        self.assertEqual(top_k, 5)

    def test_flags_add_rule_before_sources_and_raise_top_k(self):
        prompt, top_k = self.run_once({"KNOWLEDGE_COMPLETENESS_RULE": "1", "KNOWLEDGE_TOP_K": "8"})
        self.assertLess(prompt.index("11. Nếu câu hỏi có nhiều ý"), prompt.index("Nguồn:"))
        self.assertEqual(top_k, 8)


    def test_context_budget_is_configurable(self):
        import importlib
        from core.rag import rag_service
        with patch.dict(os.environ, {"KNOWLEDGE_CONTEXT_MAX_CHARS": "20000"}):
            self.assertEqual(importlib.reload(rag_service).MAX_CONTEXT_CHARS, 20000)
        self.assertEqual(importlib.reload(rag_service).MAX_CONTEXT_CHARS, 24000)


if __name__ == "__main__":
    unittest.main()
