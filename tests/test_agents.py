import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.intent_classifier import IntentClassifier
from core.agents.router import AgentRouter
from core.analytics.metric_ontology import resolve_metric_names
from core.models.agents import AgentRequest, AgentResult
from core.prompts.intent import INTENT_CLASSIFIER_PROMPT


class AgentRoutingTest(unittest.TestCase):
    def test_metric_ontology_resolves_vietnamese_commerce_metrics(self):
        self.assertEqual(
            resolve_metric_names("So sánh doanh thu và giá vốn theo năm"),
            {"revenue", "cogs"},
        )
        self.assertEqual(
            resolve_metric_names("Theo dõi tỷ lệ hết hàng và số ngày đủ hàng"),
            {"stockout_rate", "days_of_supply"},
        )

    def test_classifier_fallback_routes_vietnamese_commerce_question_to_analytics(self):
        intent = IntentClassifier.fallback("So sánh doanh thu theo khu vực năm 2025")

        self.assertEqual(intent.intent, "analytics")
        self.assertTrue(intent.needs_sql)
        self.assertFalse(intent.needs_knowledge)
        self.assertEqual(intent.reason, "Phân loại dự phòng theo quy tắc")

    def test_intent_prompt_requires_vietnamese_output(self):
        self.assertIn("tiếng Việt", INTENT_CLASSIFIER_PROMPT)

    def test_classifier_fallback_routes_generic_question_to_knowledge(self):
        intent = IntentClassifier.fallback("Trong 100 ml sữa có bao nhiêu năng lượng và protein?")
        self.assertEqual(intent.intent, "knowledge")
        self.assertFalse(intent.needs_sql)

    def test_classifier_fallback_routes_summary_request_to_report(self):
        intent = IntentClassifier.fallback("Tóm tắt doanh thu và giá vốn năm 2025")
        self.assertEqual(intent.intent, "report")
        self.assertTrue(intent.needs_sql)
        self.assertFalse(intent.needs_knowledge)

    def test_classifier_accepts_fenced_json(self):
        llm = Mock()
        llm.generate.return_value = (
            '```json\n{"intent":"knowledge","needs_knowledge":true,"needs_sql":false,'
            '"output_mode":"answer","confidence":0.9}\n```'
        )
        intent = IntentClassifier(llm).classify("Find the policy")
        self.assertEqual(intent.intent, "knowledge")

    def test_document_metadata_counts_are_normalized_to_analytics(self):
        llm = Mock()
        llm.generate.return_value = (
            '{"intent":"knowledge","needs_knowledge":true,"needs_sql":false,'
            '"output_mode":"answer","confidence":0.9}'
        )
        intent = IntentClassifier(llm).classify("Compare document counts by business domain")
        self.assertEqual(intent.intent, "analytics")
        self.assertFalse(intent.needs_knowledge)
        self.assertTrue(intent.needs_sql)

    def test_commerce_metric_is_normalized_to_analytics_when_model_misclassifies_it(self):
        llm = Mock()
        llm.generate.return_value = (
            '{"intent":"knowledge","needs_knowledge":true,"needs_sql":false,'
            '"output_mode":"answer","confidence":0.9}'
        )

        intent = IntentClassifier(llm).classify("So sánh doanh thu theo khu vực năm 2025")

        self.assertEqual(intent.intent, "analytics")
        self.assertFalse(intent.needs_knowledge)
        self.assertTrue(intent.needs_sql)

    def test_router_records_selected_destination(self):
        classifier = Mock()
        classifier.classify.return_value = IntentClassifier.fallback("Find the policy")
        knowledge = Mock()
        knowledge.run.return_value = AgentResult(answer="grounded", agent="knowledge")
        unused = Mock()
        router = AgentRouter(classifier, knowledge, unused, unused, unused)

        result = router.route(AgentRequest(question="Find the policy"))

        self.assertEqual(result.agent, "knowledge")
        self.assertEqual(router.last_destination, "knowledge")

    def test_structured_report_falls_back_to_analytics_without_report_agent(self):
        classifier = Mock()
        classifier.classify.return_value = IntentClassifier.fallback("Tóm tắt doanh thu và giá vốn năm 2025")
        analytics = Mock()
        analytics.run.return_value = AgentResult(answer="Tóm tắt có căn cứ", agent="analytics")
        unused = Mock()
        router = AgentRouter(classifier, unused, analytics, unused, unused)

        result = router.route(AgentRequest(question="Tóm tắt doanh thu và giá vốn năm 2025"))

        self.assertEqual(result.agent, "analytics")
        self.assertEqual(router.last_destination, "analytics")


if __name__ == "__main__":
    unittest.main()
