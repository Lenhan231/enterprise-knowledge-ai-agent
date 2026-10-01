import re

from core.analytics.business_metric_catalog import (
    BUSINESS_DECISION_PROFILES,
    BUSINESS_METRIC_CATALOG,
    resolve_business_metric_names,
)
from core.agents.base import BaseAgent
from core.models.agents import (
    AgentRequest,
    AgentResult,
    Evidence,
)
from core.rag.rag_service import RAGResult, RAGService


def _financial_retrieval_query(question: str, company: str | None) -> str:
    text = question.casefold()
    asks_revenue = any(term in text for term in ("revenue", "sales", "doanh thu"))
    asks_profit = any(term in text for term in ("profit", "earnings", "net income", "lợi nhuận"))
    if company and "vinamilk" in company.casefold() and asks_revenue and asks_profit:
        return f"{question} Tổng doanh thu hợp nhất và lợi nhuận sau thuế hợp nhất"
    return question


def _decision_evidence_score(context: dict, question: str, domain: str) -> tuple[int, int, float]:
    """Return domain relevance and evidence-format scores for a retrieved passage."""
    profile = BUSINESS_DECISION_PROFILES[domain]
    primary = set(profile["primary_metrics"])
    domain_metrics = {
        name for name, definition in BUSINESS_METRIC_CATALOG.items()
        if definition["domain"] == domain
    }
    requested = resolve_business_metric_names(question) & domain_metrics
    metadata = context.get("metadata") or {}
    text = " ".join((
        str(context.get("content") or ""),
        str(metadata.get("section_title") or ""),
        str(metadata.get("table_title") or ""),
    )).casefold()
    matched = set()
    for name in domain_metrics:
        definition = BUSINESS_METRIC_CATALOG[name]
        phrases = {name.replace("_", " "), definition["label"], *definition.get("aliases", ())}
        if any(" ".join(phrase.casefold().split()) in text for phrase in phrases):
            matched.add(name)

    domain_score = (
        6 * (metadata.get("business_decision_domain") == domain)
        + 3 * len(matched & primary)
        + len(matched - primary)
    )
    if not domain_score:
        return 0, 0, 0.0

    needs_values = bool(requested) or bool(re.search(r"\b(?:19|20)\d{2}\b|\d", question)) or any(
        term in question.casefold() for term in (
            "metric", "kpi", "value", "revenue", "growth", "compare", "trend",
            "bao nhiêu", "chỉ số", "doanh thu", "tăng trưởng", "so sánh", "xu hướng",
        )
    )
    has_number = bool(re.search(r"\d", str(context.get("content") or "")))
    layout = str(metadata.get("layout_type") or metadata.get("element_type") or "").casefold()
    evidence_score = float(needs_values and has_number)
    if needs_values and layout in {"table", "table_chunk", "extracted_table"}:
        evidence_score += 1.5
    if layout in {"text", "paragraph", "narrative"} and any(
        term in question.casefold() for term in ("why", "strategy", "risk", "decision", "vì sao", "chiến lược", "rủi ro", "quyết định")
    ):
        evidence_score += 0.5
    return domain_score, len(requested & matched), evidence_score


def _rank_business_decision_evidence(
    contexts: list[dict], question: str, domain: str, limit: int,
) -> list[dict]:
    """Rerank an authorized candidate pool before the smaller report prompt."""
    scored = [
        (_decision_evidence_score(context, question, domain), index, context)
        for index, context in enumerate(contexts)
    ]
    relevant = [item for item in scored if item[0][0] > 0]
    # Sparse corpora may have no exact catalog phrase; retain the retriever's
    # authorized ranking rather than returning an empty report context.
    selected = sorted(
        relevant or scored,
        key=lambda item: (item[0][1], item[0][2], item[0][0], -item[1]),
        reverse=True,
    )[:limit]
    ranked = [dict(context) for _, _, context in selected]
    for index, context in enumerate(ranked, start=1):
        context["source_id"] = f"S{index}"
    return ranked


class KnowledgeAgent(BaseAgent):
    def __init__(
        self,
        rag_service: RAGService | None = None,
    ):
        self.rag = rag_service or RAGService()

    def run(
        self,
        request: AgentRequest,
    ) -> AgentResult:
        role = request.metadata.get("role")
        if not isinstance(role, str) or not role:
            raise ValueError("Knowledge retrieval requires a trusted authenticated role")
        rag_options = {
            "limit": 10,
            "company": request.metadata.get("company"),
            "roles": [role],
        }
        if request.metadata.get("retrieval_method", "hybrid") != "hybrid":
            rag_options["retrieval_method"] = request.metadata["retrieval_method"]
        if request.metadata.get("evidence_only"):
            # Report synthesis uses one generation over its evidence; keep its
            # ranked context small enough for the configured model's TPM cap.
            rag_options["limit"] = 3 if request.metadata.get("decision_support") else 5
            decision_domain = request.metadata.get("business_decision_domain")
            if decision_domain in BUSINESS_DECISION_PROFILES:
                # Retrieve a bounded authorized candidate pool, score domain
                # and numeric/layout relevance, then send only report top-k.
                rag_options["limit"] = 15
            retrieval_query = _financial_retrieval_query(
                request.question,
                request.metadata.get("company"),
            )
            contexts = self.rag.retrieve_contexts(retrieval_query, **rag_options)
            if decision_domain in BUSINESS_DECISION_PROFILES:
                contexts = _rank_business_decision_evidence(
                    contexts, request.question, decision_domain, 3,
                )
            result = RAGResult(
                answer="",
                contexts=contexts,
                insufficient_context=not contexts,
            )
        else:
            retrieval_query = _financial_retrieval_query(
                request.question,
                request.metadata.get("company"),
            )
            if retrieval_query != request.question:
                rag_options["retrieval_query"] = retrieval_query
            result = self.rag.generate_answer(request.question, **rag_options)
        evidence = [
            Evidence(
                citation_id=context["source_id"],
                source_type="document",
                source=context["document_name"],
                content=context["content"],
                metadata={
                    **context["metadata"],
                    "chunk_index": context["chunk_index"],
                    "retrieval_score": context["retrieval_score"],
                    "retrieval_method": context["retrieval_method"],
                },
            )
            for context in result.contexts
        ]

        return AgentResult(
            answer=result.answer,
            agent="knowledge",
            evidence=evidence,
            metadata={"insufficient_context": result.insufficient_context},
        )

    def close(self) -> None:
        self.rag.close()
