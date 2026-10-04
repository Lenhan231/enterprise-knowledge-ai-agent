"""Parent-context retrieval built from dense child ranks and ACL-filtered siblings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.retrieval.retrieval import RetrievalRequest, RetrievedChunk

if TYPE_CHECKING:
    from core.database.document_chunks_repository import DocumentChunkRepository


def search(
    repository: DocumentChunkRepository,
    query_embedding: list[float] | None,
    request: RetrievalRequest,
    *, company: str | None = None, roles: list[str] | None = None,
    metadata_filter: dict | None = None,
) -> tuple[list[RetrievedChunk], dict[tuple[str, int], dict]]:
    candidates = repository.similarity_search(
        query_embedding, min(request.top_k * 5, 100), query=request.query,
        company=company, roles=roles, metadata_filter=metadata_filter, method="dense",
    )
    contexts = repository.expand_parent_contexts(candidates, company=company, roles=roles)
    selected = []
    for chunk in candidates:
        context = contexts.get((chunk.document_id, chunk.chunk_index), {})
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
            prior_context = contexts.get((prior.document_id, prior.chunk_index), {})
            prior_indices = set(prior_context.get("chunk_indices", [prior.chunk_index]))
            overlap = len(indices & prior_indices) / min(len(indices), len(prior_indices))
            if overlap >= 0.6:
                duplicate = True
                break
        if not duplicate:
            selected.append(chunk)
        if len(selected) == request.top_k:
            break
    return selected, contexts
