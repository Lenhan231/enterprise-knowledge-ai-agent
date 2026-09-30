"""Draft a cited report from role-visible passages and verified database facts."""

import re
import logging

from core.agents.base import BaseAgent
from core.agents.knowledge_agent import KnowledgeAgent
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.analytics.metric_ontology import resolve_metric_names
from core.llm.groq_provider import GroqProvider
from core.models.agents import AgentRequest, AgentResult, Evidence
from core.rag.rag_service import INSUFFICIENT_ANSWER

_CITATION = re.compile(r"(?:\[|【)([A-Z]\d+)(?:\]|】)")
_NUMERIC_CITATION = re.compile(r"(?:\[|【)(\d+)(?:\]|】)")
_NUMBER = re.compile(r"(?<![\w])\d+(?:(?:[.,]\d{3})|(?:[\s\u00a0\u202f]\d{3}))*(?:[.,]\d+)?")
_UNIT_SCALE_PATTERNS = {
    "billion": re.compile(r"\b(?:billion|tỷ)\b", re.IGNORECASE),
    "million": re.compile(r"\b(?:million|triệu)\b", re.IGNORECASE),
    "thousand": re.compile(r"\b(?:thousand|nghìn)\b", re.IGNORECASE),
    "trillion": re.compile(r"\btrillion\b|(?<=\d)T\b", re.IGNORECASE),
}
_CURRENCY_PATTERNS = {
    "vnd": re.compile(r"\b(?:VND|đồng)\b|₫", re.IGNORECASE),
    "usd": re.compile(r"\b(?:USD|US dollars?)\b|\$", re.IGNORECASE),
    "eur": re.compile(r"\b(?:EUR|euros?)\b|€", re.IGNORECASE),
}
_INVALID_REPORT = "The answer was withheld because its citations could not be verified. Please retry the question."
logger = logging.getLogger(__name__)
_REVENUE_HEADLINE = ("total consolidated revenue", "tổng doanh thu hợp nhất")
_PROFIT_HEADLINE = ("consolidated profit after tax", "consolidated net profit after tax", "lợi nhuận sau thuế hợp nhất")


def _is_financial_summary(question: str) -> bool:
    text = question.casefold()
    return (
        any(term in text for term in ("revenue", "sales", "doanh thu"))
        and any(term in text for term in ("profit", "earnings", "net income", "lợi nhuận"))
    )


def _is_financial_change_explanation(question: str) -> bool:
    text = question.casefold()
    return (
        bool(resolve_metric_names(text))
        and len(set(re.findall(r"\b(?:19|20)\d{2}\b", text))) >= 2
        and any(term in text for term in ("why", "reason", "cause", "tại sao", "vì sao", "nguyên nhân"))
    )


def _normalize_numeric_citations(answer: str, evidence: list[Evidence]) -> str:
    ids = [item.citation_id for item in evidence if item.citation_id]

    def replace(match: re.Match) -> str:
        index = int(match.group(1))
        if 1 <= index <= len(ids):
            return f"[{ids[index - 1]}]"
        return match.group(0)

    return _NUMERIC_CITATION.sub(replace, answer)


def _ordered_report_evidence(evidence: list[Evidence], question: str) -> list[Evidence]:
    if not _is_financial_summary(question):
        return evidence

    def priority(item: Evidence) -> int:
        content = (item.content or "").casefold()
        has_revenue = any(term in content for term in _REVENUE_HEADLINE)
        has_profit = any(term in content for term in _PROFIT_HEADLINE)
        return 0 if has_revenue and has_profit else 1 if has_revenue or has_profit else 2

    return [item for _, item in sorted(enumerate(evidence), key=lambda pair: (priority(pair[1]), pair[0]))]


def _financial_facts_match_cited_evidence(answer: str, evidence: list[Evidence]) -> bool:
    cited_ids = set(_CITATION.findall(answer))
    cited_text = " ".join(
        item.content or "" for item in evidence if item.citation_id in cited_ids
    )
    answer_text = _CITATION.sub("", answer)

    def numbers(text: str) -> set[str]:
        return {
            re.sub(r"(?<=\d)[\s.,]+(?=\d)", "", match)
            for match in _NUMBER.findall(text)
        }

    def scales(text: str) -> set[str]:
        return {scale for scale, pattern in _UNIT_SCALE_PATTERNS.items() if pattern.search(text)}

    def currencies(text: str) -> set[str]:
        return {currency for currency, pattern in _CURRENCY_PATTERNS.items() if pattern.search(text)}

    answer_numbers = numbers(answer_text)
    evidence_numbers = numbers(cited_text)
    answer_scales = scales(answer_text)
    evidence_scales = scales(cited_text)
    answer_currencies = currencies(answer_text)
    evidence_currencies = currencies(cited_text)
    return (
        bool(answer_numbers)
        and answer_numbers.issubset(evidence_numbers)
        and bool(answer_scales)
        and answer_scales.issubset(evidence_scales)
        and (not evidence_currencies or answer_currencies.issubset(evidence_currencies))
    )


def _report_validation_failure(
    answer: str, evidence: list[Evidence], allowed: set[str], question: str,
) -> str | None:
    citations = set(_CITATION.findall(answer))
    if not citations or citations - allowed:
        return "missing_or_unknown_citations"
    if _is_financial_summary(question) and not _financial_facts_match_cited_evidence(answer, evidence):
        return "financial_values_or_units_do_not_match_cited_evidence"
    return None


class ReportAgent(BaseAgent):
    def __init__(
        self,
        knowledge: KnowledgeAgent | None = None,
        analytics: SQLAnalyticsAgent | None = None,
        llm: GroqProvider | None = None,
    ):
        self.knowledge = knowledge or KnowledgeAgent()
        self._owns_knowledge = knowledge is None
        self.analytics = analytics
        self.llm = llm or GroqProvider()

    def run(self, request: AgentRequest) -> AgentResult:
        report_request = request.model_copy(update={
            "metadata": {**request.metadata, "evidence_only": True},
        })
        source_data = self.knowledge.run(report_request)
        if _is_financial_change_explanation(request.question) and self.analytics is not None:
            metric_data = self.analytics.run(request)
            source_data = source_data.model_copy(update={
                "evidence": source_data.evidence + metric_data.evidence,
                "data": metric_data.data,
                "metadata": {**source_data.metadata, **metric_data.metadata},
            })
        allowed = {item.citation_id for item in source_data.evidence if item.citation_id}
        if not allowed:
            return source_data.model_copy(update={
                "answer": INSUFFICIENT_ANSWER,
                "agent": "report",
                "metadata": {**source_data.metadata, "insufficient_context": True},
            })
        prompt_evidence = _ordered_report_evidence(source_data.evidence, request.question)
        headline_sources = [
            item for item in prompt_evidence
            if any(term in (item.content or "").casefold() for term in _REVENUE_HEADLINE)
            and any(term in (item.content or "").casefold() for term in _PROFIT_HEADLINE)
        ]
        sources = "\n\n".join(
            f"[{item.citation_id}] {item.source}\n{item.content or ''}\nMetadata: {item.metadata}"
            for item in prompt_evidence
        )
        priority_note = (
            "Use explicitly labelled consolidated revenue and after-tax profit when they match the request. "
            "Do not add differently labelled statement figures or claim they reconcile. Priority IDs: "
            + ", ".join(f"[{item.citation_id}]" for item in headline_sources)
            + ".\n\n"
            if headline_sources else ""
        )
        financial_instruction = (
            "For this revenue/profit summary, return exactly two concise bullets: total consolidated revenue, then "
            "consolidated profit after tax. Copy each reported number and its unit exactly from the cited evidence; "
            "never convert or rescale values (for example, tỷ to triệu, billion to million), round them, or change "
            "their currency. If a table separates its unit label from the number cells, keep that displayed unit. "
            "Use the exact reported values and period. Each bullet must end in an "
            "exact supplied citation such as [S3]. Do not include differently labelled statement figures. If evidence "
            "conflicts on the same named metric and scope, state that plainly; do not invent an accounting basis or "
            "reconciliation. Vietnamese periods group thousands.\n\n"
            if _is_financial_summary(request.question) else ""
        )
        executive_instruction = (
            "For executive decision-support requests about options, recommendations, or risks, distinguish "
            "report-stated initiatives from actual alternatives considered by leadership. Do not invent options, "
            "recommendations, or risks. List a risk only when the cited evidence explicitly identifies it; if the "
            "reports describe initiatives but do not provide decision alternatives or risks, say so clearly. "
            "Do not title a list of initiatives as 'options considered' or 'alternatives considered' unless the "
            "evidence explicitly says leadership compared or considered those alternatives. Use 'Reported initiatives' "
            "for described programs, policies, or strategies. Explicitly state when the sources do not provide "
            "leadership decision alternatives. "
            "Label an implication as an inference only when the user asks for implications.\n\n"
            if any(term in request.question.casefold() for term in (
                "leadership", "executive", "options", "risks", "lãnh đạo", "rủi ro",
            )) else ""
        )
        change_instruction = (
            "The user asks why a reported financial metric changed between years. Use verified metric evidence only "
            "to state the amounts and direction. Explain a cause only if the retrieved report evidence explicitly "
            "states it and cite that passage. A temporal association or nearby narrative is not proof of causation. "
            "If no cited source explicitly explains the change, say the reports establish the increase but do not "
            "establish why; do not infer causes. Keep metrics and explanations clearly separated.\n\n"
            if _is_financial_change_explanation(request.question) else ""
        )
        prompt = (
            "Write a concise answer in the question's language using only the evidence. Every factual sentence or "
            "bullet must end with exact supplied citation IDs in [S1] format. Never invent a citation. "
            "Do not calculate from unverified candidates.\n\n"
            f"{financial_instruction}{executive_instruction}{change_instruction}Request: {request.question}\n\n{priority_note}Evidence:\n{sources}"
        )
        answer = _normalize_numeric_citations(self.llm.generate(prompt).strip(), prompt_evidence)
        validation_failure = _report_validation_failure(
            answer, prompt_evidence, allowed, request.question,
        )
        repaired = validation_failure is not None
        if repaired:
            correction = (
                "\n\nYour previous draft failed validation: " + validation_failure + ". "
                "Rewrite the answer using only the evidence above. End every factual sentence with exact supplied IDs "
                "in [S1] format; copy values and units exactly when relevant. Do not add claims that are not supported."
            )
            answer = _normalize_numeric_citations(
                self.llm.generate(prompt + correction).strip(), prompt_evidence,
            )
            validation_failure = _report_validation_failure(
                answer, prompt_evidence, allowed, request.question,
            )
        if validation_failure:
            if validation_failure == "missing_or_unknown_citations":
                citations = set(_CITATION.findall(answer))
                logger.warning(
                    "Report answer citation validation failed (no_citations=%s, unknown_citation_ids=%s)",
                    not citations, sorted(citations - allowed),
                )
                failure_metadata = {"citation_validation_failed": True}
            else:
                logger.warning("Report financial answer did not preserve cited numeric values and magnitude units")
                failure_metadata = {"financial_evidence_validation_failed": True}
            return source_data.model_copy(update={
                "answer": _INVALID_REPORT,
                "agent": "report",
                "metadata": {**source_data.metadata, **failure_metadata},
            })
        metadata = {**source_data.metadata}
        if repaired:
            metadata["citation_repair_attempted"] = True
        return source_data.model_copy(update={"answer": answer, "agent": "report", "metadata": metadata})

    def close(self) -> None:
        if self._owns_knowledge:
            self.knowledge.close()
        if hasattr(self.llm, "close"):
            self.llm.close()
