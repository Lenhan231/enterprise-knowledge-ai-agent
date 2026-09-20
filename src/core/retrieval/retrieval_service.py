"""Retrieve ranked knowledge chunks for a natural-language question."""

from __future__ import annotations

from core.database.document_chunks_repository import VectorRepository
from core.embeddings import EmbeddingService


class RetrievalService:
    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        repository: VectorRepository | None = None,
    ) -> None:
        self.embedding_service = embedding_service or EmbeddingService()
        self.repository = repository or VectorRepository()

    def retrieve(self, question: str, limit: int = 5) -> dict:
        query_embedding = self.embedding_service.embed_query(question)
        results = self.repository.similarity_search(query_embedding, limit)
        contexts = [
            {
                "document_name": result[0],
                "chunk_index": result[1],
                "content": result[2],
                "metadata": result[3],
                "similarity_score": float(result[4]),
            }
            for result in results
        ]
        return {"question": question, "contexts": contexts}

    def close(self) -> None:
        self.repository.close()
