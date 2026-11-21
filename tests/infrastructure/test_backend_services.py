import os
import subprocess
import sys
import unittest
import json
import io
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

class BackendServicesTest(unittest.TestCase):
    def test_remote_parser_imports_without_local_ocr_dependencies(self):
        code = '''
import base64
import importlib.abc
import os
import sys
from unittest.mock import patch

class BlockLocalOCR(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "cv2" or fullname.startswith("document_processing.docling_adapter"):
            raise ImportError("Local OCR must not be imported by the remote parser client")

sys.meta_path.insert(0, BlockLocalOCR())
from document_processing.document_processor import DocumentProcessor, SUPPORTED_FORMATS
assert ".pdf" in SUPPORTED_FORMATS
os.environ["DOCUMENT_PROCESSING_URL"] = "http://document-processing:8000"
with patch("core.services.client.post", return_value={"elements": [], "tables": [], "metadata": {}}) as post:
    result = DocumentProcessor().process("scan.pdf", b"pdf bytes", {})
    assert result["elements"] == []
    assert base64.b64decode(post.call_args.args[2]["content"]) == b"pdf bytes"
'''
        environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")}
        result = subprocess.run([sys.executable, "-c", code], env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_local_parser_still_calls_docling_when_remote_url_is_unset(self):
        from types import SimpleNamespace
        from document_processing.document_processor import DocumentProcessor
        constructor = Mock()
        constructor.return_value.process.return_value = {"elements": [], "tables": [], "metadata": {}}
        with patch.dict(os.environ, {"DOCUMENT_PROCESSING_URL": ""}), patch.dict(
            sys.modules, {"document_processing.docling_adapter.processor": SimpleNamespace(DoclingProcessor=constructor)},
        ):
            result = DocumentProcessor().process("a.txt", b"hello", {})
        constructor.assert_called_once_with({"parser_engine": "docling"})
        self.assertEqual(constructor.return_value.process.call_args.args[0], b"hello")
        self.assertEqual(result["metadata"]["filename"], "a.txt")

    def test_remote_embedding_does_not_load_local_model(self):
        from core.embeddings.embedding_service import _load_backend
        _load_backend.cache_clear()
        with patch.dict(os.environ, {"EMBEDDINGS_URL": "http://embeddings:8000"}), patch("core.services.client.post", return_value={"vectors": [[1.0]]}) as call:
            backend = _load_backend("test", "remote")
            self.assertEqual(backend.embed_query("query: hello"), [1.0])
            self.assertEqual(call.call_args.args[1], "/embed")
        _load_backend.cache_clear()

    @staticmethod
    def _http_response(body: bytes, content_type: str):
        response = io.BytesIO(body)
        response.headers = {"Content-Type": content_type}
        return response

    def _retrieve_remote(self, response, record=True, **kwargs):
        """Run RemoteRetrievalService.retrieve against a fake HTTP response; returns (result, events, heard, request)."""
        from core.latency import latency_events, stage_listener
        from core.retrieval.remote_service import RemoteRetrievalService
        from core.retrieval.retrieval import RetrievalRequest
        events, heard, sent = [], [], []
        tokens = (latency_events.set(events if record else None), stage_listener.set(lambda *a: heard.append(a)))
        try:
            with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "t"}), \
                    patch("core.retrieval.remote_service.urlopen",
                          side_effect=lambda request, timeout: sent.append(request) or response):
                result = RemoteRetrievalService("http://retrieval-api:8000").retrieve(
                    RetrievalRequest(query="policy", top_k=3), roles=["admin"], **kwargs)
        finally:
            latency_events.reset(tokens[0])
            stage_listener.reset(tokens[1])
        return result, events, heard, sent[0]

    def test_remote_retrieval_preserves_scope_and_response_contract(self):
        from core.retrieval.retrieval import RetrievalResponse
        expected = RetrievalResponse(query="policy", method="hybrid", latency_ms=2, results=[])
        response = self._http_response(json.dumps(expected.model_dump(mode="json")).encode(), "application/json")
        result, _, _, request = self._retrieve_remote(response, company="Example", method="hybrid", document_ids=["DOC-1"])
        self.assertEqual(result, expected)
        self.assertEqual(request.full_url, "http://retrieval-api:8000/retrieve?stream=1")
        self.assertEqual(request.get_header("Authorization"), "Bearer t")
        sent = json.loads(request.data)
        self.assertEqual((sent["roles"], sent["company"], sent["document_ids"]), (["admin"], "Example", ["DOC-1"]))

    def test_remote_retrieval_streams_stages_as_they_happen(self):
        from core.retrieval.retrieval import RetrievalResponse
        final = RetrievalResponse(query="policy", latency_ms=2, results=[], retrieval_details={"reranker_model": "m"})
        lines = [{"stage": "embedding", "state": "started"}, {"stage": "embedding", "state": "completed", "elapsed_ms": 12.5},
                 {"stage": "reranking", "state": "started"}, {"stage": "not_a_stage", "state": "started"},
                 {"stage": "reranking", "state": "completed", "elapsed_ms": 900},
                 {"result": final.model_dump(mode="json")}]
        body = "".join(json.dumps(line) + "\n" for line in lines).encode()

        result, events, heard, _ = self._retrieve_remote(self._http_response(body, "application/x-ndjson"))
        self.assertEqual(heard, [("embedding", "started"), ("embedding", "completed"),
                                 ("reranking", "started"), ("reranking", "completed")])
        self.assertEqual([(e["stage"], e["elapsed_ms"]) for e in events], [("embedding", 12.5), ("reranking", 900.0)])
        self.assertEqual(result.retrieval_details, {"reranker_model": "m"})

        # Nothing records timings here (the public proxy): the stages travel on with the result.
        passed, _, _, _ = self._retrieve_remote(self._http_response(body, "application/x-ndjson"), record=False)
        self.assertEqual([e["stage"] for e in passed.retrieval_details["stage_events"]], ["embedding", "reranking"])

        for broken in (b'{"stage": "embedding", "state": "started"}\n{"error": "Retrieval failed"}\n',
                       b'{"stage": "embedding", "state": "started"}\n'):
            with self.assertRaises(RuntimeError):
                self._retrieve_remote(self._http_response(broken, "application/x-ndjson"))

    def test_remote_retrieval_replays_timings_from_an_older_service(self):
        from core.retrieval.retrieval import RetrievalResponse
        remote = [{"stage": "embedding", "elapsed_ms": 12.5, "status": "completed"},
                  {"stage": "reranking", "elapsed_ms": 900, "status": "completed"},
                  {"stage": "not_a_stage", "elapsed_ms": 1, "status": "completed"},
                  {"stage": "database_retrieval", "elapsed_ms": "bad", "status": "completed"}]
        payload = RetrievalResponse(query="policy", latency_ms=2, results=[],
                                    retrieval_details={"stage_events": remote, "reranker_model": "m"}).model_dump(mode="json")
        response = self._http_response(json.dumps(payload).encode(), "application/json")
        result, events, heard, _ = self._retrieve_remote(response)
        self.assertEqual([e["stage"] for e in events], ["embedding", "reranking"])
        self.assertIn(("reranking", "completed"), heard)
        self.assertNotIn("stage_events", result.retrieval_details)
        self.assertEqual(result.retrieval_details["reranker_model"], "m")

    def test_remote_retrieval_refuses_unscoped_search(self):
        from core.retrieval.remote_service import RemoteRetrievalService
        from core.retrieval.retrieval import RetrievalRequest
        with self.assertRaisesRegex(PermissionError, "verified document roles"):
            RemoteRetrievalService("http://retrieval-api:8000").retrieve(
                RetrievalRequest(query="policy"), roles=None,
            )

    def test_public_remote_retrieval_uses_matching_session_and_server_scoped_identity(self):
        from core.retrieval.remote_service import RemoteRetrievalService, remote_session_context
        from core.retrieval.retrieval import RetrievalRequest, RetrievalResponse
        expected = RetrievalResponse(query="policy", method="hybrid", latency_ms=2, results=[])
        requests = []

        def open_url(request, timeout):
            requests.append(request)
            payload = ({"username": "alice", "role": "employee"}
                       if request.full_url.endswith("/api/auth/me")
                       else expected.model_dump(mode="json"))
            return io.BytesIO(json.dumps(payload).encode())

        context = remote_session_context.set({"token": "session-token", "subject": "alice", "role": "employee"})
        try:
            with patch.dict(os.environ, {"RETRIEVAL_SERVICE_AUTH": "session"}), \
                    patch("core.retrieval.remote_service.urlopen", side_effect=open_url):
                result = RemoteRetrievalService("https://api.example/api/retrieval").retrieve(
                    RetrievalRequest(query="policy", top_k=3), roles=["employee"], method="hybrid",
                )
        finally:
            remote_session_context.reset(context)

        self.assertEqual(result, expected)
        self.assertEqual(requests[0].full_url, "https://api.example/api/auth/me")
        self.assertEqual(requests[1].full_url, "https://api.example/api/retrieval/retrieve")
        self.assertEqual(requests[1].get_header("Authorization"), "Bearer session-token")
        self.assertNotIn("roles", json.loads(requests[1].data))

    def test_public_remote_retrieval_rejects_a_different_remote_identity(self):
        from core.retrieval.remote_service import RemoteRetrievalService, remote_session_context
        from core.retrieval.retrieval import RetrievalRequest
        context = remote_session_context.set({"token": "session-token", "subject": "alice", "role": "employee"})
        try:
            with patch.dict(os.environ, {"RETRIEVAL_SERVICE_AUTH": "session"}), \
                    patch("core.retrieval.remote_service.urlopen", return_value=io.BytesIO(
                        b'{"username":"admin","role":"admin"}')) as open_url:
                with self.assertRaisesRegex(PermissionError, "does not match"):
                    RemoteRetrievalService("https://api.example/api/retrieval").retrieve(
                        RetrievalRequest(query="policy"), roles=["employee"],
                    )
            open_url.assert_called_once()
        finally:
            remote_session_context.reset(context)

    def test_public_retrieval_proxy_uses_authenticated_user_role(self):
        import jwt
        from fastapi.testclient import TestClient
        from app.main import app
        from core.retrieval.retrieval import RetrievalResponse
        secret = "a" * 32
        token = jwt.encode({"sub": "alice", "role": "employee"}, secret, algorithm="HS256")
        result = RetrievalResponse(query="policy", method="translated_hybrid_rerank", latency_ms=1, results=[])
        with patch.dict(os.environ, {"AUTH_SECRET_KEY": secret,
                                     "RETRIEVAL_SERVICE_URL": "http://retrieval-api:8000",
                                     "RETRIEVAL_SERVICE_AUTH": "internal"}), \
                patch("core.retrieval.remote_service.RemoteRetrievalService.retrieve", return_value=result) as retrieve:
            client = TestClient(app)
            denied = client.post("/api/retrieval/retrieve", json={"query": "policy"})
            response = client.post("/api/retrieval/retrieve", headers={"Authorization": "Bearer " + token},
                                   json={"query": "policy"})
            forged = client.post("/api/retrieval/retrieve", headers={"Authorization": "Bearer " + token},
                                 json={"query": "policy", "roles": ["admin"]})

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(forged.status_code, 422)
        self.assertEqual(response.json()["query"], "policy")
        self.assertEqual(retrieve.call_args.kwargs["roles"], ["employee"])

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

    def test_retrieval_endpoint_requires_token_and_passes_scope(self):
        from unittest.mock import Mock
        from core.retrieval.retrieval import RetrievalResponse
        from core.services.runtime import app

        from core.latency import measure

        def fake_retrieve(*args, **kwargs):
            with measure("reranking"):
                pass
            return RetrievalResponse(query="policy", method="hybrid", latency_ms=1, results=[])

        service = Mock()
        service.retrieve.side_effect = fake_retrieve
        previous = getattr(app.state, "retrieval_service", None)
        app.state.retrieval_service = service
        self.addCleanup(
            lambda: setattr(app.state, "retrieval_service", previous)
            if previous is not None else delattr(app.state, "retrieval_service")
        )
        with patch.dict(os.environ, {"SERVICE_KIND": "retrieval"}):
            unauthorized = self.client.post("/retrieve", json={"query": "policy", "roles": ["admin"]})
            response = self.client.post(
                "/retrieve", headers=self.headers,
                json={"query": "policy", "roles": ["admin"], "company": "Example", "method": "hybrid"},
            )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["query"], "policy")
        stages = response.json()["retrieval_details"]["stage_events"]
        self.assertEqual([(e["stage"], e["status"]) for e in stages], [("reranking", "completed")])
        self.assertEqual(service.retrieve.call_args.kwargs["roles"], ["admin"])
        self.assertEqual(service.retrieve.call_args.kwargs["company"], "Example")

        with patch.dict(os.environ, {"SERVICE_KIND": "retrieval"}):
            streamed = self.client.post("/retrieve?stream=1", headers=self.headers,
                                        json={"query": "policy", "roles": ["admin"]})
        self.assertIn("ndjson", streamed.headers["content-type"])
        lines = [json.loads(line) for line in streamed.text.splitlines()]
        self.assertEqual([(l["stage"], l["state"]) for l in lines[:2]], [("reranking", "started"), ("reranking", "completed")])
        self.assertIn("elapsed_ms", lines[1])
        self.assertEqual(lines[2]["result"]["query"], "policy")

        service.retrieve.side_effect = RuntimeError("database password=secret")
        with patch.dict(os.environ, {"SERVICE_KIND": "retrieval"}), self.assertLogs("core.services.runtime", "ERROR"):
            failed = self.client.post("/retrieve?stream=1", headers=self.headers,
                                      json={"query": "policy", "roles": ["admin"]})
        self.assertEqual([json.loads(line) for line in failed.text.splitlines()], [{"error": "Retrieval failed"}])

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
        self.assertEqual(details["reranker_model"], "remote-unreported")
        reported = {"scores": [1.0, 2.0, 3.0], "model": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
                    "revision": "r", "max_pair_tokens": 512, "quantize": ""}
        with patch.dict(os.environ, {"RERANKER_URL": "http://reranker:8000"}), patch("core.services.client.post", return_value=reported):
            _, details = BGEReranker().rerank("hello", chunks, 2)
        self.assertEqual((details["reranker_model"], details["reranker_max_pair_tokens"]), (reported["model"], 512))

    def test_reranker_service_reports_its_loaded_model(self):
        import numpy as np
        from core.retrieval.reranker import MODEL_ID
        from core.services.runtime import app
        app.state.encoder = type("Encoder", (), {"predict": lambda self, pairs, **_: np.array([0.5] * len(pairs))})()
        with patch.dict(os.environ, {"SERVICE_KIND": "reranker"}):
            response = self.client.post("/rerank", headers=self.headers, json={"query": "q", "texts": ["a", "b"]})
        self.assertEqual(response.json()["scores"], [0.5, 0.5])
        self.assertEqual(response.json()["model"], MODEL_ID)

if __name__ == "__main__":
    unittest.main()
