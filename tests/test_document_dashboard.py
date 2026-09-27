import unittest
from pathlib import Path
import sys
from unittest.mock import MagicMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.database.document_repository import DocumentRepository
from core.agents.dashboard_agent import DashboardAgent
from core.models.agents import AgentRequest


class DocumentDashboardTest(unittest.TestCase):
    def test_manifest_upsert_persists_processing_status(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        document = {"document_id": "DOC-1", "processing_status": "processing"}

        repository.upsert_document(document)

        cursor = repository.conn.cursor.return_value.__enter__.return_value
        query = " ".join(cursor.execute.call_args.args[0].lower().split())
        self.assertIn("allowed_roles, access_scope, processing_status", query)
        self.assertIn("processing_status = excluded.processing_status", query)
        self.assertEqual(cursor.execute.call_args.args[1], document)
        repository.conn.commit.assert_called_once()

    def test_dashboard_aggregates_database_rows_without_company_constants(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        documents = [
            {"document_id": "DOC-1", "company": "Example JSC", "chunks": 3},
            {"document_id": "DOC-2", "company": "Another JSC", "chunks": 2},
        ]
        cursor.fetchall.side_effect = [documents, [], [], []]

        result = repository.corpus_dashboard("employee", "uploader")

        self.assertEqual(result["document_count"], 2)
        self.assertEqual(result["chunk_count"], 5)
        self.assertEqual(result["financial"], [])
        self.assertEqual(result["candidates"], [])
        for index in (0, 1, 2):
            query = " ".join(cursor.execute.call_args_list[index].args[0].lower().split())
            self.assertIn("coalesce(d.processing_status, 'ready') = 'ready'", query)
        first_query, first_params = cursor.execute.call_args_list[0].args
        self.assertNotIn("Vinamilk", first_query)
        self.assertEqual(first_params, (["employee"], "employee", "employee", "uploader"))
        domain_query = " ".join(cursor.execute.call_args_list[1].args[0].lower().split())
        self.assertIn("select d.company, d.domain, d.fiscal_year", domain_query)
        self.assertIn("group by d.company, d.domain, d.fiscal_year", domain_query)
        self.assertEqual(cursor.execute.call_count, 4)

    def test_dashboard_company_filter_scopes_all_queries_including_metrics_and_candidates(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect = [[], [], [], [], [], []]

        repository.corpus_dashboard(
            "admin", "admin-user", include_analytics=True, company="Vinamilk Ltd."
        )

        self.assertEqual(cursor.execute.call_count, 6)
        for query, parameters in (call.args for call in cursor.execute.call_args_list):
            self.assertIn("d.company = %s::text", query)
            self.assertEqual(parameters[-1], "Vinamilk Ltd.")

    def test_dashboard_agent_passes_trusted_company_scope(self):
        repository = Mock()
        repository.corpus_dashboard.return_value = {"documents": []}
        agent = DashboardAgent(repository)

        result = agent.run(AgentRequest(
            question="Show the dashboard",
            user_id="analyst",
            metadata={"role": "finance_analyst", "company": "Vinamilk Ltd."},
        ))

        repository.corpus_dashboard.assert_called_once_with(
            "finance_analyst", "analyst", include_analytics=True,
            company="Vinamilk Ltd.",
        )
        self.assertEqual(result.data, {"documents": []})

    def test_unreviewed_metric_candidates_are_only_returned_to_admins(self):
        candidate = {"id": 7, "status": "needs_review"}
        for role, expected_queries, candidates in (
            ("finance_analyst", 5, []),
            ("admin", 6, [candidate]),
        ):
            with self.subTest(role=role):
                repository = DocumentRepository.__new__(DocumentRepository)
                repository.conn = MagicMock()
                cursor = repository.conn.cursor.return_value.__enter__.return_value
                cursor.fetchall.side_effect = [[], [], [], [], [], [candidate]][:expected_queries]

                result = repository.corpus_dashboard(role, "reviewer", include_analytics=True)

                self.assertEqual(result["candidates"], candidates)
                self.assertEqual(cursor.execute.call_count, expected_queries)
                if role == "admin":
                    candidate_query = cursor.execute.call_args_list[-1].args[0]
                    self.assertIn("FROM extracted_metric_candidates", candidate_query)
                    self.assertIn("text_extraction_method", candidate_query)
                    self.assertIn("c.document_id", candidate_query)
                    self.assertIn("d.processing_status = 'ready'", candidate_query)
                    normalized = " ".join(candidate_query.lower().split())
                    self.assertIn("row_number() over", normalized)
                    self.assertIn("partition by candidate.document_id, candidate.metric_name", normalized)
                    self.assertIn("candidate.created_at desc, candidate.id desc", normalized)
                    self.assertIn("where c.review_rank = 1", normalized)
                    self.assertIn("not exists", normalized)
                    self.assertIn("candidate.status = 'needs_review'", normalized)

    def test_candidate_review_requires_fully_processed_document(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None

        reviewed = repository.review_metric_candidate(
            7, "verified", 42.0, "billion VND", "admin", "Vinamilk Ltd."
        )

        query = " ".join(cursor.execute.call_args.args[0].lower().split())
        self.assertFalse(reviewed)
        self.assertIn("from documents d", query)
        self.assertIn("d.processing_status='ready'", query)
        self.assertIn("candidate.status='needs_review'", query)
        self.assertIn("d.company=%s::text", query)
        self.assertEqual(cursor.execute.call_args.args[1][-2:], ("Vinamilk Ltd.", "Vinamilk Ltd."))

    def test_candidate_upsert_refreshes_pending_evidence_for_admin_queue(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        rows = [{
            "metric_name": "net_revenue",
            "metric_label": "Net revenue",
            "candidate_values": ["60,479"],
            "fiscal_year": 2023,
            "page_number": 2,
            "source_quote": "Net revenue 60,479 billion VND",
            "source_quote_hash": "hash",
        }]

        repository.save_metric_candidates("VNM-AR-2023-EN", rows)

        cursor = repository.conn.cursor.return_value.__enter__.return_value
        upsert = " ".join(cursor.executemany.call_args.args[0].lower().split())
        self.assertIn("on conflict", upsert)
        self.assertIn("created_at = now()", upsert)
        self.assertIn("status in ('needs_review', 'superseded')", upsert)
        supersede, params = cursor.execute.call_args.args
        supersede = " ".join(supersede.lower().split())
        self.assertIn("set status = 'superseded'", supersede)
        self.assertIn("old.status = 'needs_review'", supersede)
        self.assertIn("from unnest(%s::text[], %s::text[])", supersede)
        self.assertEqual(params, ("VNM-AR-2023-EN", ["net_revenue"], ["hash"]))

    def test_empty_reprocess_supersedes_pending_rows_without_deleting_history(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()

        repository.save_metric_candidates("DOC-EMPTY", [])

        cursor = repository.conn.cursor.return_value.__enter__.return_value
        supersede, params = cursor.execute.call_args.args
        self.assertIn("set status = 'superseded'", supersede.lower())
        self.assertEqual(params, ("DOC-EMPTY", [], []))


if __name__ == "__main__":
    unittest.main()
