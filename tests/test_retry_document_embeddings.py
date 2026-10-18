import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
spec = importlib.util.spec_from_file_location("retry_embeddings", ROOT / "scripts/retrieval/retry_document_embeddings.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RetryEmbeddingsTest(unittest.TestCase):
    def test_retry_uses_authoritative_roles_preserves_parser_and_records_ready_only_after_vectors(self):
        parsed, vectors, documents, embedder, counter = [MagicMock() for _ in range(5)]
        documents.list_knowledge_documents.return_value = [{
            "document_id": "DOC", "company": "Company", "source_type": "user_upload",
            "processing_status": "failed", "allowed_roles": ["employee"]}]
        parsed.get_document.return_value = [{"content": "source", "metadata": {"filename": "source.pdf"}}]
        embedder.model_name, embedder.max_sequence_length = "model", 512
        embedder.embed_documents.return_value = [[0.1]]
        chunks = [{"text": "bounded", "metadata": {"document_id": "WRONG", "allowed_roles": ["admin"]}}]
        events = []
        documents.update_processing_status.side_effect = lambda doc, status: events.append(status)
        vectors.replace_document.side_effect = lambda *args: events.append("vectors")
        with patch("core.tokenization.embedding_chunker.build_embedding_chunks", return_value=chunks):
            result = module.retry_document("DOC", parsed, vectors, documents, embedder, counter)
        self.assertEqual(events, ["processing", "vectors", "ready"])
        self.assertEqual(result["indexed_chunks"], 1)
        self.assertEqual(chunks[0]["metadata"]["allowed_roles"], ["employee"])
        self.assertEqual(chunks[0]["metadata"]["document_id"], "DOC")
        parsed.get_document.assert_called_once_with("DOC", company="Company")
        parsed.replace_document.assert_not_called()
        embedder.embed_documents.side_effect = RuntimeError("encode failed")
        with patch("core.tokenization.embedding_chunker.build_embedding_chunks", return_value=chunks), self.assertRaises(RuntimeError):
            module.retry_document("DOC", parsed, vectors, documents, embedder, counter)
        self.assertEqual(events[-1], "failed")
        self.assertEqual(vectors.replace_document.call_count, 1)

    def test_retry_refuses_ready_documents_before_writing(self):
        parsed, vectors, documents = MagicMock(), MagicMock(), MagicMock()
        documents.list_knowledge_documents.return_value = [{"document_id": "DOC", "source_type": "user_upload", "processing_status": "ready"}]
        with self.assertRaises(ValueError):
            module.retry_document("DOC", parsed, vectors, documents, MagicMock(), MagicMock())
        documents.update_processing_status.assert_not_called()
        vectors.replace_document.assert_not_called()


if __name__ == "__main__":
    unittest.main()
