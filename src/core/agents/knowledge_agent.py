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
from core.agents.execution import authorize
from core.agents.runtime import deadline, remaining, run_sync


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
            result = await run_sync(
                self.rag.generate_answer,
                request.question,
                decompose=multiquery,
                verify_claims=os.getenv("KNOWLEDGE_CLAIM_VERIFICATION_ENABLED", "0") == "1",
                _timeout=timeout,
                roles=sorted(request.identity.document_roles) if request.identity and request.identity.document_roles else None,
                retrieval_method=request.metadata.get("retrieval_method", "translated_hybrid_rerank"),
            )
        finally:
            deadline.reset(token)
        cited = set(result.source_ids)

        evidence = [
            Evidence(
                citation_id=context["source_id"],
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
            for context in result.contexts
            if context["source_id"] in cited
        ]

        metadata = {"ok": not result.insufficient_context, "insufficient_context": result.insufficient_context}
        if result.verification is not None:
            metadata["claim_verification"] = result.verification.model_dump()
            metadata["ok"] = metadata["ok"] and result.verification.status == "supported"

        return AgentResult(
            answer=result.answer,
            agent="knowledge",
            evidence=evidence,
            metadata=metadata,
        )

    async def close(self) -> None:
        await asyncio.to_thread(self.rag.close)
