import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.intent_classifier import IntentClassifier
from core.analytics.metric_ontology import resolve_metric_names
from core.agents.knowledge_agent import KnowledgeAgent, _financial_retrieval_query
from core.agents.report_agent import ReportAgent, _financial_facts_match_cited_evidence
from core.agents.router import AgentRouter
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.agents.report_agent import _normalize_numeric_citations
from core.models.agents import AgentRequest, AgentResult, Evidence
from core.rag.rag_service import RAGResult


class AgentFlowTest(unittest.TestCase):
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

    def test_generic_how_many_question_stays_document_qa(self):
        intent = IntentClassifier.fallback("Trong 100 ml sữa có bao nhiêu năng lượng và protein?")
        self.assertEqual(intent.intent, "knowledge")
        self.assertFalse(intent.needs_sql)

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
        dataset = json.loads((Path(__file__).resolve().parents[1] / "data/evaluation/proposal_business_route_cases.json").read_text())
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
