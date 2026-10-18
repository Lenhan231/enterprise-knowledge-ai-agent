"""Guard the interfaces combined when merging main into translated retrieval."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.main import AskRequest
from core.database.document_chunks_repository import DocumentChunkRepository
from core.retrieval.retrieval import RetrievalRequest
from core.retrieval.retrieval_service import RetrievalService


class MainMergeCompatibilityTest(unittest.TestCase):
    def test_app_accepts_translation_and_retains_decision_mode_fields(self):
        request = AskRequest(question="Revenue in 2008?", retrieval_method="translated_hybrid")
        self.assertEqual(request.retrieval_method, "translated_hybrid")
        self.assertFalse(request.decision_suggestions)
        self.assertIsNone(request.business_decision_domain)
        page = (Path(__file__).resolve().parents[1] / "src/app/static/index.html").read_text()
        self.assertIn('value="translated_hybrid"', page)

    def test_embedding_failure_retains_document_and_metadata_scope_in_bm25_fallback(self):
        repo = DocumentChunkRepository.__new__(DocumentChunkRepository)
        repo.conn = MagicMock()
        cursor = repo.conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        embedding = MagicMock()
        embedding.embed_query.side_effect = RuntimeError("embedding unavailable")
        response = RetrievalService(embedding, repo).retrieve(
            RetrievalRequest(query="revenue"), method="hybrid", document_ids=["DOC"],
            metadata_filter={"domain": "finance"}, company="Company", roles=["employee"])
        self.assertEqual(response.method, "bm25")
        sql, params = cursor.execute.call_args.args
        for clause in ["d.document_id = ANY(%s::text[])", "c.metadata @> %s::jsonb",
                       "d.knowledge_base_active IS TRUE", "d.company = %s::text",
                       "d.allowed_roles && %s::text[]"]:
            self.assertIn(clause, sql)
        self.assertIn(["DOC"], [x for x in params if isinstance(x, list)])
        self.assertIn('{"domain": "finance"}', params)
        self.assertNotIn("vector_candidates AS", sql)


if __name__ == "__main__":
    unittest.main()
