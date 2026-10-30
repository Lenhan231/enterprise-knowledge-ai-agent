import builtins
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.embeddings import Embeddings


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.embeddings import EmbeddingService
from core.embeddings.embedding_service import _load_backend


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]


class EmbeddingServiceTest(unittest.TestCase):
    def setUp(self):
        _load_backend.cache_clear()
        self.addCleanup(_load_backend.cache_clear)
        self.service = EmbeddingService(model_name="fake-model", backend=FakeEmbeddings())

    def test_embed_documents_delegates_as_a_batch(self):
        self.assertEqual(self.service.embed_documents(["a", "abcd"]), [[1.0], [4.0]])

    def test_embed_query_delegates_one_query(self):
        self.assertEqual(self.service.embed_query("apple"), [5.0])

    def test_default_backend_is_shared_across_request_scoped_services(self):
        with patch("langchain_huggingface.HuggingFaceEmbeddings") as constructor:
            first = EmbeddingService(model_name="cache-test-model", backend_name="local")
            second = EmbeddingService(model_name="cache-test-model", backend_name="local")

        self.assertIs(first._backend, second._backend)
        constructor.assert_called_once_with(model_name="cache-test-model")

    def test_hosted_backend_uses_feature_extraction_without_local_model(self):
        _load_backend.cache_clear()
        original_import = builtins.__import__

        def reject_local_backend_import(name, *args, **kwargs):
            if name == "langchain_huggingface":
                raise AssertionError("Hosted backend must not import local model dependencies")
            return original_import(name, *args, **kwargs)

        with patch("core.embeddings.embedding_service.InferenceClient") as client_type, \
             patch("builtins.__import__", side_effect=reject_local_backend_import), \
             patch.dict("os.environ", {"HUGGINGFACE_API_KEY": "test-token"}):
            client = client_type.return_value
            client.feature_extraction.side_effect = [[0.1, 0.2], [[0.3, 0.4], [0.5, 0.6]]]
            service = EmbeddingService(model_name="test-model", backend_name="huggingface_inference")

            self.assertEqual(service.embed_query("query"), [0.1, 0.2])
            self.assertEqual(service.embed_documents(["a", "b"]), [[0.3, 0.4], [0.5, 0.6]])

        client_type.assert_called_once_with(model="test-model", token="test-token")


if __name__ == "__main__":
    unittest.main()
