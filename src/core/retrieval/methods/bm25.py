"""BM25 lexical ranking with query-term cleanup and corpus-local statistics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.retrieval.methods.common import eligible_cte, fetch_ranked, lexical_tsquery
from core.retrieval.retrieval import RetrievedChunk

if TYPE_CHECKING:
    from core.database.document_chunks_repository import DocumentChunkRepository

BM25_CTES = """
    query_terms AS (
        SELECT lexeme
        FROM unnest(to_tsvector('simple', %s)) AS terms(lexeme, positions, weights)
    ),
    document_terms AS MATERIALIZED (
        SELECT e.id, term.lexeme,
               cardinality(term.positions)::double precision AS term_frequency
        FROM eligible AS e
        CROSS JOIN LATERAL unnest(e.document_vector) AS term(lexeme, positions, weights)
    ),
    document_lengths AS (
        SELECT id, sum(term_frequency) AS document_length
        FROM document_terms GROUP BY id
    ),
    corpus_stats AS (
        SELECT count(*)::double precision AS document_count,
               coalesce(avg(coalesce(dl.document_length, 0)), 0)::double precision AS average_document_length
        FROM eligible AS e LEFT JOIN document_lengths AS dl ON dl.id = e.id
    ),
    document_frequencies AS (
        SELECT lexeme, count(*)::double precision AS document_frequency
        FROM document_terms
        WHERE lexeme IN (SELECT lexeme FROM query_terms)
        GROUP BY lexeme
    ),
    query_document_terms AS (
        SELECT dt.id, dt.lexeme, sum(dt.term_frequency) AS term_frequency,
               dl.document_length
        FROM document_terms AS dt
        JOIN query_terms AS qt ON qt.lexeme = dt.lexeme
        JOIN document_lengths AS dl ON dl.id = dt.id
        GROUP BY dt.id, dt.lexeme, dl.document_length
    ),
    bm25_scores AS (
        SELECT dt.id, e.year_match,
               sum(
                   ln(1.0 + (cs.document_count - df.document_frequency + 0.5)
                       / (df.document_frequency + 0.5))
                   * (dt.term_frequency * 2.2)
                   / (dt.term_frequency + 1.2 * (
                       0.25 + 0.75 * dt.document_length
                           / nullif(cs.average_document_length, 0)
                   ))
               ) AS bm25_score
        FROM query_document_terms AS dt
        JOIN document_frequencies AS df ON df.lexeme = dt.lexeme
        JOIN eligible AS e ON e.id = dt.id
        CROSS JOIN corpus_stats AS cs
        GROUP BY dt.id, e.year_match
    )
"""



def search(
    repository: DocumentChunkRepository,
    limit: int,
    *, query: str | None = None, company: str | None = None,
    roles: list[str] | None = None, metadata_filter: dict | None = None,
    document_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    eligible, parameters = eligible_cte(
        None, query, company, roles, metadata_filter=metadata_filter,
        include_vector=False, include_lexical=True, document_ids=document_ids,
    )
    parameters.extend((lexical_tsquery(query), limit * 10, limit))
    sql = "WITH " + eligible + "," + BM25_CTES + """,
        bm25_candidates AS (
            SELECT id, bm25_score,
                   row_number() OVER (ORDER BY year_match DESC, bm25_score DESC, id) AS candidate_rank
            FROM bm25_scores
            ORDER BY year_match DESC, bm25_score DESC, id
            LIMIT %s
        )
        SELECT e.document_name, e.chunk_index, e.content, e.metadata,
               b.bm25_score AS retrieval_score
        FROM bm25_candidates AS b JOIN eligible AS e ON e.id = b.id
        ORDER BY b.candidate_rank
        LIMIT %s
    """
    return fetch_ranked(repository, sql, parameters)
