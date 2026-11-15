"""Authenticated public proxy to the private retrieval service."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.security import require_permission

router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])


class RetrievalProxyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=100)
    method: Literal["dense", "bm25", "hybrid", "parent", "translated_hybrid", "translated_hybrid_rerank"] = "translated_hybrid_rerank"
    dense_weight: float = Field(default=1.0, ge=0)
    bm25_weight: float = Field(default=2.0, ge=0)
    rrf_k: int = Field(default=60, ge=1)
    document_ids: list[str] | None = Field(default=None, max_length=500)
    metadata_filter: dict | None = None
    query_language: Literal["auto", "en", "vn"] = "auto"
    document_languages: dict[str, str] | None = None


@router.post("/retrieve")
def retrieve(payload: RetrievalProxyRequest, user: dict = Depends(require_permission("ask_documents"))):
    """Forward a search using only the document role verified from this session."""
    from core.retrieval.remote_service import RemoteRetrievalService
    from core.retrieval.retrieval import RetrievalRequest

    result = RemoteRetrievalService().retrieve(
        RetrievalRequest(query=payload.query, top_k=payload.top_k),
        roles=[user["role"]],
        method=payload.method,
        dense_weight=payload.dense_weight,
        bm25_weight=payload.bm25_weight,
        rrf_k=payload.rrf_k,
        document_ids=payload.document_ids,
        metadata_filter=payload.metadata_filter,
        query_language=payload.query_language,
        document_languages=payload.document_languages,
    )
    return result.model_dump(mode="json")
