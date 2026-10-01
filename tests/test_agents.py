import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.intent_classifier import IntentClassifier
from core.analytics.metric_ontology import resolve_metric_names
from core.analytics.business_metric_catalog import resolve_business_metric_names
from core.agents.knowledge_agent import (
    KnowledgeAgent,
    _financial_retrieval_query,
    _rank_business_decision_evidence,
)
from core.agents.report_agent import ReportAgent, _financial_facts_match_cited_evidence, _format_prompt_evidence
from core.agents.router import AgentRouter
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.agents.report_agent import _normalize_numeric_citations, _is_business_metric_trend_question
from core.models.agents import AgentRequest, AgentResult, Evidence
from core.rag.rag_service import RAGResult


class AgentFlowTest(unittest.TestCase):
    def test_report_prompt_formats_verified_metrics_compactly(self):
        item = Evidence(
            citation_id="M1", source_type="verified_metric", source="Vinamilk 2025 · OEE target",
            content="x" * 10000,
            metadata={"metric_label": "OEE target", "fiscal_year": 2025,
                      "metric_value": 99, "unit": "%", "page_number": 86,
                      "value_qualifier": "more_than", "reporting_period": "H1",
                      "source_url": "https://example.test/long-url"},
        )
        formatted = _format_prompt_evidence(item)
        self.assertIn("H1 2025 = more than 99 %", formatted)
        self.assertIn("page 86", formatted)
        self.assertNotIn("source_url", formatted)
        self.assertLess(len(formatted), 200)

    def test_knowledge_agent_fails_closed_without_authenticated_role(self):
        rag = Mock()

        for metadata in ({}, {"role": ""}, {"role": None}):
            with self.subTest(metadata=metadata), self.assertRaisesRegex(ValueError, "authenticated role"):
                KnowledgeAgent(rag).run(AgentRequest(question="restricted policy", metadata=metadata))

        rag.generate_answer.assert_not_called()
        rag.retrieve_contexts.assert_not_called()

    def test_metric_ontology_resolves_bilingual_aliases_and_prefers_specific_phrase(self):
        self.assertEqual(resolve_metric_names("Revenue and profit after tax"), {"net_revenue", "profit_after_tax"})
        self.assertEqual(resolve_metric_names("Total revenue"), {"total_consolidated_revenue"})
        self.assertEqual(resolve_metric_names("Net revenue"), {"net_revenue"})
        self.assertEqual(resolve_metric_names("Tổng doanh thu hợp nhất năm 2024"), {"total_consolidated_revenue"})
        self.assertEqual(resolve_metric_names("Doanh thu 2024 là 52.576.991"), {"net_revenue"})

    def test_business_metric_resolver_unions_multi_domain_terms_with_exact_metric_matches(self):
        metrics = resolve_business_metric_names(
            "Across 2023–2025 water, emissions and waste, summarize the annual performance"
        )
        self.assertTrue({
            "total_raw_water_intake", "total_water_consumption", "scope_1_2_ghg_emissions",
            "dairy_product_ghg_intensity", "sugar_product_ghg_intensity",
            "total_waste_generated", "waste_recovered_recycled",
        }.issubset(metrics))
        environmental_question = (
            "Across the reported 2023–2025 water, emissions and waste indicators, which environmental priorities "
            "appear to be improving? Account for changes in reporting scope and identify what is not comparable."
        )
        self.assertTrue(_is_business_metric_trend_question(environmental_question))
        focused = resolve_business_metric_names(
            "Compare Scope 1 and 2 emissions per tonne of dairy products and sugar products from 2023 to 2025"
        )
        self.assertEqual(focused, {
            "scope_1_2_ghg_emissions", "dairy_product_ghg_intensity", "sugar_product_ghg_intensity",
        })
        intent = IntentClassifier.fallback(
            "Across the reported 2023–2025 water, emissions and waste indicators, summarize the trend"
        )
        self.assertEqual(intent.intent, "report")
        self.assertTrue(intent.needs_sql)
        self.assertTrue(intent.needs_knowledge)

        factory = resolve_business_metric_names(
            "Given OEE, estimated production cost savings and purchasing savings in FY2024, what should management review?"
        )
        self.assertTrue({
            "production_lines_meeting_oee_target", "production_cost_savings", "purchasing_cost_savings",
        }.issubset(factory))

    def test_business_metric_resolver_understands_vietnamese_market_position_questions(self):
        self.assertEqual(
            resolve_business_metric_names(
                "Vinamilk có khoảng cách thị phần với đối thủ đứng thứ hai bao nhiêu?"
            ),
            {"market_share_lead_over_runner_up"},
        )
        self.assertEqual(
            resolve_business_metric_names("Compare domestic consolidated net revenue growth with domestic consolidated net revenue"),
            {"domestic_consolidated_net_revenue", "domestic_consolidated_net_revenue_growth"},
        )

    def test_business_metric_trend_summary_uses_analytics_and_prohibits_unsupported_causes(self):
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[
            Evidence(citation_id="S1", source_type="document", source="SR25 p.139",
                     content="Total water consumption m³ 4,130,388 4,122,231 3,785,482. "
                             "Waste assurance scope expanded in 2025.")
        ])
        analytics = Mock()
        analytics.run.return_value = AgentResult(
            answer="", agent="analytics", evidence=[
                Evidence(citation_id="S2", source_type="metric", source="SR25 p.139",
                         content="FY2023 4,130,388 m³; FY2024 4,122,231 m³; FY2025 3,785,482 m³")
            ], data={"business_metrics": [{"metric_name": "total_water_consumption"}]},
        )
        llm = Mock()
        llm.generate.return_value = "Water use fell. The source does not state why. [S1] [S2]"
        question = "Summarize Vinamilk water consumption trend from 2023 to 2025"

        self.assertTrue(_is_business_metric_trend_question(question))
        ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question)
        )

        analytics.run.assert_called_once()
        prompt = llm.generate.call_args.args[0]
        self.assertIn("Do not infer operational causes", prompt)
        self.assertIn("label possible causes as unverified hypotheses", prompt)
        self.assertIn("reporting-boundary change", prompt)

    def test_generic_how_many_question_stays_document_qa(self):
        intent = IntentClassifier.fallback("Trong 100 ml sữa có bao nhiêu năng lượng và protein?")
        self.assertEqual(intent.intent, "knowledge")
        self.assertFalse(intent.needs_sql)

    def test_business_metric_decision_question_routes_to_hybrid_without_llm(self):
        intent = IntentClassifier.fallback("Should we scale Green Farm given sales growth and consumer loyalty?")
        self.assertEqual(intent.intent, "hybrid")
        self.assertTrue(intent.needs_sql)
        self.assertTrue(intent.needs_knowledge)

    def test_sql_analytics_agent_filters_using_canonical_vietnamese_metric(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [{"metric_name": "total_consolidated_revenue", "metric_label": "Doanh thu hợp nhất",
                         "fiscal_year": 2024, "metric_value": 61824, "unit": "tỷ đồng",
                         "evidence_metric_ids": [1]}],
            "evidence": [{"metric_name": "total_consolidated_revenue", "metric_label": "Doanh thu hợp nhất",
                          "fiscal_year": 2024, "metric_value": 61824, "unit": "tỷ đồng",
                          "company": "Vinamilk", "metric_id": 1, "document_id": "AR24", "page_number": 12,
                          "source_url": "https://example.test/ar24", "source_quote": "Doanh thu 61.824 tỷ đồng"}],
            "documents": [],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT metric_name, metric_label, fiscal_year, metric_value, unit, '
            'ARRAY_AGG(DISTINCT metric_id) AS evidence_metric_ids '
            'FROM authorized_financial_metrics WHERE fiscal_year = 2024 AND '
            "metric_name = 'total_consolidated_revenue' GROUP BY metric_name, metric_label, fiscal_year, metric_value, unit" + '"}'
        )
        agent = SQLAnalyticsAgent(repository, llm)
        result = agent.run(AgentRequest(question="Doanh thu hợp nhất năm 2024", metadata={"role": "finance_analyst"}))
        repository.execute_authorized_analytics.assert_called_once()
        self.assertEqual(repository.execute_authorized_analytics.call_args.args[1:], ("finance_analyst", "", None))
        self.assertEqual([row["metric_name"] for row in result.data["financial"]], ["total_consolidated_revenue"])

    def test_dashboard_sql_prompt_requests_individual_source_observations(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [], "evidence": [], "documents": [],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT metric_name, fiscal_year, ARRAY_AGG(DISTINCT metric_id) '
            'AS evidence_metric_ids FROM authorized_financial_metrics '
            'GROUP BY metric_name, fiscal_year LIMIT 10"}'
        )
        agent = SQLAnalyticsAgent(repository, llm)

        agent.run(AgentRequest(
            question="Revenue by year", metadata={"role": "finance_analyst", "dashboard_visualization": True},
        ))

        prompt = llm.generate.call_args.args[0]
        self.assertIn("return individual observations only", prompt.lower())
        self.assertIn("metric_value, unit, and document_id directly", prompt)
        self.assertIn("without summing or averaging values", prompt)

    def test_catalog_matched_business_query_uses_validated_sql_for_all_metrics_and_years(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [{"metric_name": "domestic_consolidated_net_revenue", "fiscal_year": 2022,
                         "metric_value": 50704.403447753, "unit": "VND billion",
                         "evidence_business_metric_ids": [1]}],
            "evidence": [],
            "business_evidence": [{"business_metric_id": 1, "company": "Vinamilk", "metric_domain": "market_performance",
                                   "metric_name": "domestic_consolidated_net_revenue", "metric_label": "Domestic net revenue",
                                   "fiscal_year": 2022, "metric_value": 50704.403447753, "unit": "VND billion",
                                   "scope": "Domestic segment", "document_id": "VNM-AR-2023-EN", "page_number": 170,
                                   "source_url": "https://example.test/ar23", "source_quote": "Net revenue 50,704",
                                   "source_chunk_id": 21605, "source_chunk_index": 385,
                                   "source_content_hash": "hash", "extraction_method": "parser_rule",
                                   "extractor_version": "vinamilk-page-anchors-v3"}],
            "documents": [],
        }
        llm = Mock()
        question = "Compare domestic and overseas segment net revenue and gross profit in 2022 and 2023. What decision could this inform?"

        result = SQLAnalyticsAgent(repository, llm).run(AgentRequest(question=question, metadata={"role": "admin"}))

        query = repository.execute_authorized_analytics.call_args.args[0]
        for metric in ("domestic_consolidated_net_revenue", "overseas_market_net_revenue",
                       "domestic_segment_gross_profit", "overseas_segment_gross_profit"):
            self.assertIn(metric, query)
        self.assertIn("fiscal_year IN (2022, 2023)", query)
        self.assertIn("authorized_business_metrics", query)
        llm.generate.assert_not_called()
        self.assertEqual(result.evidence[0].metadata["chunk_id"], 21605)
        self.assertEqual(result.evidence[0].metadata["chunk_index"], 385)

    def test_market_growth_query_also_fetches_revenue_scale_for_prior_year(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [], "evidence": [], "business_evidence": [], "documents": [],
        }
        llm = Mock()

        SQLAnalyticsAgent(repository, llm).run(AgentRequest(
            question="Should we prioritize overseas or domestic investment based on 2025 revenue growth?",
            metadata={"role": "admin"},
        ))

        query = repository.execute_authorized_analytics.call_args.args[0]
        for metric in ("domestic_consolidated_net_revenue_growth", "overseas_market_net_revenue_growth",
                       "domestic_consolidated_net_revenue", "overseas_market_net_revenue"):
            self.assertIn(f"'{metric}'", query)
        self.assertIn("fiscal_year IN (2024, 2025)", query)

    def test_export_market_question_requests_country_growth_metrics_from_sql(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [], "evidence": [], "business_evidence": [], "documents": [],
        }
        llm = Mock()

        SQLAnalyticsAgent(repository, llm).run(AgentRequest(
            question="Which export markets should Vinamilk prioritize for investment based on growth?",
            metadata={"role": "admin"},
        ))

        query = repository.execute_authorized_analytics.call_args.args[0]
        for metric in ("guinea_export_revenue_growth", "hong_kong_export_revenue_growth",
                       "japan_export_revenue_growth"):
            self.assertIn(metric, query)
        self.assertIn("FROM authorized_business_metrics", query)

    def test_business_summary_query_includes_contiguous_year_span_and_all_domain_metrics(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [], "evidence": [], "business_evidence": [], "documents": [],
        }
        llm = Mock()
        question = "Across the reported 2023–2025 water, emissions and waste indicators, summarize the trend"

        SQLAnalyticsAgent(repository, llm).run(AgentRequest(question=question, metadata={"role": "admin"}))

        query = repository.execute_authorized_analytics.call_args.args[0]
        self.assertIn("fiscal_year IN (2023, 2024, 2025)", query)
        for metric in ("total_raw_water_intake", "total_water_consumption", "scope_1_2_ghg_emissions",
                       "total_waste_generated", "waste_recovered_recycled"):
            self.assertIn(metric, query)
        llm.generate.assert_not_called()

    def test_focused_business_question_does_not_expand_to_every_environmental_metric(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [], "evidence": [], "business_evidence": [], "documents": [],
        }
        llm = Mock()
        question = (
            "Compare Scope 1 and 2 emissions per tonne of dairy products and sugar products "
            "from 2023 to 2025. What operational review should these trends inform?"
        )

        SQLAnalyticsAgent(repository, llm).run(AgentRequest(question=question, metadata={"role": "admin"}))

        query = repository.execute_authorized_analytics.call_args.args[0]
        self.assertIn("reporting_period", query)
        self.assertIn("value_qualifier", query)
        for metric in ("scope_1_2_ghg_emissions", "dairy_product_ghg_intensity", "sugar_product_ghg_intensity"):
            self.assertIn(metric, query)
        for unrelated in ("total_raw_water_intake", "total_waste_generated", "electricity_saved"):
            self.assertNotIn(unrelated, query)
        self.assertIn("fiscal_year IN (2023, 2024, 2025)", query)

    def test_classifier_fallback_routes_summary_request_to_report_agent(self):
        intent = IntentClassifier.fallback("Summarize Vinamilk revenue and profit for 2024")
        self.assertEqual(intent.intent, "report")
        self.assertTrue(intent.needs_sql)
        self.assertTrue(intent.needs_knowledge)

    def test_classifier_accepts_explicit_report_intent(self):
        llm = Mock()
        llm.generate.return_value = (
            '{"intent":"report","needs_knowledge":true,"needs_sql":true,'
            '"output_mode":"answer","confidence":0.9}'
        )
        intent = IntentClassifier(llm).classify("Summarize these company documents")
        self.assertEqual(intent.intent, "report")

    def test_report_intent_falls_back_to_hybrid_when_report_agent_is_not_configured(self):
        classifier = Mock()
        classifier.classify.return_value = IntentClassifier.fallback("Summarize these company documents")
        hybrid = Mock()
        hybrid.run.return_value = AgentResult(answer="grounded summary", agent="hybrid")
        unused = Mock()
        router = AgentRouter(classifier, unused, unused, hybrid, unused)

        result = router.route(AgentRequest(question="Summarize these company documents"))

        self.assertEqual(result.agent, "hybrid")
        hybrid.run.assert_called_once()

    def test_explicit_dashboard_output_is_not_rewritten_to_report(self):
        llm = Mock()
        llm.generate.return_value = (
            '{"intent":"dashboard","needs_knowledge":false,"needs_sql":true,'
            '"output_mode":"dashboard","confidence":0.9}'
        )
        intent = IntentClassifier(llm).classify("Summarize these metrics in a dashboard")
        self.assertEqual(intent.intent, "dashboard")
        self.assertEqual(intent.output_mode, "dashboard")

    def test_document_metadata_counts_are_analytics_even_if_llm_says_knowledge(self):
        llm = Mock()
        llm.generate.return_value = (
            '{"intent":"knowledge","needs_knowledge":true,"needs_sql":false,'
            '"output_mode":"answer","confidence":0.9}'
        )

        intent = IntentClassifier(llm).classify("Compare document counts by business domain")

        self.assertEqual(intent.intent, "analytics")
        self.assertFalse(intent.needs_knowledge)
        self.assertTrue(intent.needs_sql)

        report_count_intent = IntentClassifier(llm).classify(
            "How many annual reports were published each year?"
        )
        self.assertEqual(report_count_intent.intent, "analytics")
        self.assertTrue(report_count_intent.needs_sql)

    def test_report_counts_are_analytics_not_document_summaries(self):
        intent = IntentClassifier.fallback("How many annual reports were published each year?")
        self.assertEqual(intent.intent, "analytics")
        self.assertFalse(intent.needs_knowledge)
        self.assertTrue(intent.needs_sql)

        report = Mock()
        unused = Mock()
        unused.run.return_value = AgentResult(answer="count", agent="analytics")
        classifier = Mock()
        classifier.classify.return_value = intent
        router = AgentRouter(classifier, unused, unused, unused, unused, report)
        result = router.route(AgentRequest(question="How many annual reports were published each year?"))

        self.assertEqual(result.agent, "analytics")
        unused.run.assert_called_once()
        report.run.assert_not_called()

    def test_financial_fact_questions_use_both_verified_analytics_and_documents(self):
        intent = IntentClassifier.fallback("What was Vinamilk's revenue in 2024?")
        self.assertEqual(intent.intent, "hybrid")
        self.assertTrue(intent.needs_sql)
        self.assertTrue(intent.needs_knowledge)

    def test_single_period_revenue_and_profit_summary_uses_guarded_report_agent(self):
        summary = IntentClassifier.fallback(
            "What were Vinamilk's revenue and profit after tax in 2024?"
        )
        self.assertEqual(summary.intent, "report")
        comparison = IntentClassifier.fallback(
            "Compare Vinamilk's revenue and profit after tax across years"
        )
        self.assertEqual(comparison.intent, "hybrid")
        year_comparison = IntentClassifier.fallback(
            "What were Vinamilk's revenue and profit after tax in 2024 vs 2023?"
        )
        self.assertEqual(year_comparison.intent, "hybrid")
        multiple_periods = IntentClassifier.fallback(
            "What were Vinamilk's revenue and profit after tax in 2024 and 2023?"
        )
        self.assertEqual(multiple_periods.intent, "hybrid")

    def test_why_financial_change_question_uses_grounded_report_route(self):
        intent = IntentClassifier.fallback(
            "tại sao total assets của 2021 lại tăng so với 2020"
        )
        self.assertEqual(intent.intent, "report")
        self.assertTrue(intent.needs_knowledge)
        self.assertTrue(intent.needs_sql)

    def test_why_financial_change_bypasses_intent_llm_call(self):
        llm = Mock()
        result = IntentClassifier(llm).classify(
            "tại sao total assets của 2021 lại tăng so với 2020"
        )
        self.assertEqual(result.intent, "report")
        llm.generate.assert_not_called()

    def test_knowledge_agent_passes_trusted_role_and_maps_source_id(self):
        rag = Mock()
        rag.generate_answer.return_value = RAGResult(
            answer="Reported result [S1]", source_ids=["S1"],
            contexts=[{"source_id": "S1", "document_name": "Annual report", "chunk_index": 2,
                       "content": "Net revenue 100", "metadata": {"page_number": 4},
                       "retrieval_score": 0.9, "retrieval_method": "hybrid"}],
        )
        agent = KnowledgeAgent(rag)
        result = agent.run(AgentRequest(question="revenue", user_id="analyst", metadata={"role": "finance_analyst"}))
        rag.generate_answer.assert_called_once_with("revenue", limit=10, company=None, roles=["finance_analyst"])
        self.assertEqual(result.evidence[0].citation_id, "S1")

    def test_knowledge_agent_uses_bilingual_financial_query_for_retrieval_only(self):
        rag = Mock()
        rag.generate_answer.return_value = RAGResult(answer="Reported result [S1]", source_ids=["S1"])
        question = "What were Vinamilk's 2024 revenue and profit after tax?"
        KnowledgeAgent(rag).run(AgentRequest(
            question=question,
            metadata={"role": "finance_analyst", "company": "Vinamilk"},
        ))
        call = rag.generate_answer.call_args
        self.assertEqual(call.args[0], question)
        self.assertIn("Tổng doanh thu hợp nhất", call.kwargs["retrieval_query"])
        self.assertIn("lợi nhuận sau thuế hợp nhất", call.kwargs["retrieval_query"])

    def test_knowledge_agent_preserves_uncited_retrieved_context_for_report_stage(self):
        rag = Mock()
        rag.generate_answer.return_value = RAGResult(
            answer="Revenue was 52.6 trillion VND [S1]", source_ids=["S1"],
            contexts=[
                {"source_id": "S1", "document_name": "Annual report", "chunk_index": 2,
                 "content": "Audited statement revenue 52.6T", "metadata": {"page_number": 92},
                 "retrieval_score": 0.9, "retrieval_method": "hybrid"},
                {"source_id": "S7", "document_name": "Annual report", "chunk_index": 27,
                 "content": "Headline total consolidated revenue 61.824T", "metadata": {"page_number": 12},
                 "retrieval_score": 0.8, "retrieval_method": "hybrid"},
            ],
        )
        result = KnowledgeAgent(rag).run(AgentRequest(
            question="Summarize revenue", metadata={"role": "finance_analyst"}
        ))
        self.assertEqual([item.citation_id for item in result.evidence], ["S1", "S7"])

    def test_report_knowledge_path_retrieves_evidence_without_first_generation(self):
        rag = Mock()
        rag.retrieve_contexts.return_value = [{
            "source_id": "S1", "document_name": "Annual report", "chunk_index": 2,
            "content": "Annual report metric", "metadata": {"page_number": 4},
            "retrieval_score": 0.9, "retrieval_method": "hybrid",
        }]
        result = KnowledgeAgent(rag).run(AgentRequest(
            question="Summarize annual report",
            metadata={"role": "finance_analyst", "evidence_only": True},
        ))
        rag.retrieve_contexts.assert_called_once()
        self.assertEqual(rag.retrieve_contexts.call_args.kwargs["limit"], 5)
        rag.generate_answer.assert_not_called()
        self.assertEqual(result.evidence[0].citation_id, "S1")

    def test_decision_support_report_limits_retrieved_passages_for_provider_tpm(self):
        rag = Mock()
        rag.retrieve_contexts.return_value = []

        KnowledgeAgent(rag).run(AgentRequest(
            question="Should Vinamilk allocate more capital to overseas markets?",
            metadata={"role": "admin", "evidence_only": True, "decision_support": True},
        ))

        self.assertEqual(rag.retrieve_contexts.call_args.kwargs["limit"], 3)

    def test_decision_domain_reranking_filters_other_domains_and_prefers_numeric_tables(self):
        contexts = [
            {"source_id": "S1", "content": "Employee headcount: 8,000.",
             "metadata": {"layout_type": "table"}},
            {"source_id": "S2", "content": "Approximate market share lead over the second player: 30 percentage points.",
             "metadata": {"layout_type": "text"}},
            {"source_id": "S3", "content": "Domestic consolidated net revenue 2024: VND 25,000 billion.",
             "metadata": {"layout_type": "table"}},
            {"source_id": "S4", "content": "Market share and domestic revenue are discussed without values.",
             "metadata": {"layout_type": "text"}},
        ]

        ranked = _rank_business_decision_evidence(
            contexts,
            "Compare market share lead and domestic revenue in 2024",
            "market_performance",
            3,
        )

        self.assertEqual(len(ranked), 3)
        self.assertNotIn("Employee headcount", " ".join(item["content"] for item in ranked))
        self.assertEqual(ranked[0]["content"], contexts[2]["content"])
        self.assertEqual(ranked[1]["content"], contexts[1]["content"])
        self.assertEqual([item["source_id"] for item in ranked], ["S1", "S2", "S3"])

    def test_decision_domain_fetches_authorized_candidate_pool_then_limits_prompt_context(self):
        rag = Mock()
        rag.retrieve_contexts.return_value = [
            {"source_id": "S1", "document_name": "HR report", "chunk_index": 1,
             "content": "Employee headcount: 8,000.", "metadata": {"layout_type": "table"},
             "retrieval_score": 0.99, "retrieval_method": "hybrid"},
            {"source_id": "S2", "document_name": "Annual report", "chunk_index": 2,
             "content": "Domestic consolidated net revenue 2024: VND 25,000 billion.",
             "metadata": {"layout_type": "table"}, "retrieval_score": 0.7, "retrieval_method": "hybrid"},
        ]

        result = KnowledgeAgent(rag).run(AgentRequest(
            question="Compare domestic consolidated net revenue in 2024",
            user_id="analyst",
            metadata={"role": "finance_analyst", "company": "Vinamilk",
                      "evidence_only": True, "decision_support": True,
                      "business_decision_domain": "market_performance"},
        ))

        self.assertEqual(rag.retrieve_contexts.call_args.kwargs["limit"], 15)
        self.assertEqual(rag.retrieve_contexts.call_args.kwargs["roles"], ["finance_analyst"])
        self.assertEqual(len(result.evidence), 1)
        self.assertIn("Domestic consolidated net revenue", result.evidence[0].content)

    def test_knowledge_agent_routes_explicit_parent_retrieval(self):
        rag = Mock()
        rag.generate_answer.return_value = RAGResult(answer="answer", source_ids=[])
        KnowledgeAgent(rag).run(AgentRequest(
            question="revenue", metadata={"role": "finance_analyst", "retrieval_method": "parent"}
        ))
        rag.generate_answer.assert_called_once_with(
            "revenue", limit=10, company=None, roles=["finance_analyst"], retrieval_method="parent"
        )

    def test_router_uses_report_for_summary_requests(self):
        for question in ("Summarize revenue", "Tóm tắt doanh thu năm 2024"):
            with self.subTest(question=question):
                report = Mock()
                report.run.return_value = AgentResult(answer="report result", agent="report")
                unused = Mock()
                classifier = Mock()
                classifier.classify.return_value = IntentClassifier.fallback(question)
                router = AgentRouter(classifier, unused, unused, unused, unused, report)
                result = router.route(AgentRequest(question=question))
                self.assertEqual(result.agent, "report")
                report.run.assert_called_once()
                unused.run.assert_not_called()

    def test_business_decision_hybrid_uses_report_agent_to_synthesize_evidence(self):
        question = "Compare domestic and overseas segment net revenue and gross profit. What decision could this inform?"
        report = Mock()
        report.run.return_value = AgentResult(answer="decision synthesis", agent="report")
        unused = Mock()
        classifier = Mock()
        classifier.classify.return_value = IntentClassifier.fallback(question)
        router = AgentRouter(classifier, unused, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question))

        self.assertEqual(result.agent, "report")
        report.run.assert_called_once()
        unused.run.assert_not_called()

    def test_decision_report_abstains_when_requested_segment_metrics_are_incomplete(self):
        question = "Compare domestic and overseas segment net revenue and gross profit. What decision could this inform?"
        knowledge = Mock()
        analytics = Mock()
        analytics.run.return_value = AgentResult(answer="metrics", agent="analytics", evidence=[
            Evidence(citation_id="M1", source_type="verified_metric", source="FY2023 segment gross profit",
                     content="Audited segment gross profit was reported.")
        ], data={"business_metrics": [{"metric_name": "domestic_segment_gross_profit"}]})
        llm = Mock()

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question)
        )

        analytics.run.assert_called_once()
        self.assertTrue(result.metadata["insufficient_context"])
        self.assertEqual(result.metadata["decision_analysis"], "missing_role_visible_verified_metrics")
        self.assertIn("Domestic consolidated net revenue", result.answer)
        self.assertIn("Overseas segment gross profit", result.answer)
        knowledge.run.assert_not_called()
        llm.generate.assert_not_called()

    def test_complete_segment_economics_answer_uses_verified_sql_without_llm(self):
        question = (
            "Compare domestic and overseas segment net revenue and gross profit in 2022 and 2023. "
            "Which market improved more, what decision could this inform?"
        )
        observations = {
            ("domestic_consolidated_net_revenue", 2022): (50704.403447753, 208),
            ("domestic_consolidated_net_revenue", 2023): (50617.453566955, 207),
            ("domestic_segment_gross_profit", 2022): (20555.544882296, 212),
            ("domestic_segment_gross_profit", 2023): (20893.809625798, 211),
            ("overseas_market_net_revenue", 2022): (9251.843749665, 210),
            ("overseas_market_net_revenue", 2023): (9751.46194455, 209),
            ("overseas_segment_gross_profit", 2022): (3341.686624411, 214),
            ("overseas_segment_gross_profit", 2023): (3650.921989612, 213),
        }
        rows = []
        evidence = []
        for index, ((name, year), (value, metric_id)) in enumerate(observations.items(), 1):
            rows.append({"metric_name": name, "fiscal_year": year, "metric_value": value,
                         "unit": "VND billion", "business_metric_id": metric_id})
            evidence.append(Evidence(
                citation_id=f"M{index}", source_type="verified_metric", source=f"Annual Report p. 170 · {name}",
                content=f"{year}: {value} VND billion", metadata={"business_metric_id": metric_id,
                    "chunk_id": 21605, "chunk_index": 385, "page_number": 170},
            ))
        analytics = Mock()
        analytics.run.return_value = AgentResult(answer="", agent="analytics", evidence=evidence,
                                                  data={"business_metrics": rows})
        knowledge, llm = Mock(), Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge")

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question, metadata={"role": "admin"})
        )

        self.assertIn("40.54%", result.answer)
        self.assertIn("41.28%", result.answer)
        self.assertIn("36.12%", result.answer)
        self.assertIn("37.44%", result.answer)
        self.assertIn("+1.32 pp", result.answer)
        self.assertIn("further diligence", result.answer)
        self.assertIn("[M1]", result.answer)
        self.assertEqual(result.metadata["decision_analysis"], "verified_segment_economics")
        knowledge.run.assert_not_called()
        llm.generate.assert_not_called()

    def test_market_growth_decision_uses_verified_sql_instead_of_irrelevant_rag(self):
        question = "Should we prioritize overseas or domestic market investment based on 2024 revenue growth?"
        rows = [
            {"metric_name": "domestic_consolidated_net_revenue_growth", "fiscal_year": 2024,
             "metric_value": 0.4, "unit": "%", "business_metric_id": 101},
            {"metric_name": "overseas_market_net_revenue_growth", "fiscal_year": 2024,
             "metric_value": 12.6, "unit": "%", "business_metric_id": 102},
        ]
        evidence = [
            Evidence(citation_id="M1", source_type="verified_metric", source="Domestic revenue growth",
                     content="0.4%", metadata={"business_metric_id": 101}),
            Evidence(citation_id="M2", source_type="verified_metric", source="Overseas revenue growth",
                     content="12.6%", metadata={"business_metric_id": 102}),
        ]
        knowledge, analytics, llm = Mock(), Mock(), Mock()
        analytics.run.return_value = AgentResult(answer="", agent="analytics", evidence=evidence,
                                                 data={"business_metrics": rows})

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question, metadata={"role": "admin"})
        )

        self.assertIn("0.4%", result.answer)
        self.assertIn("12.6%", result.answer)
        self.assertIn("diligence review", result.answer)
        self.assertEqual(result.metadata["decision_analysis"], "verified_market_growth")
        knowledge.run.assert_not_called()
        llm.generate.assert_not_called()

    def test_export_country_decision_ranks_source_metrics_and_limits_recommendation(self):
        question = "Which export markets should Vinamilk prioritize for investment based on growth?"
        values = [
            ("guinea_export_revenue_growth", 108),
            ("hong_kong_export_revenue_growth", 94),
            ("japan_export_revenue_growth", 28),
        ]
        rows, evidence = [], []
        for index, (name, value) in enumerate(values, 1):
            rows.append({"metric_name": name, "metric_label": name, "fiscal_year": 2025,
                         "metric_value": value, "unit": "%", "business_metric_id": index})
            evidence.append(Evidence(citation_id=f"M{index}", source_type="verified_metric",
                                     source=f"Annual Report p. 47 · {name}", content=f"{value}%",
                                     metadata={"business_metric_id": index}))
        context_values = [
            ("export_net_revenue", 7105, "VND billion"),
            ("export_net_revenue_growth", 25.4, "%"),
            ("commercial_export_revenue", 6546, "VND billion"),
            ("commercial_export_revenue_growth", 16.5, "%"),
            ("export_volume_teu", 4200, "TEUs"),
        ]
        for index, (name, value, unit) in enumerate(context_values, 4):
            rows.append({"metric_name": name, "metric_label": name, "fiscal_year": 2025,
                         "metric_value": value, "unit": unit, "business_metric_id": index})
            evidence.append(Evidence(citation_id=f"M{index}", source_type="verified_metric",
                                     source=f"Annual Report p. 29 · {name}", content=str(value),
                                     metadata={"business_metric_id": index}))
        knowledge, analytics, llm = Mock(), Mock(), Mock()
        analytics.run.return_value = AgentResult(answer="", agent="analytics", evidence=evidence,
                                                 data={"business_metrics": rows})

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question, metadata={"role": "admin"})
        )

        self.assertLess(result.answer.index("108%"), result.answer.index("94%"))
        self.assertLess(result.answer.index("94%"), result.answer.index("28%"))
        self.assertIn("does not disclose", result.answer)
        self.assertIn("Do not approve a capital shift", result.answer)
        self.assertIn("VND 7,105 billion [M4]", result.answer)
        self.assertIn("VND 6,546 billion [M6]", result.answer)
        self.assertIn("included in total export net revenue", result.answer)
        self.assertEqual(result.metadata["decision_analysis"], "verified_export_country_priorities")
        knowledge.run.assert_not_called()
        llm.generate.assert_not_called()

        analytics.run.return_value.data["business_metrics"] = rows[:3]
        country_only = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question, metadata={"role": "admin"})
        )
        self.assertIn("108%", country_only.answer)

    def test_market_growth_decision_uses_revenue_scale_and_absolute_change(self):
        question = "Should we prioritize overseas or domestic investment based on 2025 revenue growth?"
        values = [
            (2024, "domestic_consolidated_net_revenue", 50799, "VND billion"),
            (2025, "domestic_consolidated_net_revenue", 50964, "VND billion"),
            (2024, "overseas_market_net_revenue", 10983, "VND billion"),
            (2025, "overseas_market_net_revenue", 12682, "VND billion"),
            (2025, "domestic_consolidated_net_revenue_growth", 0.3, "%"),
            (2025, "overseas_market_net_revenue_growth", 15.5, "%"),
        ]
        rows, evidence = [], []
        for index, (year, name, value, unit) in enumerate(values, 1):
            rows.append({"metric_name": name, "fiscal_year": year, "metric_value": value,
                         "unit": unit, "business_metric_id": index})
            evidence.append(Evidence(citation_id=f"M{index}", source_type="verified_metric",
                                     source=f"FY{year} {name}", content=str(value),
                                     metadata={"business_metric_id": index}))
        knowledge, analytics, llm = Mock(), Mock(), Mock()
        analytics.run.return_value = AgentResult(answer="", agent="analytics", evidence=evidence,
                                                 data={"business_metrics": rows})

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question, metadata={"role": "admin"})
        )

        self.assertIn("VND 50,964 billion", result.answer)
        self.assertIn("VND 12,682 billion", result.answer)
        self.assertIn("VND 165 billion", result.answer)
        self.assertIn("VND 1,699 billion", result.answer)
        self.assertEqual(result.metadata["decision_analysis"], "verified_market_growth")
        knowledge.run.assert_not_called()
        llm.generate.assert_not_called()

    def test_factory_efficiency_decision_uses_verified_metrics_without_rag_or_llm(self):
        question = (
            "Given OEE, estimated production cost savings and purchasing savings in FY2024, "
            "what should management review next?"
        )
        values = [
            ("production_lines_meeting_oee_target", 96, "%", "more_than"),
            ("production_cost_savings", 100.8, "VND billion", "approximately"),
            ("purchasing_cost_savings", 550, "VND billion", "approximately"),
        ]
        rows, evidence = [], []
        for index, (name, value, unit, qualifier) in enumerate(values, 1):
            rows.append({"metric_name": name, "metric_label": name.replace("_", " "),
                         "fiscal_year": 2024, "metric_value": value, "unit": unit,
                         "value_qualifier": qualifier, "business_metric_id": index})
            evidence.append(Evidence(
                citation_id=f"M{index}", source_type="verified_metric", source=f"Annual Report · {name}",
                content=f"FY2024 {value} {unit}", metadata={"business_metric_id": index},
            ))
        knowledge, llm, analytics = Mock(), Mock(), Mock()
        analytics.run.return_value = AgentResult(
            answer="metrics", agent="analytics", evidence=evidence, data={"business_metrics": rows},
        )

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question, metadata={"role": "admin"})
        )

        self.assertIn("more than 96%", result.answer)
        self.assertIn("approximately VND 100.8 billion", result.answer)
        self.assertIn("approximately VND 550 billion", result.answer)
        self.assertIn("do not identify which factory", result.answer)
        self.assertEqual(result.metadata["decision_analysis"], "verified_factory_efficiency")
        knowledge.run.assert_not_called()
        llm.generate.assert_not_called()

    def test_milk_sourcing_decision_compares_household_purchase_not_total_supply(self):
        question = (
            "Compare raw fresh milk purchased from farming households in 2023, 2024 and 2025. "
            "What should leadership investigate before changing procurement?"
        )
        values = [(2023, 239254, "exact"), (2024, 227000, "approximately"),
                  (2025, 225778.211, "exact")]
        rows, evidence = [], []
        for index, (year, value, qualifier) in enumerate(values, 1):
            rows.append({"metric_name": "farmer_raw_milk_purchased", "metric_label": "Milk purchased from farmers",
                         "fiscal_year": year, "metric_value": value, "unit": "tonnes",
                         "value_qualifier": qualifier, "business_metric_id": index})
            evidence.append(Evidence(citation_id=f"M{index}", source_type="verified_metric",
                                     source=f"FY{year} farmer milk purchases", content=str(value),
                                     metadata={"business_metric_id": index}))
        rows.append({"metric_name": "partner_farm_households", "fiscal_year": 2023,
                     "metric_value": 4180, "unit": "households", "business_metric_id": 4})
        evidence.append(Evidence(citation_id="M4", source_type="verified_metric",
                                 source="FY2023 partner households", content="4,180",
                                 metadata={"business_metric_id": 4}))
        knowledge, analytics, llm = Mock(), Mock(), Mock()
        analytics.run.return_value = AgentResult(answer="metrics", agent="analytics", evidence=evidence,
                                                 data={"business_metrics": rows})

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question, metadata={"role": "admin"})
        )

        self.assertIn("225,778.211 tonnes", result.answer)
        self.assertIn("fell by 13,475.789 tonnes (5.63%)", result.answer)
        self.assertIn("not proof of supplier attrition", result.answer)
        self.assertIn("[M1]", result.answer)
        self.assertIn("[M3]", result.answer)
        self.assertEqual(result.metadata["decision_analysis"], "verified_milk_sourcing")
        knowledge.run.assert_not_called()
        llm.generate.assert_not_called()

    def test_product_portfolio_decision_uses_cited_funnel_and_profitability_limits(self):
        question = (
            "Which product portfolio initiatives should management investigate before scaling? Compare plant-based "
            "milk sales growth, Green Farm sales growth, brand awareness, purchase consideration, loyalty and "
            "new or relaunched products; identify profitability evidence needed."
        )
        values = [
            ("plant_based_milk_sales_growth", 2024, 50, "approximately"),
            ("green_farm_sales_growth", 2024, 20, "more_than"),
            ("green_farm_brand_awareness", 2024, 59, "exact"),
            ("green_farm_customer_loyalty", 2024, 96, "exact"),
            ("green_farm_urban_purchase_consideration", 2022, 9, "exact"),
            ("green_farm_urban_purchase_consideration", 2024, 16, "exact"),
            ("new_or_relaunched_products", 2024, 125, "exact"),
        ]
        rows, evidence = [], []
        for index, (name, year, value, qualifier) in enumerate(values, 1):
            rows.append({"metric_name": name, "metric_label": name.replace("_", " "), "fiscal_year": year,
                         "metric_value": value, "unit": "products" if name == "new_or_relaunched_products" else "%",
                         "value_qualifier": qualifier, "business_metric_id": index})
            evidence.append(Evidence(citation_id=f"M{index}", source_type="verified_metric",
                                     source=f"FY{year} {name}", content=str(value),
                                     metadata={"business_metric_id": index}))
        knowledge, analytics, llm = Mock(), Mock(), Mock()
        analytics.run.return_value = AgentResult(answer="metrics", agent="analytics", evidence=evidence,
                                                 data={"business_metrics": rows})

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question, metadata={"role": "admin"})
        )

        self.assertIn("approximately 50%", result.answer)
        self.assertIn("more than 20%", result.answer)
        self.assertIn("+7 percentage points", result.answer)
        self.assertIn("not sufficient to rank them for expansion", result.answer)
        self.assertIn("contribution margin by SKU/channel", result.answer)
        self.assertTrue(all(f"[M{i}]" in result.answer for i in range(1, 8)))
        self.assertEqual(result.metadata["decision_analysis"], "verified_product_portfolio")
        knowledge.run.assert_not_called()
        llm.generate.assert_not_called()

    def test_report_does_not_substitute_document_passages_when_role_cannot_see_metrics(self):
        question = (
            "Compare raw fresh milk purchased from farming households in 2023, 2024 and 2025. "
            "What should leadership investigate before changing procurement?"
        )
        knowledge, analytics, llm = Mock(), Mock(), Mock()
        analytics.run.return_value = AgentResult(answer="No verified rows", agent="analytics", evidence=[],
                                                 data={"business_metrics": []})

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question, metadata={"role": "finance_analyst"})
        )

        self.assertTrue(result.metadata["insufficient_context"])
        self.assertEqual(result.metadata["decision_analysis"], "missing_role_visible_verified_metrics")
        self.assertIn("I will not substitute a similar figure", result.answer)
        knowledge.run.assert_not_called()
        llm.generate.assert_not_called()

    def test_environmental_trend_decision_uses_verified_metrics_and_respects_boundary_change(self):
        question = (
            "Across the reported 2023–2025 water, emissions and waste indicators, which environmental priorities "
            "appear to be improving? Account for changes in reporting scope and identify what is not comparable."
        )
        series = {
            "total_water_consumption": ("m³", [4130388, 4122231, 3785482]),
            "scope_1_2_ghg_emissions": ("kg CO₂e", [277730014, 252175374, 253353363]),
            "dairy_product_ghg_intensity": ("kg CO₂e/tonne product", [226, 213, 217]),
            "sugar_product_ghg_intensity": ("kg CO₂e/tonne product", [85, 36, 61]),
            "total_waste_generated": ("kg", [17383908, 17884507, 86903275]),
        }
        extras = {
            "total_raw_water_intake": ("m³", 7961404), "recycled_reused_water": ("m³", 221556),
            "wastewater_discharge": ("m³", 4175921), "scope_1_ghg_emissions": ("kg CO₂e", 122558524),
            "scope_2_ghg_emissions": ("kg CO₂e", 130794838),
            "waste_recovered_recycled": ("kg", 66664726), "waste_treated_disposed": ("kg", 20238549),
        }
        rows, evidence, metric_id = [], [], 0
        for name, (unit, values) in series.items():
            for year, value in zip((2023, 2024, 2025), values):
                metric_id += 1
                scope = ("The report notes a changed assurance boundary in 2025 and revised historical comparisons."
                         if name == "total_waste_generated" and year == 2025 else "Company-wide annual total.")
                rows.append({"metric_name": name, "metric_label": name.replace("_", " "),
                             "fiscal_year": year, "metric_value": value, "unit": unit,
                             "scope": scope, "business_metric_id": metric_id})
                evidence.append(Evidence(citation_id=f"M{metric_id}", source_type="verified_metric",
                                         source=f"FY{year} {name}", content=f"{value} {unit}",
                                         metadata={"business_metric_id": metric_id}))
        for name, (unit, value) in extras.items():
            metric_id += 1
            rows.append({"metric_name": name, "metric_label": name.replace("_", " "), "fiscal_year": 2025,
                         "metric_value": value, "unit": unit, "business_metric_id": metric_id})
            evidence.append(Evidence(citation_id=f"M{metric_id}", source_type="verified_metric",
                                     source=f"FY2025 {name}", content=f"{value} {unit}",
                                     metadata={"business_metric_id": metric_id}))
        knowledge, analytics, llm = Mock(), Mock(), Mock()
        analytics.run.return_value = AgentResult(answer="metrics", agent="analytics", evidence=evidence,
                                                 data={"business_metrics": rows})

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question, metadata={"role": "sustainability_analyst"})
        )

        self.assertIn("fell by 344,906 m³ (8.35%)", result.answer)
        self.assertIn("rose by 1,177,989 kg CO₂e (0.47%)", result.answer)
        self.assertIn("rose by 25 kg CO₂e/tonne product (69.44%)", result.answer)
        self.assertIn("changed assurance boundary in 2025", result.answer)
        self.assertEqual(result.metadata["decision_analysis"], "verified_environmental_trends")
        knowledge.run.assert_not_called()
        llm.generate.assert_not_called()

    def test_market_growth_decision_compares_each_requested_year(self):
        question = "Compare domestic and overseas revenue growth in 2024 and 2025. What should management investigate?"
        rows = []
        evidence = []
        values = [
            (2024, "domestic_consolidated_net_revenue_growth", 0.4, "%"),
            (2024, "overseas_market_net_revenue_growth", 12.6, "%"),
            (2025, "domestic_consolidated_net_revenue_growth", 0.3, "%"),
            (2025, "overseas_market_net_revenue_growth", 15.5, "%"),
            (2024, "domestic_consolidated_net_revenue", 50799, "VND billion"),
            (2024, "overseas_market_net_revenue", 10983, "VND billion"),
            (2025, "domestic_consolidated_net_revenue", 50964, "VND billion"),
            (2025, "overseas_market_net_revenue", 12682, "VND billion"),
        ]
        for index, (year, name, value, unit) in enumerate(values, 1):
            rows.append({"metric_name": name, "fiscal_year": year, "metric_value": value,
                         "unit": unit, "business_metric_id": index})
            evidence.append(Evidence(citation_id=f"M{index}", source_type="verified_metric",
                                     source=f"FY{year} {name}", content=f"{value} {unit}",
                                     metadata={"business_metric_id": index}))
        knowledge, analytics, llm = Mock(), Mock(), Mock()
        analytics.run.return_value = AgentResult(answer="", agent="analytics", evidence=evidence,
                                                 data={"business_metrics": rows})

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question=question, metadata={"role": "admin"})
        )

        self.assertIn("FY2024", result.answer)
        self.assertIn("FY2025", result.answer)
        self.assertIn("[M3]", result.answer)
        self.assertIn("[M4]", result.answer)
        self.assertIn("VND 50,964 billion", result.answer)
        self.assertIn("VND 12,682 billion", result.answer)
        self.assertIn("VND 165 billion domestically and VND 1,699 billion overseas", result.answer)
        for citation in ("[M5]", "[M6]", "[M7]", "[M8]"):
            self.assertIn(citation, result.answer)
        self.assertEqual(result.metadata["decision_analysis"], "verified_market_growth")
        knowledge.run.assert_not_called()
        llm.generate.assert_not_called()

    def test_mentioning_an_annual_report_does_not_force_report_generation(self):
        question = "What does the annual report say about governance?"
        classifier = Mock()
        classifier.classify.return_value = IntentClassifier.fallback(question)
        knowledge, unused, report = Mock(), Mock(), Mock()
        knowledge.run.return_value = AgentResult(answer="source answer", agent="knowledge")
        router = AgentRouter(classifier, knowledge, unused, unused, unused, report)

        result = router.route(AgentRequest(question=question))

        self.assertEqual(result.agent, "knowledge")
        knowledge.run.assert_called_once()
        report.run.assert_not_called()

    def test_router_keeps_selected_destination_when_agent_raises(self):
        classifier = Mock()
        classifier.classify.return_value = IntentClassifier.fallback("What does the policy say?")
        knowledge = Mock()
        knowledge.run.side_effect = RuntimeError("provider unavailable")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused)

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            router.route(AgentRequest(question="What does the policy say?"))
        self.assertEqual(router.last_destination, "knowledge")

    def test_langgraph_routes_to_each_intent_agent(self):
        cases = [
            ("What does the product policy say?", "knowledge"),
            ("Compare document counts by domain", "analytics"),
            ("What was revenue in 2024?", "hybrid"),
            ("Show the dashboard", "dashboard"),
        ]
        for question, selected_agent in cases:
            with self.subTest(selected_agent=selected_agent):
                classifier = Mock()
                classifier.classify.return_value = IntentClassifier.fallback(question)
                agents = {
                    name: Mock(run=Mock(return_value=AgentResult(answer=name, agent=name)))
                    for name in ("knowledge", "analytics", "hybrid", "dashboard")
                }
                router = AgentRouter(
                    classifier,
                    agents["knowledge"],
                    agents["analytics"],
                    agents["hybrid"],
                    agents["dashboard"],
                )
                result = router.route(AgentRequest(question=question))
                self.assertEqual(result.agent, selected_agent)
                agents[selected_agent].run.assert_called_once()
                for name, agent in agents.items():
                    if name != selected_agent:
                        agent.run.assert_not_called()

    def test_all_twelve_proposal_business_cases_reach_the_expected_route(self):
        dataset = json.loads((Path(__file__).resolve().parents[1] / "data/evaluation/archive/agents/proposal_business_route_cases.json").read_text())
        for case in dataset["cases"]:
            business_case, question, expected_route = case["id"], case["question"], case["expected_route"]
            with self.subTest(business_case=business_case):
                classifier = Mock()
                classifier.classify.side_effect = IntentClassifier.fallback
                agents = {
                    name: Mock(run=Mock(return_value=AgentResult(answer=name, agent=name)))
                    for name in ("knowledge", "analytics", "hybrid", "dashboard", "report")
                }
                router = AgentRouter(
                    classifier,
                    agents["knowledge"],
                    agents["analytics"],
                    agents["hybrid"],
                    agents["dashboard"],
                    agents["report"],
                )

                result = router.route(AgentRequest(question=question))

                self.assertEqual(result.agent, expected_route)
                agents[expected_route].run.assert_called_once()
                for name, agent in agents.items():
                    if name != expected_route:
                        agent.run.assert_not_called()

    def test_report_rejects_unprovided_citation_ids(self):
        hybrid = Mock()
        source = AgentResult(answer="A source answer [S1]", agent="hybrid", evidence=[
            Evidence(citation_id="S1", source_type="document", source="report", content="Revenue data")
        ])
        hybrid.run.return_value = source
        llm = Mock()
        llm.generate.return_value = "Unsupported figure [S9]"
        result = ReportAgent(knowledge=hybrid, llm=llm).run(AgentRequest(question="summarize report"))
        self.assertEqual(result.answer, "The answer was withheld because its citations could not be verified. Please retry the question.")
        self.assertEqual(result.agent, "report")
        self.assertTrue(result.metadata["citation_validation_failed"])
        self.assertEqual(llm.generate.call_count, 2)

    def test_report_repairs_one_missing_citation_without_weakening_validation(self):
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[
            Evidence(
                citation_id="S1", source_type="document", source="annual report, page 12",
                content="The report describes the company's strategy and initiatives.",
            )
        ])
        llm = Mock()
        llm.generate.side_effect = [
            "The report describes its strategy.",
            "The report describes its strategy [S1].",
        ]

        result = ReportAgent(knowledge=knowledge, llm=llm).run(
            AgentRequest(question="Summarize the strategy")
        )

        self.assertEqual(result.answer, "The report describes its strategy [S1].")
        self.assertTrue(result.metadata["citation_repair_attempted"])
        self.assertEqual(llm.generate.call_count, 2)
        self.assertIn("missing_or_unknown_citations", llm.generate.call_args.args[0])

    def test_executive_report_distinguishes_documented_initiatives_from_inferred_risks(self):
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="Source passages", agent="knowledge", evidence=[
            Evidence(
                citation_id="S1", source_type="document", source="2025 report, page 104",
                content="The company reported leadership training and a 360-degree assessment.",
            )
        ])
        llm = Mock()
        llm.generate.return_value = "The report describes leadership training and a 360-degree assessment [S1]."

        result = ReportAgent(knowledge=knowledge, llm=llm).run(
            AgentRequest(question="Summarize the options and risks for leadership")
        )

        prompt = llm.generate.call_args.args[0]
        self.assertIn("distinguish report-stated initiatives from actual alternatives", prompt)
        self.assertIn("List a risk only when the cited evidence explicitly identifies it", prompt)
        self.assertIn("say so clearly", prompt)
        self.assertEqual(result.agent, "report")

    def test_financial_change_report_combines_metric_rows_and_cited_causes(self):
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="", agent="knowledge", evidence=[
            Evidence(citation_id="S1", source_type="document", source="2021 annual report, p. 55",
                     content="The company expanded dairy farms and invested in a new production facility.")
        ])
        analytics = Mock()
        analytics.run.return_value = AgentResult(answer="", agent="analytics", evidence=[
            Evidence(citation_id="M1", source_type="verified_metric", source="Vinamilk 2021 · Total assets",
                     content="Total assets increased from 10 to 12 billion VND.",
                     metadata={"metric_name": "total_assets", "fiscal_year": 2021})
        ], data={"financial": []})
        llm = Mock()
        llm.generate.return_value = "Tổng tài sản tăng từ 10 lên 12 tỷ đồng [M1]. Báo cáo nêu công ty đầu tư cơ sở sản xuất [S1], nhưng không xác nhận đây là nguyên nhân trực tiếp."

        result = ReportAgent(knowledge=knowledge, analytics=analytics, llm=llm).run(
            AgentRequest(question="tại sao total assets của 2021 lại tăng so với 2020")
        )

        analytics.run.assert_called_once()
        self.assertIn("do not establish why", llm.generate.call_args.args[0])
        self.assertIn("[S1]", result.answer)
        self.assertIn("[M1]", result.answer)
        self.assertEqual({item.citation_id for item in result.evidence}, {"S1", "M1"})

    def test_report_financial_summary_uses_matching_metric_without_inventing_reconciliation(self):
        hybrid = Mock()
        hybrid.run.return_value = AgentResult(answer="Revenue [S1]", agent="hybrid", evidence=[
            Evidence(citation_id="S1", source_type="document", source="report", content="Audited-statement revenue 52.6T"),
            Evidence(citation_id="S7", source_type="document", source="report", content="Headline total consolidated revenue 61.824T and consolidated profit after tax 9.453T"),
        ])
        llm = Mock()
        llm.generate.return_value = "Vinamilk reported total consolidated revenue of 61.824 trillion VND and consolidated profit after tax of 9.453 trillion VND [1]."
        result = ReportAgent(knowledge=hybrid, llm=llm).run(AgentRequest(question="Summarize revenue and profit"))
        self.assertIn("61.824T", llm.generate.call_args.args[0])
        self.assertIn("return exactly two concise bullets", llm.generate.call_args.args[0])
        self.assertIn("do not invent an accounting basis or reconciliation", llm.generate.call_args.args[0])
        self.assertIn("never convert or rescale values", llm.generate.call_args.args[0])
        self.assertIn("tỷ to triệu", llm.generate.call_args.args[0])
        self.assertNotIn("Include both headline and statement figures for every requested metric", llm.generate.call_args.args[0])
        self.assertIn("Vietnamese periods group thousands", llm.generate.call_args.args[0])
        self.assertIn("Priority IDs: [S7]", llm.generate.call_args.args[0])
        self.assertEqual(result.answer, "Vinamilk reported total consolidated revenue of 61.824 trillion VND and consolidated profit after tax of 9.453 trillion VND [S7].")
        self.assertTrue(hybrid.run.call_args.args[0].metadata["evidence_only"])

    def test_financial_report_rejects_rescaled_or_rounded_cited_values(self):
        evidence = [Evidence(
            citation_id="S3", source_type="document", source="annual report",
            content="Total consolidated revenue 2024; profit after tax 2024; tỷ đồng tỷ đồng 9.453 61.824",
        )]

        self.assertTrue(_financial_facts_match_cited_evidence(
            "Revenue 61.824 tỷ đồng and profit 9.453 tỷ đồng [S3]", evidence,
        ))
        self.assertFalse(_financial_facts_match_cited_evidence(
            "Revenue 61.824 triệu đồng and profit 9.453 triệu đồng [S3]", evidence,
        ))
        self.assertFalse(_financial_facts_match_cited_evidence(
            "Revenue 61.8 tỷ đồng and profit 9.453 tỷ đồng [S3]", evidence,
        ))
        self.assertFalse(_financial_facts_match_cited_evidence(
            "Revenue 61.824 billion USD and profit 9.453 billion USD [S3]", evidence,
        ))

    def test_report_withholds_a_financial_answer_with_a_cited_unit_mismatch(self):
        hybrid = Mock()
        hybrid.run.return_value = AgentResult(answer="Revenue [S1]", agent="hybrid", evidence=[
            Evidence(
                citation_id="S1", source_type="document", source="annual report",
                content="Revenue 2024; profit 2024; tỷ đồng tỷ đồng 9.453 61.824",
            )
        ])
        llm = Mock()
        llm.generate.return_value = "Revenue 61.824 triệu đồng and profit 9.453 triệu đồng [S1]"

        result = ReportAgent(knowledge=hybrid, llm=llm).run(
            AgentRequest(question="Summarize revenue and profit")
        )

        self.assertTrue(result.metadata["financial_evidence_validation_failed"])
        self.assertEqual(result.agent, "report")
        self.assertIn("withheld", result.answer)

    def test_numeric_report_citations_map_to_prompt_evidence_and_reject_out_of_range(self):
        evidence = [
            Evidence(citation_id="S1", source_type="document", source="report"),
            Evidence(citation_id="S7", source_type="document", source="report"),
        ]
        answer = _normalize_numeric_citations("Headline 【2】, audited [1], year [2024], invalid [3]", evidence)
        self.assertEqual(answer, "Headline [S7], audited [S1], year [2024], invalid [3]")

    def test_vinamilk_financial_retrieval_rewrites_english_queries_bilingually(self):
        rewritten = _financial_retrieval_query(
            "What were Vinamilk's 2024 revenue and profit?",
            "Công ty Cổ phần Sữa Việt Nam (Vinamilk)",
        )
        self.assertIn("Tổng doanh thu hợp nhất", rewritten)
        self.assertIn("lợi nhuận sau thuế hợp nhất", rewritten)

    def test_other_queries_are_not_rewritten(self):
        self.assertEqual(
            _financial_retrieval_query("Summarize sustainability initiatives", "Vinamilk"),
            "Summarize sustainability initiatives",
        )


if __name__ == "__main__":
    unittest.main()
