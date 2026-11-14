from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.analytics.sql_safety import UnsafeAnalyticsQuery, validate_analytics_sql
from core.database.document_repository import DocumentRepository


class DocumentAnalyticsSafetyTest(unittest.TestCase):
    def test_adds_default_limit(self):
        sql = "SELECT document_id, ARRAY_AGG(document_id) AS evidence_document_ids FROM authorized_documents"
        self.assertTrue(validate_analytics_sql(sql).endswith("LIMIT 100"))

    def test_rejects_non_select_and_multiple_statements(self):
        for sql in (
            "DELETE FROM public.documents",
            "SELECT document_id, ARRAY_AGG(document_id) AS evidence_document_ids FROM authorized_documents; SELECT 1",
        ):
            with self.subTest(sql=sql), self.assertRaises(UnsafeAnalyticsQuery):
                validate_analytics_sql(sql)

    def test_rejects_unapproved_sources_columns_joins_and_functions(self):
        statements = (
            "SELECT id, ARRAY_AGG(document_id) AS evidence_document_ids FROM public.documents",
            "SELECT password, ARRAY_AGG(document_id) AS evidence_document_ids FROM authorized_documents",
            "SELECT d.document_id, ARRAY_AGG(d.document_id) AS evidence_document_ids FROM authorized_documents d JOIN authorized_documents e ON TRUE",
            "SELECT pg_sleep(5), ARRAY_AGG(document_id) AS evidence_document_ids FROM authorized_documents",
            "SELECT document_id, ARRAY_AGG(document_id) AS evidence_document_ids FROM (SELECT document_id FROM authorized_documents) q",
        )
        for sql in statements:
            with self.subTest(sql=sql), self.assertRaises(UnsafeAnalyticsQuery):
                validate_analytics_sql(sql)

    def test_requires_aggregated_source_ids_for_citations(self):
        with self.assertRaises(UnsafeAnalyticsQuery):
            validate_analytics_sql("SELECT document_id AS evidence_document_ids FROM authorized_documents")

    def test_rejects_duplicate_result_names_that_could_hide_citation_array(self):
        sql = (
            "SELECT ARRAY_AGG(document_id) AS evidence_document_ids, "
            "document_id AS evidence_document_ids FROM authorized_documents"
        )
        with self.assertRaises(UnsafeAnalyticsQuery):
            validate_analytics_sql(sql)

    def test_repository_runs_authorized_query_read_only_with_role_filter(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.description = [SimpleNamespace(name="matched_rows"), SimpleNamespace(name="evidence_document_ids")]
        cursor.fetchall.return_value = [{"matched_rows": 0, "evidence_document_ids": []}]

        result = repository.execute_authorized_analytics(
            "SELECT COUNT(document_id) AS matched_rows, "
            "ARRAY_AGG(DISTINCT document_id) AS evidence_document_ids FROM authorized_documents",
            "employee", "viewer",
        )

        executed = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn("SET TRANSACTION READ ONLY", executed)
        self.assertIn("SET LOCAL statement_timeout = '3s'", executed)
        cte_call = next(call for call in cursor.execute.call_args_list if "WITH authorized_documents" in call.args[0])
        self.assertIn("allowed_roles && %s::text[]", cte_call.args[0])
        self.assertEqual(cte_call.args[1], (["employee"], "employee", "employee", "viewer"))
        self.assertEqual(result["results"][0]["matched_rows"], 0)

    def test_repository_revalidates_sql_before_opening_a_transaction(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()

        with self.assertRaises(UnsafeAnalyticsQuery):
            repository.execute_authorized_analytics("DELETE FROM public.documents", "employee", "viewer")

        repository.conn.rollback.assert_not_called()
        repository.conn.cursor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
