import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.retrieval.retrieval import RetrievalRequest, RetrievalResponse
from core.rag.rag_service import RAGService, _RESPONSE_CACHE, _RESPONSE_CACHE_LOCK


class RetrievalCallersTest(unittest.TestCase):
    def setUp(self):
        with _RESPONSE_CACHE_LOCK:
            _RESPONSE_CACHE.clear()
        self.response = RetrievalResponse.model_validate_json(
            (Path(__file__).parent / "fixtures" / "ranked_dense_retrieval.json").read_text(encoding="utf-8")
        )
        self.retrieval = MagicMock()
        self.retrieval.retrieve.return_value = self.response

    def test_rag_passes_request_and_uses_full_ranked_text(self):
        llm = MagicMock()
        llm.generate.return_value = "answer [S1]"
        rag = RAGService(self.retrieval, llm)
        with redirect_stdout(io.StringIO()):
            answer = rag.generate_answer("question", limit=2, roles=["employee"])
        self.retrieval.retrieve.assert_called_once_with(
            RetrievalRequest(query="question", top_k=2), roles=["employee"]
        )
        self.assertEqual(answer.answer, "answer [S1]")
        self.assertEqual(answer.source_ids, ["S1"])
        prompt = llm.generate.call_args.args[0]
        for item in self.response.results:
            self.assertIn(item.text, prompt)
        rag.close()
        self.retrieval.close.assert_called_once()
        llm.close.assert_called_once()

    def test_rag_passes_parent_strategy_to_retrieval(self):
        llm = MagicMock()
        llm.generate.return_value = "answer [S1]"
        rag = RAGService(self.retrieval, llm)
        rag.generate_answer("question", limit=2, roles=["employee"], retrieval_method="parent")
        self.retrieval.retrieve.assert_called_once_with(
            RetrievalRequest(query="question", top_k=2), roles=["employee"], method="parent"
        )

    def test_rag_uses_retrieval_query_without_changing_question_prompt(self):
        llm = MagicMock()
        llm.generate.return_value = "Revenue and profit are reported [S1]."
        rag = RAGService(self.retrieval, llm)
        rag.generate_answer(
            "What were revenue and profit?",
            retrieval_query="What were revenue and profit? Tổng doanh thu hợp nhất",
            roles=["employee"],
        )
        self.assertEqual(
            self.retrieval.retrieve.call_args.args[0],
            RetrievalRequest(query="What were revenue and profit? Tổng doanh thu hợp nhất", top_k=5),
        )
        self.assertIn("Question:\nWhat were revenue and profit?", llm.generate.call_args.args[0])

    def test_rag_can_generate_from_pre_ranked_contexts_without_retrieving_again(self):
        context = {
            "source_id": "S1", "document_name": "Commerce Demo policy", "chunk_index": 2,
            "content": "Check stock evidence before replenishment.", "metadata": {"page_number": 2},
            "retrieval_score": 0.9, "retrieval_method": "bm25",
        }
        llm = MagicMock()
        llm.generate.return_value = "Check the cited evidence [S1]."
        rag = RAGService(self.retrieval, llm)

        answer = rag.generate_answer("How should I review inventory?", roles=["admin"], retrieved_contexts=[context])

        self.retrieval.retrieve.assert_not_called()
        self.assertEqual(answer.contexts, [context])
        self.assertIn("Commerce Demo policy", llm.generate.call_args.args[0])

    def test_rag_still_requires_trusted_roles_for_pre_ranked_contexts(self):
        with self.assertRaisesRegex(ValueError, "trusted authenticated roles"):
            RAGService(self.retrieval, MagicMock()).generate_answer(
                "question", retrieved_contexts=[],
            )

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
        context = prompt.split("Sources:\n", 1)[1].split("\n\nQuestion:", 1)[0]
        self.assertLessEqual(len(context), 16_000)
        self.assertTrue(context.startswith("[S1]"))
        self.assertEqual(self.response.model_dump(), original)
        self.assertEqual(output.getvalue(), "")

    def test_rag_only_returns_sources_that_fit_in_the_prompt(self):
        self.response.results[0].text = "A" * 20_000
        self.response.results[1].text = "B" * 2_000
        llm = MagicMock()
        llm.generate.return_value = "answer [S1]"

        answer = RAGService(self.retrieval, llm).generate_answer("question", limit=2, roles=["employee"])

        prompt = llm.generate.call_args.args[0]
        context = prompt.split("Sources:\n", 1)[1].split("\n\nQuestion:", 1)[0]
        self.assertLessEqual(len(context), 16_000)
        self.assertEqual([item["source_id"] for item in answer.contexts], ["S1"])
        self.assertIn("[S1]", context)
        self.assertNotIn("[S2]", context)
        self.assertEqual(len(self.response.results[0].text), 20_000)

if __name__ == "__main__":
    unittest.main()
