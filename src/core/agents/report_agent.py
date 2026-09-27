"""Draft a cited report from role-visible passages and verified database facts."""

import re
import logging

from core.agents.base import BaseAgent
from core.agents.hybrid_agent import HybridAgent
from core.llm.groq_provider import GroqProvider
from core.models.agents import AgentRequest, AgentResult, Evidence
from core.rag.rag_service import INSUFFICIENT_ANSWER

_CITATION = re.compile(r"(?:\[|【)([A-Z]\d+)(?:\]|】)")
_NUMERIC_CITATION = re.compile(r"(?:\[|【)(\d+)(?:\]|】)")
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


class ReportAgent(BaseAgent):
    def __init__(self, hybrid: HybridAgent | None = None, llm: GroqProvider | None = None):
        self.hybrid = hybrid or HybridAgent()
        self.llm = llm or GroqProvider()

    def run(self, request: AgentRequest) -> AgentResult:
        report_request = request.model_copy(update={
            "metadata": {**request.metadata, "evidence_only": True},
        })
        source_data = self.hybrid.run(report_request)
        allowed = {item.citation_id for item in source_data.evidence if item.citation_id}
        if not allowed:
            return source_data.model_copy(update={
                "answer": INSUFFICIENT_ANSWER,
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
            "consolidated profit after tax. Use the exact reported values, period, and unit. Each bullet must end in an "
            "exact supplied citation such as [S3]. Do not include differently labelled statement figures. If evidence "
            "conflicts on the same named metric and scope, state that plainly; do not invent an accounting basis or "
            "reconciliation. Vietnamese periods group thousands.\n\n"
            if _is_financial_summary(request.question) else ""
        )
        prompt = (
            "Write a concise answer in the question's language using only the evidence. Every factual sentence or "
            "bullet must end with exact supplied citation IDs in [S1] format. Never invent a citation. "
            "Do not calculate from unverified candidates.\n\n"
            f"{financial_instruction}Request: {request.question}\n\n{priority_note}Evidence:\n{sources}"
        )
        answer = _normalize_numeric_citations(self.llm.generate(prompt).strip(), prompt_evidence)
        citations = set(_CITATION.findall(answer))
        invalid_citations = sorted(citations - allowed)
        if not citations or invalid_citations:
            logger.warning(
                "Report answer citation validation failed (no_citations=%s, unknown_citation_ids=%s)",
                not citations,
                invalid_citations,
            )
            return source_data.model_copy(update={
                "answer": _INVALID_REPORT,
                "metadata": {**source_data.metadata, "citation_validation_failed": True},
            })
        return source_data.model_copy(update={"answer": answer, "agent": "report"})

    def close(self) -> None:
        self.hybrid.close()
        if hasattr(self.llm, "close"):
            self.llm.close()
