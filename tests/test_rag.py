import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.rag.rag_service import (
    INSUFFICIENT_ANSWER,
    RAGService,
)


class FakeRetrieval:
    def __init__(self, contexts):
        self.contexts = contexts

    def retrieve(self, question, limit=5):
        return {
            "question": question,
            "contexts": self.contexts[:limit],
        }

    def close(self):
        pass


class FakeLLM:
    def __init__(self, answer):
        self.answer = answer

    def generate(self, prompt):
        return self.answer


def context(document_id="DOC-1"):
    return {
        "document_name": "policy.pdf",
        "chunk_index": 7,
        "content": "Employees may report policy concerns.",
        "metadata": {
            "document_id": document_id,
            "source_document": "policy.pdf",
            "page_number": 12,
            "section_title": "Reporting Concerns",
        },
        "similarity_score": 0.81,
    }


class RAGServiceTest(unittest.TestCase):
    def test_grounded_answer(self):
        result = RAGService(
            FakeRetrieval([context()]),
            FakeLLM("Concerns may be reported [S1]."),
        ).generate_answer("How are concerns reported?")

        self.assertEqual(result.source_ids, ["S1"])
        self.assertFalse(result.insufficient_context)

    def test_multiple_sources(self):
        result = RAGService(
            FakeRetrieval([context("DOC-1"), context("DOC-2")]),
            FakeLLM("The requirements are described in [S1] and [S2]."),
        ).generate_answer("What are the requirements?")

        self.assertEqual(result.source_ids, ["S1", "S2"])

    def test_empty_retrieval(self):
        result = RAGService(
            FakeRetrieval([]),
            FakeLLM("Should not be called"),
        ).generate_answer("Unknown question")

        self.assertEqual(result.answer, INSUFFICIENT_ANSWER)
        self.assertTrue(result.insufficient_context)

    def test_unknown_citation(self):
        service = RAGService(
            FakeRetrieval([context()]),
            FakeLLM("Unsupported claim [S9]."),
        )

        with self.assertRaises(ValueError):
            service.generate_answer("Question")


if __name__ == "__main__":
    unittest.main()