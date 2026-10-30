import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call

import numpy as np
from pydantic import ValidationError


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.database.document_chunks_repository import DocumentChunkRepository
from core.retrieval.retrieval import RetrievedChunk


class DocumentChunkRepositorySearchTest(unittest.TestCase):
    def setUp(self):
        # Exercise the real search method without connecting to PostgreSQL.
        self.repository = DocumentChunkRepository.__new__(DocumentChunkRepository)
        self.repository.conn = MagicMock()
        self.cursor = self.repository.conn.cursor.return_value.__enter__.return_value

    def test_document_inspection_reads_ready_indexed_chunks_with_company_filter(self):
        self.cursor.description = [
            MagicMock(name="chunk_index"), MagicMock(name="content"),
            MagicMock(name="metadata"), MagicMock(name="processing_status"),
            MagicMock(name="processing_error"),
        ]
        for column, name in zip(self.cursor.description,
                                ("chunk_index", "content", "metadata", "processing_status", "processing_error")):
            column.name = name
        self.cursor.fetchall.return_value = [(0, "indexed text", {"document_id": "DOC-1"}, "embedded", None)]

        rows = self.repository.get_document_chunks("DOC-1", limit=10, offset=20, company="Vinamilk")

        self.assertEqual(rows[0]["content"], "indexed text")
        sql, params = self.cursor.execute.call_args.args
        normalized = " ".join(sql.lower().split())
        self.assertIn("join public.documents", normalized)
        self.assertIn("coalesce(d.processing_status, 'ready') = 'ready'", normalized)
        self.assertEqual(params, ("DOC-1", "Vinamilk", "Vinamilk", 10, 20))

    def test_replace_document_deletes_by_stable_id_and_keeps_source_filename(self):
        rows = [("report.pdf", 0, "content", {"document_id": "DOC-1"}, [0.1])]

        self.repository.replace_document("DOC-1", rows)

        statements = [call.args for call in self.cursor.execute.call_args_list]
        self.assertEqual(statements[0][1], ("DOC-1",))
        self.assertIn("metadata->>'document_id' = %s", " ".join(statements[0][0].split()))
        persisted = self.cursor.executemany.call_args.args[1][0]
        self.assertEqual(persisted[:3], rows[0][:3])
        self.assertEqual(persisted[3].obj, rows[0][3])

    def test_maps_rows_preserving_full_content_metadata_and_order(self):
        text = " Full content\n" * 3000
        metadata = {"document_id": "DOC-1", "document_type": "policy", "custom": {"tags": ["policy"]}}
        self.cursor.fetchall.return_value = [
            ("policy.pdf", 7, text, metadata, 0.81234),
            ("other.pdf", 0, "Other content", {"document_id": "DOC-2"}, -0.25),
        ]

        results = self.repository.similarity_search([0.1, 0.2], 2)

        self.assertTrue(all(isinstance(item, RetrievedChunk) for item in results))
        self.assertEqual(results[0].document_name, "policy.pdf")
        self.assertEqual(results[0].chunk_index, 7)
        self.assertEqual(results[0].content, text)
        self.assertEqual(results[0].metadata, metadata)
        self.assertEqual(results[0].document_id, "DOC-1")
        self.assertEqual([item.retrieval_score for item in results], [0.81234, -0.25])
        self.assertEqual([item.document_name for item in results], ["policy.pdf", "other.pdf"])

    def test_query_uses_cosine_order_and_bound_parameters(self):
        self.cursor.fetchall.return_value = []

        self.repository.similarity_search([0.1, 0.2], 3, query="profit, 2024?")

        self.cursor.execute.assert_called_once()
        sql, parameters = self.cursor.execute.call_args.args
        normalized = " ".join(sql.split())
        self.assertIn("SELECT e.document_name, e.chunk_index, e.content, e.metadata,", normalized)
        self.assertIn("JOIN documents AS d ON d.document_id = c.metadata->>'document_id'", normalized)
        self.assertIn("jsonb_build_object('document_type', d.document_type)", normalized)
        self.assertIn("d.processing_status = 'ready'", normalized)
        self.assertIn("d.knowledge_base_active IS TRUE", normalized)
        self.assertIn("cardinality(d.allowed_roles) > 0", normalized)
        self.assertIn("coalesce(%s::text IS NOT NULL AND c.metadata->>'fiscal_year' = %s, false)", normalized)
        self.assertIn("vector_candidates AS", normalized)
        self.assertIn("bm25_candidates AS", normalized)
        self.assertIn("unnest(to_tsvector('simple', %s))", normalized)
        self.assertIn("document_frequencies AS", normalized)
        self.assertIn("document_terms AS MATERIALIZED", normalized)
        self.assertIn("sum(term_frequency) AS document_length", normalized)
        self.assertNotIn("OVER (PARTITION BY", normalized)
        self.assertIn("ln(1.0 + (cs.document_count - df.document_frequency + 0.5)", normalized)
        self.assertEqual(len(parameters), 12)
        for vector in (parameters[0], parameters[1]):
            np.testing.assert_array_equal(vector, np.array([0.1, 0.2], dtype=np.float32))
        self.assertEqual(parameters[2:4], ["2024", "2024"])
        self.assertEqual(parameters[4], "profit | 2024")
        self.assertEqual(parameters[-1], 3)
        self.assertEqual(parameters[-5:-1], [1.0, 60, 2.0, 60])

    def test_hybrid_fusion_parameters_are_bound_and_validated(self):
        self.cursor.fetchall.return_value = []
        self.repository.similarity_search(
            [0.1, 0.2], 3, query="profit 2024", method="hybrid",
            dense_weight=2.0, bm25_weight=1.0, rrf_k=20,
        )
        sql, parameters = self.cursor.execute.call_args.args
        normalized = " ".join(sql.split())
        self.assertIn("%s / (%s + candidate_rank)", normalized)
        self.assertEqual(parameters[-5:-1], [2.0, 20, 1.0, 20])

        for values in ({"dense_weight": 0}, {"bm25_weight": -1}, {"rrf_k": -1}):
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, "hybrid weights"):
                self.repository.similarity_search([0.1, 0.2], 3, method="hybrid", **values)

    def test_lexical_query_removes_question_scaffolding(self):
        from core.database.document_chunks_repository import _lexical_tsquery
        self.assertEqual(
            _lexical_tsquery("Lợi nhuận sau thuế hợp nhất của Vinamilk năm 2024 là bao nhiêu?"),
            "lợi | nhuận | sau | thuế | hợp | nhất | 2024",
        )

    def test_explicit_year_prefers_one_year_but_not_comparisons(self):
        from core.database.document_chunks_repository import _explicit_fiscal_year
        self.assertEqual(_explicit_fiscal_year("revenue in 2024"), "2024")
        self.assertIsNone(_explicit_fiscal_year("compare 2023 and 2024 revenue"))
        self.assertIsNone(_explicit_fiscal_year("revenue trend"))

    def test_query_filters_by_roles_before_ranking(self):
        self.cursor.fetchall.return_value = []
        self.repository.similarity_search([0.1, 0.2], 4, company="Vinamilk", roles=["finance_analyst"])
        sql, parameters = self.cursor.execute.call_args.args
        normalized = " ".join(sql.split())
        self.assertIn("d.allowed_roles && %s::text[]", normalized)
        self.assertLess(normalized.index("d.allowed_roles &&"), normalized.index("vector_candidates AS"))
        self.assertLess(normalized.index("d.allowed_roles &&"), normalized.index("bm25_candidates AS"))
        self.assertEqual(parameters[2:4], [None, None])
        self.assertEqual(parameters[4:7], ["Vinamilk", ["finance_analyst"], ["finance_analyst"]])
        self.assertEqual(parameters[7], "")
        self.repository.conn.commit.assert_not_called()

    def test_method_selects_dense_bm25_or_hybrid_ranking(self):
        cases = {
            "dense": "v.similarity_score AS retrieval_score",
            "bm25": "b.bm25_score AS retrieval_score",
            "hybrid": "r.rrf_score AS retrieval_score",
        }
        for method, expected in cases.items():
            with self.subTest(method=method):
                self.cursor.fetchall.return_value = []
                self.repository.similarity_search([0.1, 0.2], 3, query="profit 2024", method=method)
                sql, _ = self.cursor.execute.call_args.args
                self.assertIn(expected, " ".join(sql.split()))

    def test_rejects_unknown_method_before_query(self):
        with self.assertRaisesRegex(ValueError, "method must be"):
            self.repository.similarity_search([0.1, 0.2], 3, method="sparse")
        self.cursor.execute.assert_not_called()

    def test_empty_search_returns_empty_list(self):
        self.cursor.fetchall.return_value = []
        self.assertEqual(self.repository.similarity_search([0.1, 0.2], 5), [])

    def test_equal_scores_preserve_cursor_order(self):
        self.cursor.fetchall.return_value = [
            ("z.pdf", 9, "first", {"document_id": "Z"}, 0.8),
            ("a.pdf", 1, "second", {"document_id": "A"}, 0.8),
        ]
        results = self.repository.similarity_search([0.1, 0.2], 2)
        self.assertEqual([item.document_name for item in results], ["z.pdf", "a.pdf"])

    def test_missing_document_id_fails_including_null_metadata(self):
        for metadata in (None, {}, {"document_id": ""}, {"document_id": " "}):
            with self.subTest(metadata=metadata):
                self.cursor.fetchall.return_value = [("no-fallback.pdf", 0, "text", metadata, 0.5)]
                with self.assertRaisesRegex(ValidationError, "metadata.document_id"):
                    self.repository.similarity_search([0.1, 0.2], 1)

    def test_parent_expansion_stays_within_section_and_reapplies_role_filter(self):
        self.cursor.fetchall.return_value = [
            ("DOC-1", 4, 2, "Earlier section passage"),
            ("DOC-1", 4, 3, "Previous passage"),
            ("DOC-1", 4, 4, "Anchor passage"),
            ("DOC-1", 4, 5, "Next passage"),
        ]
        anchor = RetrievedChunk(
            document_name="report.pdf", chunk_index=4, content="Anchor passage",
            metadata={"document_id": "DOC-1", "section_title": "Revenue", "page_number": 2},
            retrieval_score=0.9,
        )

        result = self.repository.expand_parent_contexts(
            [anchor], company="Vinamilk", roles=["finance_analyst"]
        )

        context = result[("DOC-1", 4)]
        self.assertEqual(context["text"], "Earlier section passage\nPrevious passage\nAnchor passage\nNext passage")
        self.assertEqual(context["chunk_indices"], [2, 3, 4, 5])
        self.assertEqual(context["parent_context_type"], "section_window")
        sql, parameters = self.cursor.execute.call_args.args
        normalized = " ".join(sql.split())
        self.assertIn("jsonb_to_recordset", normalized)
        self.assertIn("c.metadata->>'section_title' IS NOT DISTINCT FROM a.section_title", normalized)
        self.assertIn("c.metadata->>'page_number' IS NOT DISTINCT FROM a.page_number", normalized)
        self.assertIn("d.allowed_roles && %s::text[]", normalized)
        self.assertIn("d.processing_status = 'ready'", normalized)
        self.assertIn("d.knowledge_base_active IS TRUE", normalized)
        self.assertIn("cardinality(d.allowed_roles) > 0", normalized)
        self.assertEqual(parameters[1:3], [2, 2])
        self.assertEqual(parameters[3:], ["Vinamilk", ["finance_analyst"], ["finance_analyst"]])

    def test_parent_expansion_does_not_restore_an_anchor_rejected_by_the_database(self):
        self.cursor.fetchall.return_value = []
        anchor = RetrievedChunk(
            document_name="policy.pdf", chunk_index=0, content="Previously visible evidence",
            metadata={"document_id": "DOC-1"}, retrieval_score=0.9,
        )
        self.assertEqual(self.repository.expand_parent_contexts([anchor], roles=["employee"]), {})

    def test_invalid_row_is_not_silently_skipped(self):
        self.cursor.fetchall.return_value = [
            ("valid.pdf", 0, "text", {"document_id": "DOC"}, 0.8),
            ("invalid.pdf", 0, "text", {}, 0.7),
        ]
        with self.assertRaisesRegex(ValidationError, "metadata.document_id"):
            self.repository.similarity_search([0.1, 0.2], 2)


if __name__ == "__main__":
    unittest.main()
