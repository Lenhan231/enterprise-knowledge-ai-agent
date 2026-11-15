import asyncio
import os
import time

from core.agents.base import BaseAgent
from core.models.agents import (
    AgentRequest,
    AgentResult,
    Evidence,
)
from core.rag.rag_service import RAGService
from core.agents.orchestration.execution import authorize
from core.agents.runtime import deadline, remaining, run_sync
from core.prompts.Knowledge import INSUFFICIENT_ANSWER, NO_MATCHING_DOCUMENTS_ANSWER


class KnowledgeAgent(BaseAgent):
    def __init__(
        self,
        rag_service: RAGService | None = None,
    ):
        self.rag = rag_service or RAGService()

    async def retrieve(self, request: AgentRequest) -> list[Evidence]:
        """Raw, role-scoped evidence for reports; no answer-model filtering."""
        identity = request.identity
        if identity is None or "documents:read" not in identity.permissions or not identity.document_roles:
            raise PermissionError("Verified document scope is required")
        contexts = await run_sync(
            self.rag.retrieve_contexts, request.question, limit=5,
            roles=sorted(identity.document_roles),
            retrieval_method=request.metadata.get("retrieval_method", "translated_hybrid_rerank"),
        )
        return [Evidence(source_type="document", source=item["document_name"],
                         content=item["content"], metadata={**item["metadata"],
                         "chunk_id": item.get("chunk_id"), "chunk_index": item["chunk_index"]})
                for item in contexts]

    async def run(
        self,
        request: AgentRequest,
    ) -> AgentResult:
        authorize(request, 'knowledge')
        multiquery = os.getenv("KNOWLEDGE_MULTIQUERY_ENABLED", "0") == "1"
        timeout = 90.0 if multiquery else 60.0
        token = deadline.set(time.monotonic() + remaining(timeout))
        try:
            contexts, insufficient_context = await run_sync(
                self.rag.retrieve_for_answer,
                request.question,
                decompose=multiquery,
                _timeout=timeout,
                roles=sorted(request.identity.document_roles) if request.identity and request.identity.document_roles else None,
                retrieval_method=request.metadata.get("retrieval_method", "translated_hybrid_rerank"),
            )
        finally:
            deadline.reset(token)
        evidence = [
            Evidence(
                citation_id=f"S{index}",
                source_type="document",
                source=context["document_name"],
                content=context["content"],
                metadata={
                    **context["metadata"],
                    "chunk_index": context["chunk_index"],
                    "similarity_score": (
                        context["similarity_score"]
                    ),
                    "retrieval_method": context.get("retrieval_method", "translated_hybrid_rerank"),
                    "retrieval_details": context.get("retrieval_details", {}),
                },
            )
            for index, context in enumerate(contexts, start=1)
        ]

        metadata = {"ok": not insufficient_context and bool(contexts),
                    "insufficient_context": insufficient_context or not contexts}
        if contexts:
            details = contexts[0].get("retrieval_details") or {}
            metadata["search"] = {
                "lexical_queries": details.get("lexical_queries"),
                "candidate_count": details.get("reranker_candidate_count"),
                "passages_to_model": len(contexts),
                "reranker_model": details.get("reranker_model"),
                "context_radius": details.get("context_radius", 0),
            }
        return AgentResult(
            answer=(INSUFFICIENT_ANSWER if insufficient_context else NO_MATCHING_DOCUMENTS_ANSWER) if not contexts or insufficient_context else "",
            agent="knowledge",
            evidence=evidence,
            metadata=metadata,
        )

    async def close(self) -> None:
        await asyncio.to_thread(self.rag.close)
