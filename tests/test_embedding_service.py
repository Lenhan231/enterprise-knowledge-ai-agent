import sys
import unittest
from pathlib import Path

from langchain_core.embeddings import Embeddings


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.embeddings import EmbeddingService


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]


class EmbeddingServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = EmbeddingService(backend=FakeEmbeddings())

    def test_embed_documents_delegates_as_a_batch(self):
        self.assertEqual(self.service.embed_documents(["a", "abcd"]), [[1.0], [4.0]])

    def test_embed_query_delegates_one_query(self):
        self.assertEqual(self.service.embed_query("apple"), [5.0])


if __name__ == "__main__":
    unittest.main()
