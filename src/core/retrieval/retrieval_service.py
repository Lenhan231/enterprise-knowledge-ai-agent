"""Shared retrieval dispatch, embedding lifecycle, and ranked-result mapping."""

from __future__ import annotations

from time import perf_counter
from typing import Literal

from core.database.document_chunks_repository import DocumentChunkRepository
from core.embeddings import EmbeddingService
from core.retrieval.methods import parent
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
        document_ids: list[str] | None = None,
    ) -> RetrievalResponse:
        """Run one selected retrieval method and map its chunks to the public contract."""
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

        options = {"company": company, "roles": roles}
        if document_ids is not None:
            if not isinstance(document_ids, list) or any(
                not isinstance(value, str) or not value.strip() for value in document_ids
            ):
                raise ValueError("document_ids must be a list of non-empty document IDs")
            options["document_ids"] = document_ids
        parent_contexts = {}
        if method == "parent":
            chunks, parent_contexts = parent.search(
                self.repository, query_embedding, request, **options,
            )
        else:
            fusion_options = (
                {"dense_weight": dense_weight, "bm25_weight": bm25_weight, "rrf_k": rrf_k}
                if method == "hybrid" else {}
            )
            chunks = self.repository.similarity_search(
                query_embedding, request.top_k, query=request.query, method=method,
                **fusion_options, **options,
            )

        results = []
        for rank, chunk in enumerate(chunks, start=1):
            context = parent_contexts.get((chunk.document_id, chunk.chunk_index), {})
            metadata = dict(chunk.metadata)
            if method == "parent":
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
                retrieval_method=method,
            ))
        return RetrievalResponse(
            query=request.query,
            latency_ms=(perf_counter() - started) * 1000,
            results=results,
            method=method,
        )

    def close(self) -> None:
        self.repository.close()
