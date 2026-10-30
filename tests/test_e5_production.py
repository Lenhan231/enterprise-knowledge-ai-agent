"""Pinned E5 profile and existing production index SQL; no model inference or database calls."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.embeddings.embedding_service import DEFAULT_EMBEDDING_MODEL, EmbeddingService, _load_backend
from core.embeddings.settings import E5_MODEL, E5_REVISION
from core.retrieval.methods.common import eligible_cte
from core.database.document_chunks_repository import DocumentChunkRepository
from core.database.document_repository import DocumentRepository


class E5ProductionTest(unittest.TestCase):
    def test_environment_selects_e5_by_default(self):
        self.assertEqual(DEFAULT_EMBEDDING_MODEL, E5_MODEL)

    def test_prefixes_normalization_and_chunk_prefix_reserve(self):
        backend = MagicMock()
        backend.embed_documents.return_value = [[2.0] + [0.0] * 767]
        backend.embed_query.return_value = [0.0, 3.0] + [0.0] * 766
        service = EmbeddingService(E5_MODEL, backend)
        self.assertEqual(service.embed_documents(["passage"]), [[1.0] + [0.0] * 767])
        self.assertEqual(service.embed_query("question"), [0.0, 1.0] + [0.0] * 766)
        backend.embed_documents.assert_called_once_with(["passage: passage"])
        backend.embed_query.assert_called_once_with("query: question")
        self.assertEqual(service.max_sequence_length, 508)
        backend.embed_query.return_value = [0.0] * 768
        with self.assertRaises(ValueError):
            service.embed_query("question")
        backend.embed_query.return_value = [1.0] * 384
        with self.assertRaises(ValueError):
            service.embed_query("question")

    def test_local_model_load_pins_revision_and_normalization(self):
        _load_backend.cache_clear()
        try:
            with patch("langchain_huggingface.HuggingFaceEmbeddings") as constructor:
                encoder = constructor.return_value._client
                encoder.__getitem__.return_value.auto_model.config.max_position_embeddings = 514
                EmbeddingService(E5_MODEL, backend_name="local")
                self.assertEqual(constructor.call_args.kwargs["model_kwargs"]["revision"], E5_REVISION)
                self.assertTrue(constructor.call_args.kwargs["encode_kwargs"]["normalize_embeddings"])
                self.assertEqual(encoder.max_seq_length, 512)
        finally:
            _load_backend.cache_clear()

    def test_sql_keeps_production_table_and_trusted_filters(self):
        sql, params = eligible_cte([0.1] * 768, "question 2022", "Company", ["employee"],
            include_vector=True, include_lexical=True, document_ids=["DOC"], metadata_filter={"domain": "test"})
        self.assertIn("FROM document_chunks AS c", sql)
        self.assertIn("c.metadata->>'fiscal_year' = %s", sql)
        self.assertNotIn("d.fiscal_year", sql)
        self.assertEqual(params[2:4], ["2022", "2022"])
        for clause in ["c.metadata->>'company' = %s::text", "d.allowed_roles && %s::text[]",
                       "d.processing_status = 'ready'", "d.knowledge_base_active IS TRUE",
                       "'admin' = ANY(%s::text[])",
                       "d.document_id = ANY(%s::text[])", "c.metadata @> %s::jsonb"]:
            self.assertIn(clause, sql)


if __name__ == "__main__":
    unittest.main()
