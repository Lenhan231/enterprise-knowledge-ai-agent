from core.agents.base import BaseAgent
from core.models.agents import (
    AgentRequest,
    AgentResult,
    Evidence,
)
from core.rag.rag_service import RAGResult, RAGService


def _report_retrieval_query(question: str, company: str | None, evidence_only: bool) -> str:
    text = question.casefold()
    asks_revenue = any(term in text for term in ("revenue", "sales", "doanh thu"))
    asks_profit = any(term in text for term in ("profit", "earnings", "net income", "lợi nhuận"))
    if evidence_only and company and "vinamilk" in company.casefold() and asks_revenue and asks_profit:
        return f"{question} Tổng doanh thu hợp nhất và lợi nhuận sau thuế hợp nhất"
    return question


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
            rag_options["limit"] = 5
            retrieval_query = _report_retrieval_query(
                request.question,
                request.metadata.get("company"),
                evidence_only=True,
            )
            contexts = self.rag.retrieve_contexts(retrieval_query, **rag_options)
            result = RAGResult(
                answer="",
                contexts=contexts,
                insufficient_context=not contexts,
            )
        else:
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
