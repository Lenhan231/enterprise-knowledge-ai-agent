import asyncio

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

    async def run(
        self,
        request: AgentRequest,
    ) -> AgentResult:

        result = await asyncio.to_thread(
            self.rag.generate_answer,
            request.question,
        )
        cited = set(result.source_ids)

        evidence = [
            Evidence(
                citation_id=context["source_id"],
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
            if context["source_id"] in cited
        ]

        return AgentResult(
            answer=result.answer,
            agent="knowledge",
            evidence=evidence,
        )

    async def close(self) -> None:
        await asyncio.to_thread(self.rag.close)
