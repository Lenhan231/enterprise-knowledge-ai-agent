"""Shared retrieval dispatch, embedding lifecycle, and ranked-result mapping."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Literal

from core.database.document_chunks_repository import DocumentChunkRepository
from core.embeddings import EmbeddingService
from core.retrieval.methods import parent, translated_hybrid
from core.retrieval.retrieval import (
    RankedChunk, RetrievalRequest, RetrievalResponse, SourceLocation, make_chunk_id,
)

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        repository: DocumentChunkRepository | None = None,
        query_translator=None,
        reranker=None,
    ) -> None:
        self.embedding_service = embedding_service
        self.repository = repository or DocumentChunkRepository()
        self.reranker = reranker
        self.query_translator = query_translator
        self._translation_llm = None

    def _get_translator(self):
        if self.query_translator is None:
            from core.llm.groq_provider import GroqProvider
            from core.retrieval.query_translator import QueryTranslator
            self._translation_llm = GroqProvider()
            self.query_translator = QueryTranslator(self._translation_llm)
        return self.query_translator

    def retrieve(
        self, request: RetrievalRequest, company: str | None = None,
        roles: list[str] | None = None,
        metadata_filter: dict | None = None,
        method: Literal["dense", "bm25", "hybrid", "parent", "translated_hybrid", "translated_hybrid_rerank"] = "hybrid",
        dense_weight: float = 1.0, bm25_weight: float = 2.0, rrf_k: int = 60,
        document_ids: list[str] | None = None,
        query_language: str = "auto",
        document_languages: dict[str, str] | None = None,
    ) -> RetrievalResponse:
        """Run one selected retrieval method and map its chunks to the public contract."""
        if not isinstance(request, RetrievalRequest):
            raise TypeError("request must be a RetrievalRequest")
        if method not in {"dense", "bm25", "hybrid", "parent", "translated_hybrid", "translated_hybrid_rerank"}:
            raise ValueError("method must be dense, bm25, hybrid, parent, translated_hybrid, or translated_hybrid_rerank")
        started = perf_counter()
        query_embedding = None
        effective_method = method
        if method != "bm25":
            try:
                if self.embedding_service is None:
                    self.embedding_service = EmbeddingService()
                query_embedding = self.embedding_service.embed_query(request.query)
            except Exception as exc:
                if method != "hybrid":
                    raise
                effective_method = "bm25"
                logger.warning(
                    "Hybrid retrieval embedding failed; falling back to BM25 (%s)",
                    type(exc).__name__,
                )

        options = {"company": company, "roles": roles}
        if metadata_filter:
            options["metadata_filter"] = metadata_filter
        if document_ids is not None:
            if not isinstance(document_ids, list) or any(
                not isinstance(value, str) or not value.strip() for value in document_ids
            ):
                raise ValueError("document_ids must be a list of non-empty document IDs")
            options["document_ids"] = document_ids
        parent_contexts = {}
        retrieval_details = {}
        if method in {"translated_hybrid", "translated_hybrid_rerank"}:
            candidate_request = (request.model_copy(update={"top_k": max(30, request.top_k)})
                                 if method == "translated_hybrid_rerank" else request)
            chunks, retrieval_details = translated_hybrid.search(
                self.repository, query_embedding, candidate_request, self._get_translator,
                query_language=query_language, document_languages=document_languages,
                dense_weight=dense_weight, bm25_weight=bm25_weight, rrf_k=rrf_k, **options,
            )
        elif effective_method == "parent":
            chunks, parent_contexts = parent.search(
                self.repository, query_embedding, request, **options,
            )
        else:
            fusion_options = (
                {"dense_weight": dense_weight, "bm25_weight": bm25_weight, "rrf_k": rrf_k}
                if effective_method == "hybrid" else {}
            )
            chunks = self.repository.similarity_search(
                query_embedding, request.top_k, query=request.query, method=effective_method,
                **fusion_options, **options,
            )

        if method == "translated_hybrid_rerank":
            if self.reranker is None:
                from core.retrieval.reranker import BGEReranker
                self.reranker = BGEReranker()
            retrieval_details["candidate_method"] = retrieval_details["effective_method"]
            chunks, rerank_details = self.reranker.rerank(request.query, chunks, request.top_k)
            retrieval_details.update(rerank_details)
            retrieval_details["effective_method"] = (
                "dense_rerank" if retrieval_details.get("dense_fallback") else method)
            retrieval_details["embedding_model"] = getattr(self.embedding_service, "model_name", None)

        results = []
        for rank, chunk in enumerate(chunks, start=1):
            context = parent_contexts.get((chunk.document_id, chunk.chunk_index), {})
            metadata = dict(chunk.metadata)
            if effective_method == "parent":
                indices = context.get("chunk_indices", [chunk.chunk_index])
                metadata.update({
                    "parent_id": f"{chunk.document_id}::parent::{indices[0]}-{indices[-1]}",
                    "parent_chunk_indices": indices,
                    "parent_chunk_count": context.get("parent_chunk_count", len(indices)),
                    "parent_context_type": context.get("parent_context_type", "page_window"),
                })
            results.append(RankedChunk(
                rank=rank,
                chunk_id=make_chunk_id(chunk.document_id, chunk.chunk_index),
                document_id=chunk.document_id,
                text=context.get("text", chunk.content),
                score=chunk.retrieval_score,
                source=chunk.document_name,
                location=SourceLocation(
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.metadata.get("page_number"),
                    section_title=chunk.metadata.get("section_title"),
                ),
                metadata=metadata,
                retrieval_method=effective_method,
            ))
        return RetrievalResponse(
            query=request.query,
            latency_ms=(perf_counter() - started) * 1000,
            results=results,
            retrieval_details=retrieval_details,
            method=effective_method,
        )

    def close(self) -> None:
        try:
            self.repository.close()
        finally:
            if self._translation_llm is not None:
                self._translation_llm.close()
