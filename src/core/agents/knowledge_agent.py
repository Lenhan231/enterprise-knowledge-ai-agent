from core.agents.base import BaseAgent
from core.models.agents import (
    AgentRequest,
    AgentResult,
    Evidence,
)
from core.rag.rag_service import RAGService


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

        result = self.rag.generate_answer(
            request.question
        )

        evidence = [
            Evidence(
                source_type="document",
                source=context["document_name"],
                content=context["content"],
                metadata={
                    "chunk_index": context["chunk_index"],
                    "similarity_score": (
                        context["similarity_score"]
                    ),
                    **context["metadata"],
                },
            )
            for context in result.contexts
        ]

        return AgentResult(
            answer=result.answer,
            agent="knowledge",
            evidence=evidence,
        )

    def close(self) -> None:
        self.rag.close()