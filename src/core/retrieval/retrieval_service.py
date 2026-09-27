"""Retrieve ranked knowledge chunks for a natural-language question."""

from __future__ import annotations

from typing import Literal

from core.database.document_chunks_repository import DocumentChunkRepository
from time import perf_counter
from core.embeddings import EmbeddingService
from core.retrieval.retrieval import (
    RankedChunk, RetrievalRequest, RetrievalResponse, SourceLocation, make_chunk_id,
)


class RetrievalService:
    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        repository: DocumentChunkRepository | None = None,
    ) -> None:
        self.embedding_service = embedding_service
        self.repository = repository or DocumentChunkRepository()

    def retrieve(
        self, request: RetrievalRequest, company: str | None = None,
        roles: list[str] | None = None,
        method: Literal["dense", "bm25", "hybrid", "parent"] = "hybrid",
        dense_weight: float = 1.0, bm25_weight: float = 2.0, rrf_k: int = 60,
    ) -> RetrievalResponse:
        """Rank typed chunks using dense and lexical repository candidates.

        Latency includes embedding, search and result mapping. Query text is
        passed through unchanged; no legacy tuple or dictionary adapter is used.
        """
        if not isinstance(request, RetrievalRequest):
            raise TypeError("request must be a RetrievalRequest")
        if method not in {"dense", "bm25", "hybrid", "parent"}:
            raise ValueError("method must be dense, bm25, hybrid, or parent")
        started = perf_counter()
        query_embedding = None
        if method != "bm25":
            if self.embedding_service is None:
                self.embedding_service = EmbeddingService()
            query_embedding = self.embedding_service.embed_query(request.query)
        search_method = "dense" if method == "parent" else method
        search_limit = min(request.top_k * 5, 100) if method == "parent" else request.top_k
        fusion_options = (
            {"dense_weight": dense_weight, "bm25_weight": bm25_weight, "rrf_k": rrf_k}
            if search_method == "hybrid" else {}
        )
        if company is None and roles is None:
            chunks = self.repository.similarity_search(
                query_embedding, search_limit, query=request.query, method=search_method,
                **fusion_options,
            )
        else:
            filters = {"roles": roles}
            if company is not None:
                filters["company"] = company
            chunks = self.repository.similarity_search(
                query_embedding, search_limit, query=request.query, method=search_method,
                **fusion_options, **filters
            )
        parent_contexts = (
            self.repository.expand_parent_contexts(chunks, company=company, roles=roles)
            if method == "parent" else {}
        )
        if method == "parent":
            selected = []
            for chunk in chunks:
                context = parent_contexts.get((chunk.document_id, chunk.chunk_index), {})
                indices = set(context.get("chunk_indices", [chunk.chunk_index]))
                title = chunk.metadata.get("section_title")
                page = chunk.metadata.get("page_number") if not title else None
                duplicate = False
                for prior in selected:
                    if prior.document_id != chunk.document_id:
                        continue
                    prior_title = prior.metadata.get("section_title")
                    prior_page = prior.metadata.get("page_number") if not prior_title else None
                    if (prior_title, prior_page) != (title, page):
                        continue
                    prior_context = parent_contexts.get((prior.document_id, prior.chunk_index), {})
                    prior_indices = set(prior_context.get("chunk_indices", [prior.chunk_index]))
                    overlap = len(indices & prior_indices) / min(len(indices), len(prior_indices))
                    if overlap >= 0.6:
                        duplicate = True
                        break
                if not duplicate:
                    selected.append(chunk)
                if len(selected) == request.top_k:
                    break
            chunks = selected
        results = [
            RankedChunk(
                rank=rank,
                chunk_id=make_chunk_id(chunk.document_id, chunk.chunk_index),
                document_id=chunk.document_id,
                text=parent_contexts.get(
                    (chunk.document_id, chunk.chunk_index), {}
                ).get("text", chunk.content),
                score=chunk.retrieval_score,
                source=chunk.document_name,
                location=SourceLocation(
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.metadata.get("page_number"),
                    section_title=chunk.metadata.get("section_title"),
                ),
                metadata={
                    **chunk.metadata,
                    **({
                        "parent_id": (
                            f"{chunk.document_id}::parent::"
                            f"{parent_contexts[(chunk.document_id, chunk.chunk_index)]['chunk_indices'][0]}-"
                            f"{parent_contexts[(chunk.document_id, chunk.chunk_index)]['chunk_indices'][-1]}"
                        ),
                        "parent_chunk_indices": parent_contexts[(chunk.document_id, chunk.chunk_index)]["chunk_indices"],
                        "parent_chunk_count": parent_contexts[(chunk.document_id, chunk.chunk_index)]["parent_chunk_count"],
                        "parent_context_type": parent_contexts[(chunk.document_id, chunk.chunk_index)]["parent_context_type"],
                    } if method == "parent" else {})
                },
                retrieval_method=method,
            )
            for rank, chunk in enumerate(chunks, start=1)
        ]
        return RetrievalResponse(
            query=request.query,
            latency_ms=(perf_counter() - started) * 1000,
            results=results,
            method=method,
        )

    def close(self) -> None:
        self.repository.close()
