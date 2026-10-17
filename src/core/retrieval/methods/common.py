"""Shared PostgreSQL query pieces for retrieval methods."""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from core.retrieval.retrieval import RetrievedChunk

_SEARCH_STOP_WORDS = {
    "a", "an", "the", "what", "which", "who", "is", "are", "was", "were",
    "how", "many", "much", "of", "for", "in", "on", "at", "to", "and",
    "or", "with", "by", "from", "about", "please", "show", "me", "give",
    "tell", "của", "là", "năm", "bao", "nhiêu", "gì", "cho", "với",
    "được", "về", "thế", "nào", "summarize", "summary", "vinamilk", "s",
}


def lexical_tsquery(query: str | None) -> str:
    if not query:
        return ""
    terms = (word for word in re.findall(r"[\w]+", query.casefold()) if word not in _SEARCH_STOP_WORDS)
    return " | ".join(terms)


def explicit_fiscal_year(query: str | None) -> str | None:
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", query or ""))
    return next(iter(years)) if len(years) == 1 else None


def eligible_cte(
    query_embedding: list[float] | None,
    query: str | None,
    company: str | None,
    roles: list[str] | None,
    *,
    include_vector: bool,
    include_lexical: bool,
    document_ids: list[str] | None = None,
) -> tuple[str, list[Any]]:
    """Build the common ready-document and ACL filter before any ranking limit."""
    parameters: list[Any] = []
    vector_fields = ""
    if include_vector:
        if query_embedding is None:
            raise ValueError("query_embedding is required for dense retrieval")
        vector = np.asarray(query_embedding, dtype=np.float32)
        parameters.extend((vector, vector))
        vector_fields = """
            1 - (c.embedding <=> %s) AS similarity_score,
            c.embedding <=> %s AS vector_distance,
        """
    fiscal_year = explicit_fiscal_year(query)
    parameters.extend((fiscal_year, fiscal_year))
    filters = ""
    if company is not None:
        filters += " AND d.company = %s::text"
        parameters.append(company)
    if roles is not None:
        filters += " AND (d.allowed_roles && %s::text[] OR 'admin' = ANY(%s::text[]))"
        parameters.extend((roles, roles))
    if document_ids is not None:
        filters += " AND d.document_id = ANY(%s::text[])"
        parameters.append(document_ids)
    lexical_field = ", to_tsvector('simple', c.content) AS document_vector" if include_lexical else ""
    cte = f"""
        eligible AS MATERIALIZED (
            SELECT c.id, c.document_name, c.chunk_index, c.content,
                   c.metadata || jsonb_build_object('document_type', d.document_type) AS metadata,
                   {vector_fields}
                   coalesce(%s::text IS NOT NULL AND d.fiscal_year = %s, false) AS year_match
                   {lexical_field}
            FROM document_chunks AS c
            JOIN documents AS d ON d.document_id = c.metadata->>'document_id'
            WHERE coalesce(d.processing_status, 'ready') = 'ready' {filters}
        )
    """
    return cte, parameters


def fetch_ranked(repository, sql: str, parameters: list[Any]) -> list[RetrievedChunk]:
    with repository.conn.cursor() as cursor:
        cursor.execute(sql, parameters)
        rows = cursor.fetchall()
    return [
        RetrievedChunk(
            document_name=name,
            chunk_index=index,
            content=content,
            metadata={} if metadata is None else metadata,
            retrieval_score=score,
        )
        for name, index, content, metadata, score in rows
    ]
