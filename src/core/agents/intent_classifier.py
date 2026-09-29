import json
import re

from core.analytics.metric_ontology import resolve_metric_names
from core.llm.groq_provider import GroqProvider
from core.models.intent import IntentResult
from core.prompts.intent import INTENT_CLASSIFIER_PROMPT


def _is_document_count_request(text: str) -> bool:
    explicit_count = any(term in text for term in (
        "document count", "document counts", "count of document",
        "number of document", "count documents", "counts by domain",
        "documents by domain", "documents by business domain",
        "how many reports", "number of reports", "count of reports",
        "reports by year", "annual reports by year",
        "số lượng tài liệu", "thống kê tài liệu", "tài liệu theo lĩnh vực",
        "bao nhiêu báo cáo", "số báo cáo", "báo cáo theo năm",
    ))
    report_count = "report" in text and any(term in text for term in (
        "how many", "number of", "count of", "count the", "bao nhiêu", "số lượng",
    ))
    return explicit_count or report_count


class IntentClassifier:
    def __init__(self, llm: GroqProvider | None = None):
        self.llm = llm or GroqProvider()

    def classify(self, question: str) -> IntentResult:
        fallback = self.fallback(question)
        if fallback.intent == "report" and any(term in question.casefold() for term in (
            "why", "reason", "cause", "tại sao", "vì sao", "nguyên nhân",
        )):
            return fallback
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
        metadata_counts = _is_document_count_request(text)
        financial_summary = (
            any(term in text for term in ("revenue", "sales", "doanh thu"))
            and any(term in text for term in ("profit", "earnings", "net income", "lợi nhuận"))
            and len(set(re.findall(r"\b(?:19|20)\d{2}\b", text))) <= 1
            and not any(term in text for term in (
                "trend", "growth", "compare", "comparison", "compared", "versus", " vs ",
                "year over year", "year-over-year", "change", "between", "across years", "by year",
                "tăng trưởng", "so sánh", "so với", "thay đổi", "qua các năm", "theo năm",
                "chart", "dashboard", "biểu đồ",
            ))
        )
        why_financial_change = (
            any(term in text for term in ("why", "reason", "cause", "tại sao", "vì sao", "nguyên nhân"))
            and len(financial_metrics) >= 1
            and len(set(re.findall(r"\b(?:19|20)\d{2}\b", text))) >= 2
        )
        analytics = metadata_counts or bool(financial_metrics) or any(term in text for term in (
            "trend", "compare", "growth", "tăng trưởng", "so sánh", "thống kê"
        ))
        dashboard = any(term in text for term in ("dashboard", "chart", "visualize", "biểu đồ", "đồ thị"))
        report = not metadata_counts and (financial_summary or why_financial_change or any(term in text for term in (
            "summarize", "summarise", "summary of", "tóm tắt", "write a report",
            "draft a report", "generate a report", "prepare a report", "create a report",
            "viết báo cáo", "lập báo cáo", "tạo báo cáo",
        )))
        financial_metric = bool(financial_metrics) or any(term in text for term in ("financial", "tài chính", "biên lợi nhuận"))
        intent = "dashboard" if dashboard else "report" if report else "hybrid" if analytics and financial_metric else "analytics" if analytics else "knowledge"
        return IntentResult(intent=intent, needs_knowledge=intent in {"knowledge", "hybrid", "report"} or financial_metric,
                            needs_sql=intent in {"analytics", "hybrid", "report"},
                            output_mode="dashboard" if dashboard else "answer", confidence=0.35)

    @classmethod
    def _normalize_data_intent(cls, question: str, result: IntentResult) -> IntentResult:
        text = question.casefold()
        metadata_counts = _is_document_count_request(text)
        if metadata_counts and result.output_mode != "dashboard":
            return result.model_copy(update={
                "intent": "analytics", "needs_knowledge": False,
                "needs_sql": True, "output_mode": "answer",
            })

        fallback = cls.fallback(question)
        if fallback.intent == "report" and result.output_mode != "dashboard":
            return fallback
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
