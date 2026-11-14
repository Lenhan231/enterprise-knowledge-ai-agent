"""HTTP client implementing the local retrieval-service contract."""

from __future__ import annotations

import os

from core.retrieval.retrieval import RetrievalRequest, RetrievalResponse
from core.services.client import post


class RemoteRetrievalService:
    def __init__(self, url: str | None = None) -> None:
        self.url = (url or os.getenv("RETRIEVAL_SERVICE_URL", "")).rstrip("/")
        if not self.url:
            raise ValueError("RETRIEVAL_SERVICE_URL is required")

    def retrieve(
        self,
        request: RetrievalRequest,
        company: str | None = None,
        roles: list[str] | None = None,
        method: str = "translated_hybrid_rerank",
        dense_weight: float = 1.0,
        bm25_weight: float = 2.0,
        rrf_k: int = 60,
        document_ids: list[str] | None = None,
        metadata_filter: dict | None = None,
        query_language: str = "auto",
        document_languages: dict[str, str] | None = None,
    ) -> RetrievalResponse:
        if not roles:
            raise PermissionError("Role-scoped retrieval requires verified document roles")
        payload = {
            "query": request.query,
            "top_k": request.top_k,
            "company": company,
            "roles": roles,
            "method": method,
            "dense_weight": dense_weight,
            "bm25_weight": bm25_weight,
            "rrf_k": rrf_k,
            "document_ids": document_ids,
            "metadata_filter": metadata_filter,
            "query_language": query_language,
            "document_languages": document_languages,
        }
        timeout = float(os.getenv("RETRIEVAL_SERVICE_TIMEOUT_SECONDS", "90"))
        result = post(self.url, "/retrieve", payload, timeout=timeout)
        return RetrievalResponse.model_validate(result)

    def close(self) -> None:
        return None
