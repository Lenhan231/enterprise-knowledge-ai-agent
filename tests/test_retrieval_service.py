import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.retrieval import RetrievalService


class FakeEmbeddingService:
    def __init__(self):
        self.questions = []

    def embed_query(self, question: str) -> list[float]:
        self.questions.append(question)
        return [0.1, 0.2]


class FakeRepository:
    def __init__(self):
        self.search_args = None
        self.closed = False

    def similarity_search(self, embedding: list[float], limit: int):
        self.search_args = (embedding, limit)
        return [
            (
                "policy.pdf",
                7,
                "Relevant policy text",
                {"document_id": "APL-CMP-001"},
                0.81234,
            )
        ]

    def close(self):
        self.closed = True


class RetrievalServiceTest(unittest.TestCase):
    def setUp(self):
        self.embeddings = FakeEmbeddingService()
        self.repository = FakeRepository()
        self.service = RetrievalService(self.embeddings, self.repository)

    def test_retrieve_embeds_question_and_maps_repository_results(self):
        result = self.service.retrieve("What is required?", limit=3)

        self.assertEqual(self.embeddings.questions, ["What is required?"])
        self.assertEqual(self.repository.search_args, ([0.1, 0.2], 3))
        self.assertEqual(result["question"], "What is required?")
        self.assertEqual(result["contexts"][0]["document_name"], "policy.pdf")
        self.assertEqual(result["contexts"][0]["similarity_score"], 0.81234)

    def test_close_delegates_to_repository(self):
        self.service.close()

        self.assertTrue(self.repository.closed)


if __name__ == "__main__":
    unittest.main()
