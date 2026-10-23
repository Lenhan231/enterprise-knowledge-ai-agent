"""Embedding boundary shared by ingestion, chunking, and retrieval."""

from __future__ import annotations

import os
from functools import lru_cache
from threading import Lock

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from huggingface_hub import InferenceClient


load_dotenv()

from core.embeddings.settings import DEFAULT_EMBEDDING_MODEL, E5_MODEL, E5_REVISION

EMBEDDING_MAX_SEQUENCE_LENGTH = int(os.getenv("EMBEDDING_MAX_SEQUENCE_LENGTH", "512"))
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "local").strip().lower()
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
        vectors = self.client.feature_extraction(texts)
        return [[float(value) for value in vector] for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = self.client.feature_extraction(text)
        return [float(value) for value in vector]


@lru_cache(maxsize=2)
def _load_backend(model_name: str, backend_name: str = EMBEDDING_BACKEND) -> Embeddings:
    if backend_name == "local":
        from langchain_huggingface import HuggingFaceEmbeddings

        token = os.getenv("HUGGINGFACE_API_KEY")
        options = {"model_kwargs": {"token": token}} if token else {}
        if model_name == E5_MODEL:
            options.setdefault("model_kwargs", {})["revision"] = E5_REVISION
            options["encode_kwargs"] = {"normalize_embeddings": True}
        backend = HuggingFaceEmbeddings(model_name=model_name, **options)
        encoder = backend._client
        architecture_limit = getattr(encoder[0].auto_model.config, "max_position_embeddings", None)
        if EMBEDDING_MAX_SEQUENCE_LENGTH < 1 or (
            isinstance(architecture_limit, int) and EMBEDDING_MAX_SEQUENCE_LENGTH > architecture_limit
        ):
            raise ValueError("Configured embedding sequence length exceeds the model architecture limit")
        encoder.max_seq_length = EMBEDDING_MAX_SEQUENCE_LENGTH
        return backend
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
        self.max_sequence_length = EMBEDDING_MAX_SEQUENCE_LENGTH - (4 if model_name == E5_MODEL else 0)
        self.backend_name = backend_name
        self._backend = backend if backend is not None else _shared_backend(model_name, backend_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        inputs = ["passage: " + text for text in texts] if self.model_name == E5_MODEL else texts
        return self._normalize(self._backend.embed_documents(inputs))

    def embed_query(self, text: str) -> list[float]:
        text = "query: " + text if self.model_name == E5_MODEL else text
        return self._normalize([self._backend.embed_query(text)])[0]

    def _normalize(self, vectors):
        if self.model_name != E5_MODEL:
            return vectors
        import numpy as np
        if not vectors:
            return []
        values = np.asarray(vectors, dtype=np.float32)
        if values.ndim != 2 or values.shape[1] != 768 or not np.isfinite(values).all():
            raise ValueError("E5-base requires finite 768-dimensional vectors")
        norms = np.linalg.norm(values, axis=1, keepdims=True)
        if (norms == 0).any():
            raise ValueError("E5-base returned a zero vector")
        return (values / norms).tolist()
