import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

class BackendServicesTest(unittest.TestCase):
    def test_remote_embedding_does_not_load_local_model(self):
        from core.embeddings.embedding_service import _load_backend
        _load_backend.cache_clear()
        with patch.dict(os.environ, {"EMBEDDINGS_URL": "http://embeddings:8000"}), patch("core.services.client.post", return_value={"vectors": [[1.0]]}) as call:
            backend = _load_backend("test", "remote")
            self.assertEqual(backend.embed_query("query: hello"), [1.0])
            self.assertEqual(call.call_args.args[1], "/embed")
        _load_backend.cache_clear()

    def test_parser_delegates_without_local_docling(self):
        from document_processing.document_processor import DocumentProcessor
        with patch.dict(os.environ, {"DOCUMENT_PROCESSING_URL": "http://document-processing:8000"}), patch("core.services.client.post", return_value={"elements": [], "tables": [], "metadata": {}}) as call:
            self.assertEqual(DocumentProcessor().process("a.txt", b"hello", {})["elements"], [])
            self.assertEqual(call.call_args.args[2]["filename"], "a.txt")

    def test_private_service_requires_token(self):
        from fastapi.testclient import TestClient
        from core.services.runtime import app
        with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "test-token"}):
            response = TestClient(app).post("/embed", json={"texts": ["a"]})
            self.assertEqual(response.status_code, 401)

class InternalRuntimeTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from core.services.runtime import app
        self.app = app
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token"}
        self.env = patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "test-token"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_embedding_preserves_prefixed_input(self):
        from unittest.mock import Mock
        self.app.state.encoder = Mock()
        self.app.state.encoder.embed_documents.return_value = [[0.5, 0.5]]
        with patch.dict(os.environ, {"SERVICE_KIND": "embeddings"}):
            response = self.client.post("/embed", headers=self.headers, json={"texts": ["query: hello"]})
        self.assertEqual(response.json(), {"vectors": [[0.5, 0.5]]})
        self.app.state.encoder.embed_documents.assert_called_once_with(["query: hello"])

    def test_embedding_rejects_oversized_batch(self):
        with patch.dict(os.environ, {"SERVICE_KIND": "embeddings"}):
            response = self.client.post("/embed", headers=self.headers, json={"texts": ["x"] * 33})
        self.assertEqual(response.status_code, 413)

    def test_embedding_rejects_a_different_model(self):
        with patch.dict(os.environ, {"SERVICE_KIND": "embeddings"}):
            response = self.client.post("/embed", headers=self.headers, json={"texts": ["x"], "model_name": "different-model"})
        self.assertEqual(response.status_code, 409)

    def test_remote_embedding_batches_and_checks_cardinality(self):
        from core.embeddings.embedding_service import RemoteEmbeddings
        with patch.dict(os.environ, {"EMBEDDINGS_URL": "http://embeddings:8000"}), patch("core.services.client.post", side_effect=[{"vectors": [[1.0]] * 32}, {"vectors": [[2.0]]}]) as call:
            result = RemoteEmbeddings("test").embed_documents(["a"] * 33)
        self.assertEqual(len(result), 33)
        self.assertEqual(call.call_count, 2)
        with patch.dict(os.environ, {"EMBEDDINGS_URL": "http://embeddings:8000"}), patch("core.services.client.post", return_value={"vectors": []}):
            with self.assertRaisesRegex(ValueError, "vector count"):
                RemoteEmbeddings("test").embed_query("a")

    def test_wrong_service_rejects_endpoint(self):
        with patch.dict(os.environ, {"SERVICE_KIND": "reranker"}):
            response = self.client.post("/embed", headers=self.headers, json={"texts": ["x"]})
        self.assertEqual(response.status_code, 404)

    def test_parser_rejects_invalid_base64(self):
        with patch.dict(os.environ, {"SERVICE_KIND": "document-processing"}):
            response = self.client.post("/parse", headers=self.headers, json={"filename": "a.pdf", "content": "!!!"})
        self.assertEqual(response.status_code, 422)

    def test_client_reports_upstream_failure_without_leaking_details(self):
        from urllib.error import URLError
        from core.services.client import post
        with patch("core.services.client.urlopen", side_effect=URLError("private host")):
            with self.assertRaisesRegex(RuntimeError, "Internal backend service unavailable"):
                post("http://embeddings:8000", "/embed", {"texts": ["a"]})

    def test_remote_parser_round_trips_preview_bytes(self):
        from document_processing.document_processor import DocumentProcessor
        with patch.dict(os.environ, {"DOCUMENT_PROCESSING_URL": "http://document-processing:8000"}), patch("core.services.client.post", return_value={"elements": [], "tables": [], "metadata": {}, "page_previews": {"1": "aGVsbG8="}}):
            result = DocumentProcessor().process("a.txt", b"hello", {})
        self.assertEqual(result["page_previews"], {"1": b"hello"})

    def test_remote_reranking_keeps_original_chunks_and_stable_ties(self):
        from dataclasses import dataclass, replace
        @dataclass
        class Chunk:
            chunk_index: int
            content: str = "text"
            retrieval_score: float = 0.8
            def model_copy(self, update):
                return replace(self, **update)
        from core.retrieval.reranker import BGEReranker
        chunks = [Chunk(i) for i in range(3)]
        with patch.dict(os.environ, {"RERANKER_URL": "http://reranker:8000"}), patch("core.services.client.post", return_value={"scores": [-2.0, 4.0, 4.0]}):
            ranked, details = BGEReranker().rerank("hello", chunks, 2)
        self.assertEqual([chunk.chunk_index for chunk in ranked], [1, 2])
        self.assertEqual(chunks[1].retrieval_score, 0.8)
        self.assertTrue(details["reranker_applied"])

if __name__ == "__main__":
    unittest.main()
