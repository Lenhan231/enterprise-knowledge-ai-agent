import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.intent_classifier import IntentClassifier
from core.analytics.metric_ontology import resolve_metric_names
from core.agents.knowledge_agent import KnowledgeAgent, _report_retrieval_query
from core.agents.report_agent import ReportAgent
from core.agents.router import AgentRouter
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.agents.report_agent import _normalize_numeric_citations
from core.models.agents import AgentRequest, AgentResult, Evidence
from core.rag.rag_service import RAGResult


class AgentFlowTest(unittest.TestCase):
    def test_metric_ontology_resolves_bilingual_aliases_and_prefers_specific_phrase(self):
        self.assertEqual(resolve_metric_names("Revenue and profit after tax"), {"net_revenue", "profit_after_tax"})
        self.assertEqual(resolve_metric_names("Tổng doanh thu hợp nhất năm 2024"), {"total_consolidated_revenue"})

    def test_generic_how_many_question_stays_document_qa(self):
        intent = IntentClassifier.fallback("Trong 100 ml sữa có bao nhiêu năng lượng và protein?")
        self.assertEqual(intent.intent, "knowledge")
        self.assertFalse(intent.needs_sql)

    def test_sql_analytics_agent_filters_using_canonical_vietnamese_metric(self):
        repository = Mock()
        repository.execute_authorized_analytics.return_value = {
            "results": [{"metric_name": "total_consolidated_revenue", "metric_label": "Doanh thu hợp nhất",
                         "fiscal_year": 2024, "metric_value": 61824, "unit": "tỷ đồng",
                         "evidence_document_ids": ["AR24"]}],
            "evidence": [{"metric_name": "total_consolidated_revenue", "metric_label": "Doanh thu hợp nhất",
                          "fiscal_year": 2024, "metric_value": 61824, "unit": "tỷ đồng",
                          "company": "Vinamilk", "document_id": "AR24", "page_number": 12,
                          "source_url": "https://example.test/ar24", "source_quote": "Doanh thu 61.824 tỷ đồng"}],
            "documents": [],
        }
        llm = Mock()
        llm.generate.return_value = (
            '{"sql":"SELECT metric_name, metric_label, fiscal_year, metric_value, unit, '
            'ARRAY_AGG(DISTINCT document_id) AS evidence_document_ids '
            'FROM authorized_financial_metrics WHERE fiscal_year = 2024 AND '
            "metric_name = 'total_consolidated_revenue' GROUP BY metric_name, metric_label, fiscal_year, metric_value, unit" + '"}'
        )
        agent = SQLAnalyticsAgent(repository, llm)
        result = agent.run(AgentRequest(question="Doanh thu hợp nhất năm 2024", metadata={"role": "finance_analyst"}))
        repository.execute_authorized_analytics.assert_called_once()
        self.assertEqual(repository.execute_authorized_analytics.call_args.args[1:], ("finance_analyst", "", None))
        self.assertEqual([row["metric_name"] for row in result.data["financial"]], ["total_consolidated_revenue"])

    def test_classifier_fallback_routes_summary_of_metrics_to_hybrid(self):
        intent = IntentClassifier.fallback("Summarize Vinamilk revenue and profit for 2024")
        self.assertEqual(intent.intent, "hybrid")
        self.assertTrue(intent.needs_sql)
        self.assertTrue(intent.needs_knowledge)

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

    def test_financial_fact_questions_use_both_verified_analytics_and_documents(self):
        intent = IntentClassifier.fallback("What was Vinamilk's revenue in 2024?")
        self.assertEqual(intent.intent, "hybrid")
        self.assertTrue(intent.needs_sql)
        self.assertTrue(intent.needs_knowledge)

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
        result = ReportAgent(hybrid=hybrid, llm=llm).run(AgentRequest(question="summarize report"))
        self.assertEqual(result.answer, "The answer was withheld because its citations could not be verified. Please retry the question.")
        self.assertTrue(result.metadata["citation_validation_failed"])

    def test_report_financial_summary_uses_matching_metric_without_inventing_reconciliation(self):
        hybrid = Mock()
        hybrid.run.return_value = AgentResult(answer="Revenue [S1]", agent="hybrid", evidence=[
            Evidence(citation_id="S1", source_type="document", source="report", content="Audited-statement revenue 52.6T"),
            Evidence(citation_id="S7", source_type="document", source="report", content="Headline total consolidated revenue 61.824T and consolidated profit after tax 9.453T"),
        ])
        llm = Mock()
        llm.generate.return_value = "Vinamilk reported total consolidated revenue of 61.824 trillion VND and consolidated profit after tax of 9.453 trillion VND [1]."
        result = ReportAgent(hybrid=hybrid, llm=llm).run(AgentRequest(question="Summarize revenue and profit"))
        self.assertIn("61.824T", llm.generate.call_args.args[0])
        self.assertIn("return exactly two concise bullets", llm.generate.call_args.args[0])
        self.assertIn("do not invent an accounting basis or reconciliation", llm.generate.call_args.args[0])
        self.assertNotIn("Include both headline and statement figures for every requested metric", llm.generate.call_args.args[0])
        self.assertIn("Vietnamese periods group thousands", llm.generate.call_args.args[0])
        self.assertIn("Priority IDs: [S7]", llm.generate.call_args.args[0])
        self.assertEqual(result.answer, "Vinamilk reported total consolidated revenue of 61.824 trillion VND and consolidated profit after tax of 9.453 trillion VND [S7].")
        self.assertTrue(hybrid.run.call_args.args[0].metadata["evidence_only"])

    def test_numeric_report_citations_map_to_prompt_evidence_and_reject_out_of_range(self):
        evidence = [
            Evidence(citation_id="S1", source_type="document", source="report"),
            Evidence(citation_id="S7", source_type="document", source="report"),
        ]
        answer = _normalize_numeric_citations("Headline 【2】, audited [1], year [2024], invalid [3]", evidence)
        self.assertEqual(answer, "Headline [S7], audited [S1], year [2024], invalid [3]")

    def test_vinamilk_report_retrieval_rewrites_english_financial_summary_bilingually(self):
        rewritten = _report_retrieval_query(
            "Summarize Vinamilk's 2024 revenue and profit",
            "Công ty Cổ phần Sữa Việt Nam (Vinamilk)",
            evidence_only=True,
        )
        self.assertIn("Tổng doanh thu hợp nhất", rewritten)
        self.assertIn("lợi nhuận sau thuế hợp nhất", rewritten)

    def test_other_queries_are_not_rewritten(self):
        self.assertEqual(
            _report_retrieval_query("Summarize sustainability initiatives", "Vinamilk", evidence_only=True),
            "Summarize sustainability initiatives",
        )


if __name__ == "__main__":
    unittest.main()
