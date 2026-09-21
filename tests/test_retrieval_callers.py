import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.retrieval.retrieval import RetrievalRequest, RetrievalResponse
from core.rag.rag_service import RAGService


class RetrievalCallersTest(unittest.TestCase):
    def setUp(self):
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
            answer = rag.generate_answer("question", limit=2)
        self.retrieval.retrieve.assert_called_once_with(RetrievalRequest(query="question", top_k=2))
        self.assertEqual(answer.answer, "answer [S1]")
        self.assertEqual(answer.source_ids, ["S1"])
        prompt = llm.generate.call_args.args[0]
        for item in self.response.results:
            self.assertIn(item.text, prompt)
        rag.close()
        self.retrieval.close.assert_called_once()

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
            answer = RAGService(self.retrieval, llm).generate_answer("question", limit=2)

        llm.generate.assert_called_once()
        self.assertEqual(answer.answer, "answer [S1]")
        prompt = llm.generate.call_args.args[0]
        context = prompt.split("Sources:\n", 1)[1].split("\n\nQuestion:", 1)[0]
        self.assertEqual(len(context), 24_000)
        self.assertTrue(context.startswith("[S1]"))
        self.assertEqual(self.response.model_dump(), original)
        self.assertEqual(output.getvalue(), "")

if __name__ == "__main__":
    unittest.main()
