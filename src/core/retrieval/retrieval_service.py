"""Retrieve ranked knowledge chunks for a natural-language question."""

from __future__ import annotations

from core.database.document_chunks_repository import DocumentChunkRepository
from time import perf_counter
from core.embeddings import EmbeddingService
from core.models.retrieval import (
    RankedChunk, RetrievalRequest, RetrievalResponse, SourceLocation, make_chunk_id,
)


class RetrievalService:
    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        repository: DocumentChunkRepository | None = None,
    ) -> None:
        self.embedding_service = embedding_service or EmbeddingService()
        self.repository = repository or DocumentChunkRepository()

    def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        """Rank typed chunks in repository order (cosine distance, then row ID).

        Latency includes embedding, search and result mapping. Query text is
        passed through unchanged; no legacy tuple or dictionary adapter is used.
        """
        if not isinstance(request, RetrievalRequest):
            raise TypeError("request must be a RetrievalRequest")
        started = perf_counter()
        query_embedding = self.embedding_service.embed_query(request.query)
        chunks = self.repository.similarity_search(query_embedding, request.top_k)
        results = [
            RankedChunk(
                rank=rank,
                chunk_id=make_chunk_id(chunk.document_id, chunk.chunk_index),
                document_id=chunk.document_id,
                text=chunk.content,
                score=chunk.similarity_score,
                source=chunk.document_name,
                location=SourceLocation(
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.metadata.get("page_number"),
                    section_title=chunk.metadata.get("section_title"),
                ),
                metadata=chunk.metadata,
            )
            for rank, chunk in enumerate(chunks, start=1)
        ]
        return RetrievalResponse(
            query=request.query,
            latency_ms=(perf_counter() - started) * 1000,
            results=results,
        )

    def close(self) -> None:
        self.repository.close()
