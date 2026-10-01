import unittest
from pathlib import Path
import sys
from unittest.mock import MagicMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.database.document_repository import DocumentRepository
from core.analytics.business_metric_catalog import BUSINESS_VALUE_QUALIFIER_SQL
from core.agents.dashboard_agent import DashboardAgent, _financial_time_series
from core.models.agents import AgentRequest, AgentResult, Evidence


class DocumentDashboardTest(unittest.TestCase):
    def test_estimated_savings_are_not_exposed_as_exact_metrics(self):
        self.assertRegex(BUSINESS_VALUE_QUALIFIER_SQL, r"estimated\?|ước tính")
        self.assertIn("THEN 'approximately'", BUSINESS_VALUE_QUALIFIER_SQL)
        self.assertIn("[[:space:]])over[[:space:]]", BUSINESS_VALUE_QUALIFIER_SQL)
        self.assertNotIn("|over|", BUSINESS_VALUE_QUALIFIER_SQL)

    def test_uploaded_source_lookup_requires_ready_upload_in_company_scope(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {
            "title": "Annual report", "format": "PDF", "storage_path": "UPLOAD-1/report.pdf",
        }

        result = repository.uploaded_source("UPLOAD-1", "Vinamilk", "admin", "reviewer")

        self.assertEqual(result["storage_path"], "UPLOAD-1/report.pdf")
        query, params = cursor.execute.call_args.args
        normalized = " ".join(query.lower().split())
        self.assertIn("source_type = 'user_upload'", normalized)
        self.assertIn("processing_status = 'ready'", normalized)
        self.assertIn("storage_path is not null", normalized)
        self.assertIn("allowed_roles && array[%s]::text[]", normalized)
        self.assertEqual(params, ("UPLOAD-1", "Vinamilk", "admin", "admin", "admin", "reviewer"))

    def test_manifest_upsert_persists_processing_status(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        document = {"document_id": "DOC-1", "processing_status": "processing"}

        repository.upsert_document(document)

        cursor = repository.conn.cursor.return_value.__enter__.return_value
        query = " ".join(cursor.execute.call_args.args[0].lower().split())
        self.assertIn("allowed_roles, processing_status", query)
        self.assertIn("processing_status = excluded.processing_status", query)
        self.assertEqual(cursor.execute.call_args.args[1], document)
        repository.conn.commit.assert_called_once()

    def test_parser_candidate_enriches_one_matching_pending_research_record(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [{
            "id": 42, "chunk_index": 31, "content": "Source quote: milk supplied 402,000 tonnes",
        }]
        cursor.fetchone.side_effect = [None, {"id": 18}]
        candidate = {
            "company": "Vinamilk", "domain": "milk_supply", "metric_name": "total_raw_milk_supply",
            "metric_label": "Total raw milk supply", "fiscal_year": 2024, "metric_value": 402000,
            "unit": "tonnes", "scope": "Annual reported supply", "source_document_id": "VNM-AR-2024-VI",
            "page_number": 31, "source_quote": "milk supplied 402,000 tonnes", "source_url": "https://example.test/report.pdf",
            "allowed_roles": ["admin"], "extraction_method": "llm_parser", "extractor_version": "v4",
            "extraction_config": {"pdf_page_number": 31}, "source_content_hash": "page-hash",
        }

        saved = repository.save_business_metric_candidates([candidate])

        self.assertEqual(saved, 1)
        self.assertEqual(cursor.execute.call_count, 3)
        refresh_query = " ".join(cursor.execute.call_args_list[1].args[0].lower().split())
        self.assertIn("candidate.entered_by = 'source_research'", refresh_query)
        self.assertIn("candidate.source_chunk_id is null", refresh_query)
        self.assertIn("candidate.status = 'needs_review'", refresh_query)
        query, params = cursor.execute.call_args_list[2].args
        normalized = " ".join(query.lower().split())
        self.assertIn("having count(*) = 1", normalized)
        self.assertIn("candidate.status = 'needs_review'", normalized)
        self.assertIn("candidate.entered_by = 'source_research'", normalized)
        self.assertIn("candidate.metric_value = %s", normalized)
        self.assertIn("not exists", normalized)
        self.assertEqual(params[:3], (31, "milk supplied 402,000 tonnes", "https://example.test/report.pdf"))
        self.assertEqual(params[-5:], (2024, "VNM-AR-2024-VI", 402000, "tonnes", 31))

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
        cursor.fetchall.side_effect = [[], [], [], [], [], [], [], []]

        repository.corpus_dashboard(
            "admin", "admin-user", include_analytics=True, company="Vinamilk Ltd."
        )

        self.assertEqual(cursor.execute.call_count, 8)
        for query, parameters in (call.args for call in cursor.execute.call_args_list):
            query = query.lower()
            self.assertTrue(any(scope in query for scope in (
                "d.company = %s::text", "m.company = %s::text",
                "coalesce(candidate.company, d.company) = %s::text",
                "(%s::text is null or company = %s::text)",
            )))
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

    def test_dashboard_agent_creates_only_source_backed_financial_time_series(self):
        repository = Mock()
        analytics = Mock()
        analytics.run.return_value = AgentResult(
            answer="Revenue by year [M1] [M2]", agent="analytics",
            evidence=[Evidence(
                citation_id="M1", source_type="verified_metric", source="FY2023 revenue",
                metadata={"document_id": "AR23"},
            ), Evidence(
                citation_id="M2", source_type="verified_metric", source="FY2024 revenue",
                metadata={"document_id": "AR24"},
            )],
            data={"financial": [
                {"metric_name": "net_revenue", "metric_label": "Net revenue", "fiscal_year": 2023,
                 "metric_value": "60322", "unit": "billion VND", "document_id": "AR23"},
                {"metric_name": "net_revenue", "metric_label": "Net revenue", "fiscal_year": 2024,
                 "metric_value": "61524", "unit": "billion VND", "document_id": "AR24"},
            ]},
        )
        agent = DashboardAgent(repository, analytics)
        request = AgentRequest(
            question="Show a chart of revenue by year", user_id="analyst",
            metadata={"role": "finance_analyst", "company": "Vinamilk"},
        )

        result = agent.run(request)

        analytics.run.assert_called_once()
        chart_request = analytics.run.call_args.args[0]
        self.assertEqual(chart_request.metadata["role"], "finance_analyst")
        self.assertEqual(chart_request.metadata["company"], "Vinamilk")
        self.assertTrue(chart_request.metadata["dashboard_visualization"])
        repository.corpus_dashboard.assert_not_called()
        self.assertEqual(result.agent, "dashboard")
        self.assertEqual(result.evidence[0].citation_id, "M1")
        self.assertEqual(result.data["visualization"]["categories"], [2023, 2024])
        self.assertEqual(result.data["visualization"]["series"][0]["values"], [60322.0, 61524.0])

    def test_financial_chart_rejects_ambiguous_or_incomparable_rows(self):
        base = {"metric_name": "net_revenue", "metric_label": "Net revenue", "unit": "billion VND"}
        rows = [
            {**base, "fiscal_year": 2023, "metric_value": 10},
            {**base, "fiscal_year": 2024, "metric_value": 12},
        ]
        self.assertIsNotNone(_financial_time_series(rows, "Revenue trend"))
        self.assertIsNone(_financial_time_series(rows + [rows[0]], "Revenue trend"))
        self.assertIsNone(_financial_time_series([
            rows[0], {**rows[1], "unit": "million VND"},
        ], "Revenue trend"))
        self.assertIsNone(_financial_time_series([
            rows[0], {**rows[1], "metric_value": "1e9999"},
        ], "Revenue trend"))

    def test_dashboard_agent_requires_authenticated_role_before_querying(self):
        analytics = Mock()
        repository = Mock()
        with self.assertRaisesRegex(ValueError, "authenticated role"):
            DashboardAgent(repository, analytics).run(AgentRequest(
                question="Show a chart of revenue by year",
            ))
        analytics.run.assert_not_called()
        repository.corpus_dashboard.assert_not_called()

    def test_unreviewed_metric_candidates_are_only_returned_to_admins(self):
        candidate = {"id": 7, "status": "needs_review"}
        for role, expected_queries, candidates in (
            ("finance_analyst", 6, []),
            ("admin", 8, [candidate]),
        ):
            with self.subTest(role=role):
                repository = DocumentRepository.__new__(DocumentRepository)
                repository.conn = MagicMock()
                cursor = repository.conn.cursor.return_value.__enter__.return_value
                cursor.fetchall.side_effect = [[], [], [], [], [], [], [], [candidate]][:expected_queries]

                result = repository.corpus_dashboard(role, "reviewer", include_analytics=True)

                self.assertEqual(result["candidates"], candidates)
                self.assertEqual(cursor.execute.call_count, expected_queries)
                if role == "admin":
                    candidate_query = cursor.execute.call_args_list[-1].args[0]
                    self.assertIn("FROM extracted_metric_candidates", candidate_query)
                    self.assertIn("text_extraction_method", candidate_query)
                    self.assertIn("candidate.extraction_method", candidate_query)
                    self.assertIn("candidate.selection_evidence", candidate_query)
                    self.assertIn("c.document_id", candidate_query)
                    self.assertIn("d.processing_status = 'ready'", candidate_query)
                    normalized = " ".join(candidate_query.lower().split())
                    self.assertIn("row_number() over", normalized)
                    self.assertIn("partition by coalesce(candidate.document_id, 'manual-' || candidate.id::text), candidate.metric_name", normalized)
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
            "unit": "billion VND",
        }]

        repository.save_metric_candidates("VNM-AR-2023-EN", rows)

        cursor = repository.conn.cursor.return_value.__enter__.return_value
        upsert = " ".join(cursor.executemany.call_args.args[0].lower().split())
        self.assertIn("on conflict", upsert)
        self.assertIn("created_at = now()", upsert)
        self.assertIn("selection_evidence = excluded.selection_evidence", upsert)
        self.assertEqual(upsert.count("unit = excluded.unit"), 1)
        self.assertNotIn("unit = null", upsert)
        candidate_values = cursor.executemany.call_args.args[1]
        self.assertEqual(candidate_values[0][8], "billion VND")
        self.assertEqual(candidate_values[0][9], "rule_based_page_evidence")
        self.assertEqual(candidate_values[0][12].obj, {})
        self.assertIn("status in ('needs_review', 'superseded')", upsert)
        supersede, params = cursor.execute.call_args.args
        supersede = " ".join(supersede.lower().split())
        self.assertIn("set status = 'superseded'", supersede)
        self.assertIn("old.status = 'needs_review'", supersede)
        self.assertIn("from unnest(%s::text[], %s::text[])", supersede)
        self.assertEqual(params, ("VNM-AR-2023-EN", ["net_revenue"], ["hash"]))

    def test_financial_candidate_links_to_unique_source_chunk_and_hash(self):
        import hashlib

        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        content = "Total revenue 63,724 billion VND"
        cursor.fetchall.return_value = [{
            "id": 991, "chunk_index": 7, "content": content, "page_number": "48",
        }]
        row = {
            "metric_name": "total_consolidated_revenue",
            "metric_label": "Total consolidated revenue",
            "candidate_values": ["63,724"], "fiscal_year": 2025,
            "page_number": 48, "source_quote": "In 2025, consolidated total revenue | 63,724",
            "source_quote_hash": "quote-hash", "unit": "billion VND",
        }

        repository.save_metric_candidates("VNM-AR-2025-EN", [row])

        values = cursor.executemany.call_args.args[1][0]
        self.assertEqual(values[13:15], (991, 7))
        self.assertEqual(values[15], hashlib.sha256(content.encode()).hexdigest())

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
