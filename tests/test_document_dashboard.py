import unittest
from pathlib import Path
import sys
from unittest.mock import MagicMock, Mock

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.analytics.sql_safety import UnsafeAnalyticsQuery
from core.database.document_repository import (
    DocumentRepository,
    link_financial_metric_source_chunk,
)
from core.agents.dashboard_agent import DashboardAgent
from core.models.agents import AgentRequest, AgentResult, Evidence


class DocumentDashboardTest(unittest.TestCase):
    def test_commerce_query_error_preserves_postgres_error_category_for_agent_repair(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = [None, None, psycopg.errors.UndefinedColumn("missing column")]

        with self.assertRaisesRegex(UnsafeAnalyticsQuery, "UndefinedColumn, SQLSTATE 42703"):
            repository.execute_commerce_analytics(
                "SELECT i.category, COUNT(*) AS products FROM commerce.inventory i "
                "GROUP BY i.category LIMIT 10", "inventory_allocation",
            )

    def test_knowledge_file_list_exposes_source_type_for_admin_ui(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        policy = {"document_id": "CD-POL-INV-001", "synthetic_company_policy": True,
                  "knowledge_base_active": False,
                  "evidence_class": "company_policy_reference"}
        cursor.fetchall.return_value = [policy]

        result = repository.list_knowledge_documents()

        self.assertEqual(result, [policy])
        query = " ".join(cursor.execute.call_args.args[0].lower().split())
        self.assertIn("max(c.metadata->>'evidence_class') as evidence_class", query)
        self.assertIn("bool_or(c.metadata->>'synthetic_company_policy' = 'true')", query)
        self.assertIn("left join public.document_chunks c", query)
        self.assertNotIn("where d.knowledge_base_active", query)
        self.assertFalse(result[0]["knowledge_base_active"])

    def test_failed_upload_without_indexed_chunks_remains_visible_in_file_management(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        failed_upload = {
            "document_id": "UPLOAD-failed", "title": "OCR test only",
            "processing_status": "failed", "knowledge_base_active": True,
            "chunk_count": 0, "allowed_roles": ["admin"],
        }
        cursor.fetchall.return_value = [failed_upload]

        result = repository.list_knowledge_documents()

        self.assertEqual(result[0]["processing_status"], "failed")
        self.assertEqual(result[0]["chunk_count"], 0)
        query = " ".join(cursor.execute.call_args.args[0].lower().split())
        self.assertIn("left join public.document_chunks c", query)

    def test_failed_upload_can_be_removed_from_retrieval_before_it_has_indexed_chunks(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"document_id": "UPLOAD-failed"}

        removed = repository.set_knowledge_base_active("UPLOAD-failed", False)

        self.assertTrue(removed)
        query = " ".join(cursor.execute.call_args.args[0].lower().split())
        self.assertIn("set knowledge_base_active = %s", query)
        self.assertIn("(%s is false or (", query)
        self.assertEqual(cursor.execute.call_args.args[1], (False, "UPLOAD-failed", False))

    def test_failed_upload_without_indexed_chunks_cannot_be_restored_to_retrieval(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None

        restored = repository.set_knowledge_base_active("UPLOAD-failed", True)

        self.assertFalse(restored)
        query = " ".join(cursor.execute.call_args.args[0].lower().split())
        self.assertIn("processing_status = 'ready'", query)
        self.assertIn("exists (", query)

    def test_commerce_dashboard_runs_only_requested_aggregates(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value

        result = repository.commerce_dashboard(("inventory_latest_flag_overlap",))

        self.assertEqual(cursor.fetchall.call_count, 1)
        self.assertEqual(set(result), {"inventory_latest_flag_overlap", "data_notes"})

    def test_slow_commerce_dashboard_aggregates_read_refreshed_database_views(self):
        cases = (
            (("promotions_by_year",), "commerce.dashboard_promotions_by_year"),
            (("promotions_by_campaign",), "commerce.dashboard_promotions_by_campaign"),
            (("logistics_by_year_region",), "commerce.dashboard_logistics_by_year_region"),
        )
        for keys, view in cases:
            with self.subTest(view=view):
                repository = DocumentRepository.__new__(DocumentRepository)
                repository.conn = MagicMock()
                cursor = repository.conn.cursor.return_value.__enter__.return_value

                repository.commerce_dashboard(keys)

                query = " ".join(cursor.execute.call_args.args[0].lower().split())
                self.assertIn(f"select * from {view}", query)

    def test_commerce_dashboard_scopes_data_notes_to_requested_domain(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        cases = (
            (("inventory_by_year",), "days_of_supply", ("Promotion comparisons", "Geography is grouped")),
            (("promotions_by_year",), "randomized holdout", ("days_of_supply", "Geography is grouped")),
            (("logistics_by_year_region",), "carrier, warehouse origin", ("randomized holdout", "days_of_supply")),
        )

        for keys, expected_note, excluded_notes in cases:
            with self.subTest(keys=keys):
                notes = repository.commerce_dashboard(keys)["data_notes"]
                joined = " ".join(notes)
                self.assertIn("synthetic competition data", joined)
                self.assertIn(expected_note, joined)
                for excluded in excluded_notes:
                    self.assertNotIn(excluded, joined)

    def test_commerce_dashboard_rejects_unknown_aggregate_key(self):
        repository = DocumentRepository.__new__(DocumentRepository)

        with self.assertRaisesRegex(ValueError, "Unsupported Commerce dashboard aggregates"):
            repository.commerce_dashboard(("typo",))

    def test_commerce_dashboard_counts_latest_products_with_both_inventory_flags(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        overlap = [{
            "snapshot_date": "2022-12-31", "product_rows": 424,
            "stockout_flagged_rows": 232, "overstock_flagged_rows": 232,
            "both_flagged_rows": 232,
        }]
        cursor.fetchall.side_effect = [[], [], [], [], [], overlap, [], [], []]

        result = repository.commerce_dashboard()

        self.assertEqual(result["inventory_latest_flag_overlap"], overlap)
        query = next(
            " ".join(call.args[0].lower().split())
            for call in cursor.execute.call_args_list
            if "both_flagged_rows" in call.args[0].lower()
        )
        self.assertIn("max(snapshot_date)", query)
        self.assertIn("i.stockout_flag and i.overstock_flag", query)
        self.assertIn("as both_flagged_rows", query)

    def test_commerce_dashboard_returns_year_end_category_snapshots_for_the_year_filter(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        snapshots = [{
            "year": 2021, "snapshot_date": "2021-12-31", "category": "Outdoor",
            "products": 12, "stockout_products": 3, "overstock_products": 4,
            "both_flagged_products": 2,
        }]
        cursor.fetchall.return_value = snapshots

        result = repository.commerce_dashboard(("inventory_year_end_by_category",))

        self.assertEqual(result["inventory_year_end_by_category"], snapshots)
        query = cursor.execute.call_args.args[0].lower()
        self.assertIn("max(snapshot_date)", query)
        self.assertIn("group by year", query)
        self.assertIn("using (year, snapshot_date)", query)

    def test_commerce_decision_snapshot_limits_data_to_relevant_recent_observations(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.commerce_dashboard = Mock(return_value={
            "inventory_by_year": [
                {"year": year, "stockout_snapshots": year, "overstock_snapshots": 1}
                for year in range(2018, 2024)
            ],
            "inventory_latest_by_category": [
                {"category": "A", "stockout_products": 2, "overstock_products": 1, "both_flagged_products": 1},
                {"category": "B", "stockout_products": 8, "overstock_products": 1, "both_flagged_products": 2},
            ],
            "inventory_latest_flag_overlap": [{
                "snapshot_date": "2022-12-31", "product_rows": 424,
                "stockout_flagged_rows": 232, "overstock_flagged_rows": 232,
                "both_flagged_rows": 232,
            }],
            "data_notes": [],
        })

        result = repository.commerce_decision_snapshot("inventory_allocation")

        repository.commerce_dashboard.assert_called_once_with((
            "inventory_by_year", "inventory_latest_by_category", "inventory_latest_flag_overlap",
        ))
        self.assertEqual([row["year"] for row in result["observations"]["inventory_by_year"]], [2021, 2022, 2023])
        self.assertEqual(result["observations"]["inventory_latest_by_category"][0]["category"], "B")
        self.assertEqual(result["observations"]["inventory_latest_flag_overlap"][0]["both_flagged_rows"], 232)
        self.assertEqual(result["source_tables"], ["commerce.inventory"])

    def test_commerce_promotion_snapshot_keeps_recent_campaign_window_results(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.commerce_dashboard = Mock(return_value={
            "promotions_by_year": [],
            "promotions_by_campaign": [
                {"year": year, "campaign": f"Campaign {year}-{index}", "net_item_sales": index}
                for year in range(2018, 2024) for index in range(14)
            ],
            "data_notes": [],
        })

        result = repository.commerce_decision_snapshot("promotion_planning")

        repository.commerce_dashboard.assert_called_once_with(("promotions_by_year", "promotions_by_campaign"))
        campaigns = result["observations"]["promotions_by_campaign"]
        self.assertEqual({row["year"] for row in campaigns}, {2021, 2022, 2023})
        self.assertEqual(len(campaigns), 36)
        self.assertTrue(all(row["net_item_sales"] >= 2 for row in campaigns))
        self.assertEqual(result["source_tables"], ["commerce.orders", "commerce.order_items", "commerce.products", "commerce.promotions"])

    def test_uploaded_source_lookup_requires_ready_upload_in_company_scope(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {
            "title": "Annual report", "format": "PDF", "storage_path": "UPLOAD-1/report.pdf",
        }

        result = repository.uploaded_source("UPLOAD-1", "Example Retailer", "admin", "reviewer")

        self.assertEqual(result["storage_path"], "UPLOAD-1/report.pdf")
        query, params = cursor.execute.call_args.args
        normalized = " ".join(query.lower().split())
        self.assertIn("source_type = 'user_upload'", normalized)
        self.assertIn("processing_status = 'ready'", normalized)
        self.assertIn("storage_path is not null", normalized)
        self.assertIn("allowed_roles && array[%s]::text[]", normalized)
        self.assertEqual(params, ("UPLOAD-1", "Example Retailer", "admin", "admin", "admin", "reviewer"))

    def test_synthetic_policy_source_lookup_enforces_active_status_and_document_roles(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"title": "Inventory policy", "format": "PDF"}

        result = repository.accessible_synthetic_policy_source(
            "CD-POL-INV-001", "Commerce Demo", "finance_analyst",
        )

        self.assertEqual(result["format"], "PDF")
        query, params = cursor.execute.call_args.args
        normalized = " ".join(query.lower().split())
        self.assertIn("source_type = 'synthetic_demo_policy'", normalized)
        self.assertIn("processing_status = 'ready'", normalized)
        self.assertIn("knowledge_base_active is true", normalized)
        self.assertIn("allowed_roles && array[%s]::text[]", normalized)
        self.assertEqual(params, ("CD-POL-INV-001", "Commerce Demo", "finance_analyst", "finance_analyst"))

    def test_manifest_upsert_persists_processing_status(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        document = {"document_id": "DOC-1", "processing_status": "processing", "knowledge_base_active": False}

        repository.upsert_document(document)

        cursor = repository.conn.cursor.return_value.__enter__.return_value
        query = " ".join(cursor.execute.call_args.args[0].lower().split())
        self.assertIn("allowed_roles, storage_path, processing_status, knowledge_base_active", query)
        self.assertIn("processing_status = excluded.processing_status", query)
        self.assertNotIn("allowed_roles = excluded.allowed_roles", query)
        self.assertNotIn("knowledge_base_active = excluded.knowledge_base_active", query)
        self.assertEqual(cursor.execute.call_args.args[1], {**document, "storage_path": None})
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
        for index in range(3):
            query = " ".join(cursor.execute.call_args_list[index].args[0].lower().split())
            self.assertIn("coalesce(d.processing_status, 'ready') = 'ready'", query)
            self.assertIn("d.knowledge_base_active is true", query)
            self.assertIn("'synthetic_demo_policy'", query)
        processing_query = " ".join(cursor.execute.call_args_list[3].args[0].lower().split())
        self.assertIn("'synthetic_demo_policy'", processing_query)
        first_query, first_params = cursor.execute.call_args_list[0].args
        self.assertNotIn("Example Retailer", first_query)
        self.assertIn("reference.metadata->'knowledge_domains'", first_query)
        self.assertIn("source_publisher", first_query)
        self.assertEqual(first_params, (["employee"], "employee", "employee", "uploader"))
        domain_query = " ".join(cursor.execute.call_args_list[1].args[0].lower().split())
        self.assertIn("select d.company, d.domain, d.fiscal_year", domain_query)
        self.assertIn("group by d.company, d.domain, d.fiscal_year", domain_query)
        self.assertEqual(cursor.execute.call_count, 4)

    def test_dashboard_agent_requires_a_commerce_domain(self):
        repository = Mock()
        agent = DashboardAgent(repository)

        result = agent.run(AgentRequest(
            question="Show the dashboard",
            user_id="analyst",
            metadata={"role": "finance_analyst"},
        ))

        repository.corpus_dashboard.assert_not_called()
        self.assertTrue(result.metadata["needs_domain_clarification"])
        self.assertIn("Inventory allocation", result.answer)

    def test_dashboard_does_not_fall_back_to_legacy_financial_metrics(self):
        repository = Mock()
        agent = DashboardAgent(repository)
        request = AgentRequest(
            question="Show a chart of revenue by year", user_id="analyst",
            metadata={"role": "finance_analyst"},
        )

        result = agent.run(request)

        repository.corpus_dashboard.assert_not_called()
        self.assertEqual(result.agent, "dashboard")
        self.assertTrue(result.metadata["needs_domain_clarification"])

    def test_dashboard_agent_creates_cited_commerce_fill_rate_chart(self):
        repository = Mock()
        repository.commerce_dashboard.return_value = {
            "inventory_by_year": [
                {"year": 2022, "avg_fill_rate": 0.89, "stockout_snapshots": 9, "overstock_snapshots": 2},
                {"year": 2023, "avg_fill_rate": 0.91, "stockout_snapshots": 8, "overstock_snapshots": 3},
                {"year": 2024, "avg_fill_rate": 0.94, "stockout_snapshots": 7, "overstock_snapshots": 4},
            ], "data_notes": ["Synthetic Commerce data."],
        }
        agent = DashboardAgent(repository)

        result = agent.run(AgentRequest(
            question="Show a chart of inventory fill rate by year from 2023 to 2024", user_id="analyst",
            metadata={"role": "analyst"},
        ))

        repository.commerce_dashboard.assert_called_once_with(("inventory_by_year", "inventory_latest_by_category", "inventory_latest_flag_overlap"))
        self.assertEqual(result.agent, "dashboard")
        self.assertEqual(result.data["visualization"]["categories"], [2023, 2024])
        self.assertEqual(result.data["visualization"]["unit"], "%")
        self.assertEqual(result.data["visualization"]["series"][0]["values"], [91.0, 94.0])
        self.assertIn("[C1]", result.answer)
        self.assertEqual(result.evidence[0].metadata["source_tables"], ["commerce.inventory"])
        self.assertEqual([row["year"] for row in result.evidence[0].metadata["commerce_observations"]], [2023, 2024])

    def test_dashboard_agent_charts_promotions_and_logistics_by_available_period(self):
        cases = (
            ("promotion_planning", "Show a chart of promotion net sales by year", {
                "promotions_by_year": [
                    {"year": 2023, "used_promotion": True, "net_sales": 30},
                    {"year": 2023, "used_promotion": False, "net_sales": 20},
                    {"year": 2024, "used_promotion": True, "net_sales": 40},
                    {"year": 2024, "used_promotion": False, "net_sales": 25},
                ],
            }, [2023, 2024]),
            ("nationwide_logistics", "Show a chart of transit time by region and year", {
                "logistics_by_year_region": [
                    {"year": 2023, "region": "North", "avg_transit_days": 2.0},
                    {"year": 2024, "region": "North", "avg_transit_days": 2.2},
                    {"year": 2023, "region": "South", "avg_transit_days": 3.0},
                    {"year": 2024, "region": "South", "avg_transit_days": 2.8},
                ],
            }, [2023, 2024]),
        )
        for domain, question, data, expected_years in cases:
            with self.subTest(domain=domain):
                repository = Mock()
                repository.commerce_dashboard.return_value = data
                result = DashboardAgent(repository).run(AgentRequest(
                    question=question, metadata={"role": "analyst", "business_decision_domain": domain},
                ))
                self.assertEqual(result.data["visualization"]["categories"], expected_years)
                self.assertEqual(len(result.data["visualization"]["series"]), 2)
                self.assertEqual(result.evidence[0].citation_id, "C1")

    def test_dashboard_agent_explains_when_requested_commerce_years_are_absent(self):
        repository = Mock()
        repository.commerce_dashboard.return_value = {
            "inventory_by_year": [
                {"year": 2020, "avg_fill_rate": 0.91},
                {"year": 2021, "avg_fill_rate": 0.92},
                {"year": 2022, "avg_fill_rate": 0.93},
            ],
        }

        result = DashboardAgent(repository).run(AgentRequest(
            question="Show inventory fill rate from 2023 to 2024", metadata={
                "role": "analyst", "business_decision_domain": "inventory_allocation",
            },
        ))

        self.assertIsNone(result.data["visualization"])
        self.assertEqual(result.data["visualization_status"], "no_matching_period")
        self.assertIn("Available years for Inventory allocation: 2020, 2021, 2022", result.answer)
        self.assertEqual(len(result.evidence[0].metadata["commerce_observations"]), 3)

    def test_dashboard_agent_requires_authenticated_role_before_querying(self):
        repository = Mock()
        with self.assertRaisesRegex(ValueError, "authenticated role"):
            DashboardAgent(repository).run(AgentRequest(
                question="Show a chart of revenue by year",
            ))
        repository.corpus_dashboard.assert_not_called()

    def test_candidate_review_requires_fully_processed_document(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None

        reviewed = repository.review_metric_candidate(
            7, "verified", 42.0, "billion VND", "admin", "Example Retailer Ltd."
        )

        query = " ".join(cursor.execute.call_args.args[0].lower().split())
        self.assertFalse(reviewed)
        self.assertIn("from documents d", query)
        self.assertIn("d.processing_status='ready'", query)
        self.assertIn("candidate.status='needs_review'", query)
        self.assertIn("d.company=%s::text", query)
        self.assertEqual(cursor.execute.call_args.args[1][-2:], ("Example Retailer Ltd.", "Example Retailer Ltd."))

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

        repository.save_metric_candidates("EXAMPLE-AR-2023-EN", rows)

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
        self.assertEqual(params, ("EXAMPLE-AR-2023-EN", ["net_revenue"], ["hash"]))

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

        repository.save_metric_candidates("EXAMPLE-AR-2025-EN", [row])

        values = cursor.executemany.call_args.args[1][0]
        self.assertEqual(values[13:15], (991, 7))
        self.assertEqual(values[15], hashlib.sha256(content.encode()).hexdigest())

    def test_financial_metric_link_prefers_structured_table_chunk_on_text_tie(self):
        import hashlib

        shared_content = "Gross profit 8.166.269 7.503.136"
        row = {
            "metric_name": "gross_profit", "metric_label": "Gross profit",
            "candidate_values": ["8.166.269"], "page_number": 92,
            "source_quote": "label: Lợi nhuận gộp | value_1: 8.166.269",
        }
        chunks = [
            {"id": 11, "chunk_index": 4, "content": shared_content,
             "page_number": "92", "metadata": {"layout_type": "text"}},
            {"id": 12, "chunk_index": 5, "content": shared_content,
             "page_number": "92", "metadata": {"layout_type": "table", "element_type": "table"}},
        ]

        self.assertEqual(
            link_financial_metric_source_chunk(row, chunks),
            (12, 5, hashlib.sha256(shared_content.encode()).hexdigest()),
        )

    def test_financial_metric_link_does_not_fallback_to_a_different_page(self):
        row = {
            "metric_name": "gross_profit", "metric_label": "Gross profit",
            "candidate_values": ["8,166,269"], "page_number": 92,
            "source_quote": "Gross profit 8,166,269",
        }

        self.assertEqual(link_financial_metric_source_chunk(row, [{
            "id": 1, "chunk_index": 0, "content": "Gross profit 8,166,269",
            "page_number": "91", "metadata": {"layout_type": "table"},
        }]), (None, None, None))

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
