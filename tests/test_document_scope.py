"""Verify document scope reaches SQL without replacing ready/company/role filters."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.database.document_chunks_repository import DocumentChunkRepository
from core.retrieval.retrieval import RetrievalRequest
from core.retrieval.retrieval_service import RetrievalService


class DocumentScopeTest(unittest.TestCase):
    def test_scope_is_parameterized_before_ranking_for_every_method(self):
        for scope in (None, [], ['DOC-A', 'DOC-B']):
            for method in ('dense', 'bm25', 'hybrid', 'parent'):
                with self.subTest(scope=scope, method=method):
                    repository = DocumentChunkRepository.__new__(DocumentChunkRepository)
                    repository.conn = MagicMock()
                    cursor = repository.conn.cursor.return_value.__enter__.return_value
                    cursor.fetchall.return_value = []
                    embedding = MagicMock()
                    embedding.embed_query.return_value = [0.1, 0.2]
                    service = RetrievalService(embedding, repository)
                    service.retrieve(RetrievalRequest(query='revenue 2008'), method=method,
                                     company='Company', roles=['employee'], document_ids=scope)
                    sql, params = cursor.execute.call_args.args
                    self.assertIn("coalesce(d.processing_status, 'ready') = 'ready'", sql)
                    self.assertIn('d.company = %s::text', sql)
                    self.assertIn('d.allowed_roles && %s::text[]', sql)
                    clause = 'd.document_id = ANY(%s::text[])'
                    if scope is None:
                        self.assertNotIn(clause, sql)
                    else:
                        self.assertIn(clause, sql)
                        self.assertLess(sql.index(clause), sql.index('LIMIT'))
                        self.assertIn(scope, [value for value in params if isinstance(value, list)])
                        self.assertNotIn('DOC-A', sql)

    def test_invalid_scope_is_rejected(self):
        service = RetrievalService(MagicMock(), MagicMock())
        for value in ('DOC-A', [None], [' ']):
            with self.subTest(value=value), self.assertRaises(ValueError):
                service.retrieve(RetrievalRequest(query='question'), document_ids=value)


if __name__ == '__main__':
    unittest.main()