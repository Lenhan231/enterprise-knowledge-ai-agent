"""Embedding boundary shared by ingestion, chunking, and retrieval."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings


load_dotenv()

DEFAULT_EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)


class EmbeddingService(Embeddings):
    """Expose one embedding model through the LangChain Embeddings contract."""

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        backend: Embeddings | None = None,
    ) -> None:
        self.model_name = model_name
        self._backend = backend or HuggingFaceEmbeddings(model_name=model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._backend.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._backend.embed_query(text)
