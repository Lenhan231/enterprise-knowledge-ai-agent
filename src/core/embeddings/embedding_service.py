"""Embedding boundary shared by ingestion, chunking, and retrieval."""

from __future__ import annotations

import os
from functools import lru_cache
from threading import Lock

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from huggingface_hub import InferenceClient


load_dotenv()

DEFAULT_EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
EMBEDDING_MAX_SEQUENCE_LENGTH = int(os.getenv("EMBEDDING_MAX_SEQUENCE_LENGTH", "512"))
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "local").strip().lower()
HUGGINGFACE_EMBEDDING_BATCH_SIZE = 16
_BACKEND_LOAD_LOCK = Lock()


class HuggingFaceInferenceEmbeddings(Embeddings):
    """Use Hugging Face hosted feature extraction without loading model weights locally."""

    def __init__(self, model_name: str) -> None:
        token = os.getenv("HUGGINGFACE_API_KEY")
        if not token:
            raise ValueError("HUGGINGFACE_API_KEY is required for the Hugging Face backend")
        self.client = InferenceClient(model=model_name, token=token)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = []
        for start in range(0, len(texts), HUGGINGFACE_EMBEDDING_BATCH_SIZE):
            batch = texts[start:start + HUGGINGFACE_EMBEDDING_BATCH_SIZE]
            batch_vectors = self.client.feature_extraction(batch)
            vectors.extend([[float(value) for value in vector] for vector in batch_vectors])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vector = self.client.feature_extraction(text)
        return [float(value) for value in vector]


@lru_cache(maxsize=2)
def _load_backend(model_name: str, backend_name: str = EMBEDDING_BACKEND) -> Embeddings:
    if backend_name == "local":
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name=model_name)
    if backend_name == "huggingface_inference":
        return HuggingFaceInferenceEmbeddings(model_name=model_name)
    raise ValueError(f"Unsupported EMBEDDING_BACKEND: {backend_name}")


def _shared_backend(model_name: str, backend_name: str = EMBEDDING_BACKEND) -> Embeddings:
    # Serialize first load so concurrent requests do not initialize duplicate models.
    with _BACKEND_LOAD_LOCK:
        return _load_backend(model_name, backend_name)


class EmbeddingService(Embeddings):
    """Expose one embedding model through the LangChain Embeddings contract."""

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        backend: Embeddings | None = None,
        backend_name: str = EMBEDDING_BACKEND,
    ) -> None:
        self.model_name = model_name
        self.max_sequence_length = EMBEDDING_MAX_SEQUENCE_LENGTH
        self.backend_name = backend_name
        self._backend = backend if backend is not None else _shared_backend(model_name, backend_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._backend.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._backend.embed_query(text)
