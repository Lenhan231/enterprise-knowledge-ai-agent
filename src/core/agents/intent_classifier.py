import json

from core.analytics.metric_ontology import resolve_metric_names
from core.llm.groq_provider import GroqProvider
from core.models.intent import IntentResult
from core.prompts.intent import INTENT_CLASSIFIER_PROMPT


class IntentClassifier:
    def __init__(self, llm: GroqProvider | None = None):
        self.llm = llm or GroqProvider()

    def classify(self, question: str) -> IntentResult:
        prompt = INTENT_CLASSIFIER_PROMPT.format(
            question=question,
        )

        try:
            raw = self.llm.generate(prompt)
            payload = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
            result = IntentResult.model_validate(payload)
            return self._normalize_data_intent(question, result)
        except Exception:
            return self.fallback(question)

    @staticmethod
    def fallback(question: str) -> IntentResult:
        text = question.casefold()
        financial_metrics = resolve_metric_names(text)
        analytics = bool(financial_metrics) or any(term in text for term in (
            "trend", "compare", "growth", "tăng trưởng", "so sánh", "thống kê"
        ))
        dashboard = any(term in text for term in ("dashboard", "chart", "visualize", "biểu đồ", "đồ thị"))
        summarize = any(term in text for term in ("summarize", "summary", "report", "tổng hợp", "báo cáo"))
        financial_metric = bool(financial_metrics) or any(term in text for term in ("financial", "tài chính", "biên lợi nhuận"))
        intent = "dashboard" if dashboard else "hybrid" if analytics and (summarize or financial_metric) else "analytics" if analytics else "knowledge"
        return IntentResult(intent=intent, needs_knowledge=intent in {"knowledge", "hybrid"} or financial_metric,
                            needs_sql=intent in {"analytics", "hybrid"},
                            output_mode="dashboard" if dashboard else "answer", confidence=0.35)

    @classmethod
    def _normalize_data_intent(cls, question: str, result: IntentResult) -> IntentResult:
        text = question.casefold()
        metadata_counts = any(term in text for term in (
            "document count", "document counts", "count of document",
            "number of document", "count documents", "counts by domain",
            "documents by domain", "documents by business domain",
            "số lượng tài liệu", "thống kê tài liệu", "tài liệu theo lĩnh vực",
        ))
        if metadata_counts and result.output_mode != "dashboard":
            return result.model_copy(update={
                "intent": "analytics", "needs_knowledge": False,
                "needs_sql": True, "output_mode": "answer",
            })

        fallback = cls.fallback(question)
        if fallback.needs_knowledge and fallback.needs_sql and result.output_mode != "dashboard":
            return result.model_copy(update={"intent": "hybrid", "needs_knowledge": True, "needs_sql": True})
        return result

    def close(self) -> None:
        if hasattr(self.llm, "close"):
            self.llm.close()

if __name__ == "__main__":
    intent_classifier = IntentClassifier()
    question = "Show me revenue trend for the last 5 quarters"
    print(intent_classifier.classify(question))
    intent_classifier.close()
