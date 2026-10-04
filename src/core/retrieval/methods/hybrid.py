"""Dense + BM25 candidate ranking combined with reciprocal-rank fusion."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.retrieval.methods.bm25 import BM25_CTES
from core.retrieval.methods.common import eligible_cte, fetch_ranked, lexical_tsquery
from core.retrieval.retrieval import RetrievedChunk

if TYPE_CHECKING:
    from core.database.document_chunks_repository import DocumentChunkRepository


def search(
    repository: DocumentChunkRepository,
    query_embedding: list[float] | None,
    limit: int,
    *, query: str | None = None, company: str | None = None,
    roles: list[str] | None = None, metadata_filter: dict | None = None,
    dense_weight: float = 1.0,
    bm25_weight: float = 2.0, rrf_k: int = 60,
) -> list[RetrievedChunk]:
    eligible, parameters = eligible_cte(
        query_embedding, query, company, roles, metadata_filter=metadata_filter,
        include_vector=True, include_lexical=True,
    )
    parameters.append(lexical_tsquery(query))
    parameters.extend((limit * 10, limit * 10, dense_weight, rrf_k, bm25_weight, rrf_k, limit))
    sql = "WITH " + eligible + "," + BM25_CTES + """,
        vector_candidates AS (
            SELECT id, similarity_score, vector_distance, year_match,
                   row_number() OVER (ORDER BY year_match DESC, vector_distance, id) AS candidate_rank
            FROM eligible
            ORDER BY year_match DESC, vector_distance, id
            LIMIT %s
        ),
        bm25_candidates AS (
            SELECT id, bm25_score,
                   row_number() OVER (ORDER BY year_match DESC, bm25_score DESC, id) AS candidate_rank
            FROM bm25_scores
            ORDER BY year_match DESC, bm25_score DESC, id
            LIMIT %s
        ),
        combined AS (
            SELECT id, %s / (%s + candidate_rank) AS rrf_score FROM vector_candidates
            UNION ALL
            SELECT id, %s / (%s + candidate_rank) AS rrf_score FROM bm25_candidates
        ),
        ranked AS (
            SELECT id, sum(rrf_score) AS rrf_score FROM combined GROUP BY id
        )
        SELECT e.document_name, e.chunk_index, e.content, e.metadata,
               r.rrf_score AS retrieval_score
        FROM ranked AS r JOIN eligible AS e ON e.id = r.id
        ORDER BY r.rrf_score DESC, e.vector_distance, e.id
        LIMIT %s
    """
    return fetch_ranked(repository, sql, parameters)
