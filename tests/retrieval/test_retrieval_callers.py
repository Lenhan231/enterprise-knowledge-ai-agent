import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from scripts.retrieval import check_apple_retrieval
from core.retrieval.retrieval import RankedChunk, RetrievalRequest, RetrievalResponse, SourceLocation, make_chunk_id
from core.agents.knowledge.rag_service import MAX_CONTEXT_CHARS, RAGService


class RetrievalCallersTest(unittest.TestCase):

    def setUp(self):
        self.response = RetrievalResponse(
            query="question",
            method="hybrid",
            latency_ms=0,
            results=[
                RankedChunk(
                    rank=index,
                    chunk_id=make_chunk_id(document_id, 0),
                    document_id=document_id,
                    text=text,
                    score=0.9 - index / 10,
                    source=f"{document_id}.pdf",
                    location=SourceLocation(chunk_index=0, page_number=index),
                    metadata={"document_id": document_id},
                    retrieval_method="hybrid",
                )
                for index, (document_id, text) in enumerate(
                    (("DOC-1", "First ranked passage"), ("DOC-2", "Second ranked passage")),
                    start=1,
                )
            ],
        )
        class RetrievalStub:
            def __init__(self, response):
                self.response = response
                self.responses = None
                self.calls = []

            def retrieve(self, request, company=None, roles=None, method="translated_hybrid_rerank"):
                self.calls.append((request, company, roles, method))
                if self.responses is not None:
                    return self.responses.pop(0)
                return self.response

            def close(self):
                self.close_count += 1

        self.retrieval = RetrievalStub(self.response)
        self.retrieval.close_count = 0

    def test_rag_passes_request_and_uses_full_ranked_text(self):
        llm = MagicMock()
        llm.generate.return_value = "answer [S1]"
        rag = RAGService(self.retrieval, llm)
        with redirect_stdout(io.StringIO()):
            answer = rag.generate_answer("question", limit=2, roles=["employee"])
        self.assertEqual(self.retrieval.calls, [
            (RetrievalRequest(query="question", top_k=2), None, ["employee"], "translated_hybrid_rerank")
        ])
        self.assertEqual(answer.answer, "answer [S1]")
        self.assertEqual(answer.source_ids, ["S1"])
        prompt = llm.generate.call_args.args[0]
        for item in self.response.results:
            self.assertIn(item.text, prompt)
        rag.close()
        self.assertEqual(self.retrieval.close_count, 1)

    def test_rag_passes_parent_strategy_to_retrieval(self):
        llm = MagicMock()
        llm.generate.return_value = "answer [S1]"
        rag = RAGService(self.retrieval, llm)
        rag.generate_answer("question", limit=2, roles=["employee"], retrieval_method="parent")
        self.assertEqual(self.retrieval.calls, [
            (RetrievalRequest(query="question", top_k=2), None, ["employee"], "parent")
        ])

    def test_rag_bounds_context_without_mutating_results_or_printing(self):
        # Include separators and a second chunk in the cutoff, not just one
        # oversized chunk, to verify the limit applies to the assembled context.
        self.response.results[0].text = "A" * 12_000
        self.response.results[1].text = "B" * 13_000
        original = self.response.model_dump()
        llm = MagicMock()
        llm.generate.return_value = "answer [S1]"
        output = io.StringIO()

        with redirect_stdout(output):
            answer = RAGService(self.retrieval, llm).generate_answer("question", limit=2, roles=["employee"])

        llm.generate.assert_called_once()
        self.assertEqual(answer.answer, "answer [S1]")
        prompt = llm.generate.call_args.args[0]
        context = prompt.split("Nguồn:\n", 1)[1].split("\n\nCâu hỏi:", 1)[0]
        self.assertLessEqual(len(context), MAX_CONTEXT_CHARS)
        self.assertTrue(context.startswith("[S1]"))
        self.assertEqual(self.response.model_dump(), original)
        self.assertEqual(output.getvalue(), "")

    def test_rag_only_returns_sources_that_fit_in_the_prompt(self):
        self.response.results[0].text = "A" * 20_000
        self.response.results[1].text = "B" * 2_000
        llm = MagicMock()
        llm.generate.return_value = "answer [S1]"

        with patch("core.agents.knowledge.rag_service.MAX_CONTEXT_CHARS", 16_000):
            answer = RAGService(self.retrieval, llm).generate_answer("question", limit=2, roles=["employee"])

        prompt = llm.generate.call_args.args[0]
        context = prompt.split("Nguồn:\n", 1)[1].split("\n\nCâu hỏi:", 1)[0]
        self.assertLessEqual(len(context), 16_000)
        self.assertEqual([item["source_id"] for item in answer.contexts], ["S1"])
        self.assertIn("[S1]", context)
        self.assertNotIn("[S2]", context)
        self.assertEqual(len(self.response.results[0].text), 20_000)

    def test_script_consumes_typed_results_and_closes_service(self):
        output = io.StringIO()
        result_by_id = {}
        for document_id in check_apple_retrieval.CASES:
            results = [item.model_copy(update={"document_id": document_id}) for item in self.response.results]
            result_by_id[document_id] = self.response.model_copy(update={"results": results})
        self.retrieval.responses = list(result_by_id.values())
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "results.json"
            with patch.object(check_apple_retrieval, "RetrievalService", return_value=self.retrieval), \
                 patch.object(sys, "argv", ["scripts.retrieval.check_apple_retrieval.py", "--limit", "2", "--output", str(output_path)]), \
                 redirect_stdout(output):
                self.assertEqual(check_apple_retrieval.main(), 0)
            self.assertEqual(len(self.retrieval.calls), len(check_apple_retrieval.CASES))
            for call, question in zip(self.retrieval.calls, check_apple_retrieval.CASES.values()):
                self.assertEqual(call, (RetrievalRequest(query=question, top_k=2), None, None, "translated_hybrid_rerank"))
            self.assertIn("[PASS] APL-CMP-003", output.getvalue())
            self.assertIn("DOC-1.pdf", output.getvalue())
            self.assertTrue(output_path.exists())
            self.assertEqual(self.retrieval.close_count, 1)


if __name__ == "__main__":
    unittest.main()
