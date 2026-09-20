import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_apple_retrieval
from core.models.retrieval import RetrievalRequest, RetrievalResponse
from core.rag.rag_service import RAGService


class RetrievalCallersTest(unittest.TestCase):
    def setUp(self):
        self.response = RetrievalResponse.model_validate_json(
            (Path(__file__).parent / "fixtures" / "ranked_dense_retrieval.json").read_text(encoding="utf-8")
        )
        self.retrieval = MagicMock()
        self.retrieval.retrieve.return_value = self.response

    def test_rag_passes_request_and_uses_full_ranked_text(self):
        self.response.results[0].text = " Full text\n" * 3000
        llm = MagicMock()
        llm.generate.return_value = "answer"
        rag = RAGService(self.retrieval, llm)
        with redirect_stdout(io.StringIO()):
            answer = rag.generate_answer("question", limit=2)
        self.retrieval.retrieve.assert_called_once_with(RetrievalRequest(query="question", top_k=2))
        self.assertEqual(answer, "answer")
        prompt = llm.generate.call_args.args[0]
        context = "\n\n".join(item.text for item in self.response.results)
        self.assertIn(context, prompt)
        rag.close()
        self.retrieval.close.assert_called_once()

    def test_script_consumes_typed_results_and_closes_service(self):
        output = io.StringIO()
        with patch.object(check_apple_retrieval, "RetrievalService", return_value=self.retrieval), \
             patch.object(sys, "argv", ["check_apple_retrieval.py", "--limit", "2"]), \
             redirect_stdout(output):
            self.assertEqual(check_apple_retrieval.main(), 0)
        self.assertEqual(self.retrieval.retrieve.call_count, len(check_apple_retrieval.QUESTIONS))
        for call, question in zip(self.retrieval.retrieve.call_args_list, check_apple_retrieval.QUESTIONS):
            self.assertEqual(call.args, (RetrievalRequest(query=question, top_k=2),))
        rows = [json.loads(line) for line in output.getvalue().splitlines() if line.startswith("{")]
        self.assertEqual(rows[0]["rank"], self.response.results[0].rank)
        self.assertEqual(rows[0]["document_name"], self.response.results[0].source)
        self.assertEqual(rows[0]["chunk_index"], self.response.results[0].location.chunk_index)
        self.assertEqual(rows[0]["score"], self.response.results[0].score)
        self.assertEqual(rows[0]["preview"], " ".join(self.response.results[0].text.split())[:240])
        self.retrieval.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
