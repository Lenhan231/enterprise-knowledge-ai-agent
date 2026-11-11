"""Dense vector ranking over the ACL-filtered eligible corpus."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.retrieval.methods.common import eligible_cte, fetch_ranked
from core.retrieval.retrieval import RetrievedChunk

if TYPE_CHECKING:
    from core.database.document_chunks_repository import DocumentChunkRepository


def search(
    repository: DocumentChunkRepository,
    query_embedding: list[float] | None,
    limit: int,
    *, query: str | None = None, company: str | None = None,
    roles: list[str] | None = None,
    document_ids: list[str] | None = None,
    metadata_filter: dict | None = None,
) -> list[RetrievedChunk]:
    eligible, parameters = eligible_cte(
        query_embedding, query, company, roles,
        include_vector=True, include_lexical=False, document_ids=document_ids,
        metadata_filter=metadata_filter,
    )
    parameters.extend((limit * 10, limit))
    sql = "WITH " + eligible + """,
        vector_candidates AS (
            SELECT id, similarity_score, vector_distance, year_match,
                   row_number() OVER (ORDER BY year_match DESC, vector_distance, id) AS candidate_rank
            FROM eligible
            ORDER BY year_match DESC, vector_distance, id
            LIMIT %s
        )
        SELECT e.document_name, e.chunk_index, e.content, e.metadata,
               v.similarity_score AS retrieval_score
        FROM vector_candidates AS v JOIN eligible AS e ON e.id = v.id
        ORDER BY v.candidate_rank
        LIMIT %s
    """
    return fetch_ranked(repository, sql, parameters)
