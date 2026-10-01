from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.analytics.sql_safety import UnsafeAnalyticsQuery, validate_analytics_sql
from core.database.document_repository import DocumentRepository
from core.models.agents import AgentRequest


class AnalyticsSqlSafetyTest(unittest.TestCase):
    def test_accepts_aggregate_select_and_caps_limit(self):
        sql = """SELECT metric_name, fiscal_year, SUM(metric_value) AS total,
                         ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids
                  FROM authorized_financial_metrics
                  GROUP BY metric_name, fiscal_year LIMIT 900"""
        normalized = validate_analytics_sql(sql)
        self.assertIn("LIMIT 100", normalized)
        self.assertIn("authorized_financial_metrics", normalized)

    def test_accepts_case_expressions_inside_allowlisted_aggregates(self):
        sql = """SELECT company, metric_name, fiscal_year,
                         SUM(CASE WHEN metric_name = 'Revenue' THEN metric_value END) AS revenue,
                         SUM(CASE WHEN metric_name = 'Profit' THEN metric_value END) AS profit,
                         ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids
                  FROM authorized_financial_metrics
                  GROUP BY company, metric_name, fiscal_year"""
        normalized = validate_analytics_sql(sql)
        self.assertIn("SUM(CASE", normalized)
        self.assertIn("LIMIT 100", normalized)

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
            "SELECT d.document_id, ARRAY_AGG(d.document_id) AS evidence_document_ids FROM authorized_documents d JOIN authorized_financial_metrics m ON TRUE",
            "SELECT pg_sleep(5), ARRAY_AGG(document_id) AS evidence_document_ids FROM authorized_documents",
            "SELECT document_id, ARRAY_AGG(document_id) AS evidence_document_ids FROM (SELECT document_id FROM authorized_documents) q",
        )
        for sql in statements:
            with self.subTest(sql=sql), self.assertRaises(UnsafeAnalyticsQuery):
                validate_analytics_sql(sql)

    def test_requires_aggregated_source_ids_for_citations(self):
        sql = "SELECT document_id AS evidence_document_ids FROM authorized_documents"
        with self.assertRaises(UnsafeAnalyticsQuery):
            validate_analytics_sql(sql)

    def test_financial_analytics_must_keep_metric_and_year_dimensions(self):
        sql = (
            "SELECT SUM(metric_value) AS total, "
            "ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids "
            "FROM authorized_financial_metrics"
        )
        with self.assertRaisesRegex(UnsafeAnalyticsQuery, "metric_name and fiscal_year"):
            validate_analytics_sql(sql)

    def test_business_metric_analytics_requires_exact_business_metric_citations(self):
        sql = """SELECT metric_name, fiscal_year, SUM(metric_value) AS total,
                         ARRAY_AGG(DISTINCT business_metric_id) AS evidence_business_metric_ids
                  FROM authorized_business_metrics
                  GROUP BY metric_name, fiscal_year"""
        self.assertIn("authorized_business_metrics", validate_analytics_sql(sql))
        with self.assertRaises(UnsafeAnalyticsQuery):
            validate_analytics_sql(
                "SELECT metric_name, fiscal_year, SUM(metric_value) AS total, "
                "ARRAY_AGG(DISTINCT business_metric_id) AS evidence_metric_ids "
                "FROM authorized_business_metrics GROUP BY metric_name, fiscal_year"
            )

    def test_export_market_question_fetches_optional_company_level_context(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [], "evidence": [], "business_evidence": [], "documents": [],
        }
        agent = SQLAnalyticsAgent(repository, Mock())

        agent.run(AgentRequest(
            question="Which export markets should Vinamilk prioritize for investment based on growth?",
            user_id="analyst", metadata={"role": "finance_analyst", "company": "Vinamilk"},
        ))

        query = repository.execute_authorized_analytics.call_args.args[0]
        for name in (
            "guinea_export_revenue_growth", "hong_kong_export_revenue_growth",
            "japan_export_revenue_growth", "export_net_revenue",
            "export_net_revenue_growth", "commercial_export_revenue",
            "commercial_export_revenue_growth", "export_volume_teu",
        ):
            self.assertIn(f"'{name}'", query)

    def test_selected_decision_domain_scopes_query_and_prompt_to_that_domain(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [], "evidence": [], "business_evidence": [], "documents": [],
        }
        llm = Mock()
        agent = SQLAnalyticsAgent(repository, llm)

        agent.run(AgentRequest(
            question="Which measures should management review before prioritizing market investment?",
            user_id="analyst",
            metadata={"role": "finance_analyst", "company": "Vinamilk",
                      "business_decision_domain": "market_performance"},
        ))

        query = repository.execute_authorized_analytics.call_args.args[0]
        self.assertIn("FROM authorized_business_metrics", query)
        self.assertIn("'domestic_consolidated_net_revenue'", query)
        self.assertIn("'overseas_market_net_revenue'", query)
        self.assertIn("'market_share_lead_over_runner_up'", query)
        self.assertNotIn("'employee_headcount'", query)
        self.assertNotIn("'total_water_consumption'", query)
        self.assertFalse(llm.generate.called)

    def test_vietnamese_market_position_question_uses_verified_metric_sql_without_llm(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [], "evidence": [], "business_evidence": [], "documents": [],
        }
        llm = Mock()

        SQLAnalyticsAgent(repository, llm).run(AgentRequest(
            question="Khoảng cách thị phần với đối thủ đứng thứ hai của Vinamilk năm 2024 là bao nhiêu?",
            user_id="analyst",
            metadata={"role": "finance_analyst", "company": "Vinamilk",
                      "business_decision_domain": "market_performance"},
        ))

        query = repository.execute_authorized_analytics.call_args.args[0]
        self.assertIn("'market_share_lead_over_runner_up'", query)
        self.assertIn("fiscal_year IN (2024)", query)
        self.assertFalse(llm.generate.called)

    def test_domain_question_keeps_supporting_market_metrics_in_scope(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [], "evidence": [], "business_evidence": [], "documents": [],
        }
        agent = SQLAnalyticsAgent(repository, Mock())

        agent.run(AgentRequest(
            question="Compare domestic and overseas segment gross profit for 2023.",
            user_id="analyst",
            metadata={"role": "finance_analyst", "company": "Vinamilk",
                      "business_decision_domain": "market_performance"},
        ))

        query = repository.execute_authorized_analytics.call_args.args[0]
        self.assertIn("'domestic_segment_gross_profit'", query)
        self.assertIn("'overseas_segment_gross_profit'", query)

    def test_rejects_duplicate_result_names_that_could_hide_citation_array(self):
        sql = (
            "SELECT ARRAY_AGG(document_id) AS evidence_document_ids, "
            "document_id AS evidence_document_ids FROM authorized_documents"
        )
        with self.assertRaises(UnsafeAnalyticsQuery):
            validate_analytics_sql(sql)

    def test_agent_generates_sql_executes_it_and_returns_provenance(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [{"metric_name": "net_revenue", "fiscal_year": 2024,
                         "total": 61824, "evidence_metric_ids": [1]}],
            "evidence": [{"company": "Vinamilk", "fiscal_year": 2024,
                          "metric_name": "net_revenue", "metric_label": "Net revenue",
                          "metric_value": 61824, "unit": "billion VND", "document_id": "AR24",
                          "metric_id": 1, "page_number": 12, "source_url": "https://example.test/ar24",
                          "source_quote": "Total revenue 61,824 billion VND", "source_chunk_id": 90,
                          "source_chunk_index": 4, "source_content_hash": "chunk-sha256"}],
            "documents": [],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT metric_name, fiscal_year, SUM(metric_value) AS total, '
            'ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids '
            'FROM authorized_financial_metrics WHERE fiscal_year = 2024 '
            'AND metric_name = \'net_revenue\' GROUP BY metric_name, fiscal_year"}'
        )
        agent = SQLAnalyticsAgent(repository, llm)
        result = agent.run(AgentRequest(
            question="Total verified revenue in 2024?", user_id="analyst",
            metadata={"role": "finance_analyst", "company": "Vinamilk"},
        ))
        self.assertIn("total: 61824", result.answer)
        self.assertIn("[M1]", result.answer)
        self.assertEqual(result.evidence[0].metadata["document_id"], "AR24")
        self.assertEqual(result.evidence[0].metadata["source_chunk_id"], 90)
        self.assertEqual(result.evidence[0].metadata["chunk_index"], 4)
        self.assertEqual(result.evidence[0].metadata["source_content_hash"], "chunk-sha256")
        repository.execute_authorized_analytics.assert_called_once()
        self.assertEqual(repository.execute_authorized_analytics.call_args.args[1:],
                         ("finance_analyst", "analyst", "Vinamilk"))
        self.assertIn("LIMIT 100", repository.execute_authorized_analytics.call_args.args[0])
        prompt = llm.generate.call_args.args[0]
        self.assertIn("total_consolidated_revenue", prompt)
        self.assertIn("profit_after_tax", prompt)
        self.assertIn("project metric_name and fiscal_year directly", prompt)
        self.assertIn("Do not add a company equality filter", prompt)

    def test_empty_aggregate_result_with_null_evidence_is_reported_as_no_verified_data(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [{"total": None, "evidence_metric_ids": None}],
            "evidence": [],
            "documents": [],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT metric_name, fiscal_year, SUM(metric_value) AS total, '
            'ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids '
            'FROM authorized_financial_metrics GROUP BY metric_name, fiscal_year"}'
        )
        result = SQLAnalyticsAgent(repository, llm).run(AgentRequest(
            question="Total verified revenue?", user_id="viewer",
            metadata={"role": "employee", "company": "Vinamilk"},
        ))

        self.assertEqual(result.answer, "No verified, role-visible data matched this analytics request.")
        self.assertEqual(result.data["results"], [])
        self.assertEqual(result.evidence, [])

    def test_repository_executes_inside_read_only_timeout_and_role_filtered_ctes(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()
        cursor = repository.conn.cursor.return_value.__enter__.return_value
        cursor.description = [SimpleNamespace(name="matched_rows"), SimpleNamespace(name="evidence_document_ids")]
        cursor.fetchall.return_value = [{"matched_rows": 0, "evidence_document_ids": []}]
        query = (
            "SELECT COUNT(document_id) AS matched_rows, "
            "ARRAY_AGG(DISTINCT document_id) AS evidence_document_ids FROM authorized_documents"
        )
        result = repository.execute_authorized_analytics(query, "employee", "viewer", "Vinamilk")
        executed = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn("SET TRANSACTION READ ONLY", executed)
        self.assertIn("SET LOCAL statement_timeout = '3s'", executed)
        repository.conn.rollback.assert_called_once()
        cte_call = next(call for call in cursor.execute.call_args_list if "WITH authorized_financial_metrics" in call.args[0])
        self.assertIn("allowed_roles && %s::text[]", cte_call.args[0])
        self.assertIn("case when d.fiscal_year ~ '^[0-9]{4}$' then d.fiscal_year::integer end as fiscal_year", " ".join(cte_call.args[0].lower().split()))
        self.assertIn("company = %s", cte_call.args[0])
        self.assertEqual(cte_call.args[1], (
            ["employee"], "employee", "Vinamilk", "Vinamilk",
            ["employee"], "employee", "Vinamilk", "Vinamilk",
            ["employee"], "employee", "employee", "viewer", "Vinamilk", "Vinamilk",
        ))
        self.assertEqual(result["results"][0]["matched_rows"], 0)

    def test_repository_revalidates_sql_before_opening_a_transaction(self):
        repository = DocumentRepository.__new__(DocumentRepository)
        repository.conn = MagicMock()

        with self.assertRaises(UnsafeAnalyticsQuery):
            repository.execute_authorized_analytics("DELETE FROM public.documents", "employee", "viewer")

        repository.conn.rollback.assert_not_called()
        repository.conn.cursor.assert_not_called()

    def test_metric_result_cites_only_matching_metric_and_year_within_same_document(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [{"metric_name": "net_revenue", "fiscal_year": 2024,
                         "total": 61824, "evidence_metric_ids": [1]}],
            "evidence": [
                {"company": "Vinamilk", "fiscal_year": 2024, "metric_name": "net_revenue",
                 "metric_label": "Consolidated revenue", "metric_value": 61824, "unit": "billion VND",
                 "document_id": "AR24", "metric_id": 1, "page_number": 12, "source_url": "https://example.test/ar24",
                 "source_quote": "Consolidated revenue 61,824 billion VND"},
                {"company": "Vinamilk", "fiscal_year": 2024, "metric_name": "profit_after_tax",
                 "metric_label": "Profit after tax", "metric_value": 9453, "unit": "billion VND",
                 "document_id": "AR24", "page_number": 12, "source_url": "https://example.test/ar24",
                 "source_quote": "Profit after tax 9,453 billion VND"},
                {"company": "Vinamilk", "fiscal_year": 2023, "metric_name": "net_revenue",
                 "metric_label": "Consolidated revenue", "metric_value": 60479, "unit": "billion VND",
                 "document_id": "AR24", "page_number": 12, "source_url": "https://example.test/ar24",
                 "source_quote": "Prior-year consolidated revenue 60,479 billion VND"},
            ],
            "documents": [],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT metric_name, fiscal_year, SUM(metric_value) AS total, '
            'ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids '
            'FROM authorized_financial_metrics WHERE metric_name = \'net_revenue\' '
            'AND fiscal_year = 2024 GROUP BY metric_name, fiscal_year"}'
        )

        result = SQLAnalyticsAgent(repository, llm).run(AgentRequest(
            question="Total net revenue in 2024?", metadata={"role": "finance_analyst"}
        ))

        self.assertIn("[M1]", result.answer)
        self.assertNotIn("[M2]", result.answer)
        self.assertNotIn("[M3]", result.answer)
        self.assertEqual([item.citation_id for item in result.evidence], ["M1"])
        self.assertEqual([row["metric_name"] for row in result.data["financial"]], ["net_revenue"])

    def test_document_analytics_cites_visible_documents_not_unrelated_metric_rows(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [{"domain": "finance", "document_count": 1,
                         "evidence_document_ids": ["AR24"]}],
            "evidence": [{"company": "Vinamilk", "fiscal_year": 2024, "metric_name": "net_revenue",
                          "metric_label": "Revenue", "metric_value": 61824, "unit": "billion VND",
                          "document_id": "AR24", "page_number": 12, "source_url": "https://example.test/ar24",
                          "source_quote": "Revenue 61,824 billion VND"}],
            "documents": [{"document_id": "AR24", "company": "Vinamilk", "domain": "finance",
                           "title": "Annual report 2024", "source_url": "https://example.test/ar24"}],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT domain, COUNT(document_id) AS document_count, '
            'ARRAY_AGG(DISTINCT document_id) AS evidence_document_ids '
            'FROM authorized_documents GROUP BY domain"}'
        )

        result = SQLAnalyticsAgent(repository, llm).run(AgentRequest(
            question="How many finance documents?", metadata={"role": "finance_analyst"}
        ))

        self.assertIn("[D1]", result.answer)
        self.assertEqual([item.source_type for item in result.evidence], ["document"])
        self.assertEqual(result.data["financial"], [])


if __name__ == "__main__":
    unittest.main()
