import os
import re
from typing import Literal
from psycopg.types.json import Jsonb

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
import numpy as np

from core.database.connection_limit import close_database_connection, connect_database
from core.retrieval.retrieval import RetrievedChunk

load_dotenv()

_SEARCH_STOP_WORDS = {
    "a", "an", "the", "what", "which", "who", "is", "are", "was", "were",
    "how", "many", "much", "of", "for", "in", "on", "at", "to", "and",
    "or", "with", "by", "from", "about", "please", "show", "me", "give",
    "tell", "của", "là", "năm", "bao", "nhiêu", "gì", "cho", "với",
    "được", "về", "thế", "nào", "summarize", "summary", "vinamilk", "s",
}


def _lexical_tsquery(query: str | None) -> str:
    """Drop question scaffolding so lexical ranking emphasizes domain terms."""
    if not query:
        return ""
    terms = (word for word in re.findall(r"[\w]+", query.casefold()) if word not in _SEARCH_STOP_WORDS)
    return " | ".join(terms)


def _explicit_fiscal_year(query: str | None) -> str | None:
    """Return a year only when the question names one unambiguous year."""
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", query or ""))
    return next(iter(years)) if len(years) == 1 else None


class DocumentChunkRepository:
    def __init__(self):
        DATABASE_URL = os.getenv("DATABASE_URL")
        if DATABASE_URL is None:
            raise ValueError("DATABASE_URL is not set")
        self.DATABASE_URL = DATABASE_URL
        self.conn = connect_database(self.DATABASE_URL)
        try:
            register_vector(self.conn)
        except BaseException:
            close_database_connection(self.conn)
            raise
        

    def insert_chunk(
        self,
        document_name:str,
        chunk_index:int,
        content:str,
        metadata:dict,
        embedding:list[float]
    ):
        """
        Save a semantic chunk and its embedding to Supabase PostgreSQL.

        Args:
            document_name: Name of the source document.
            chunk_index: Position of the chunk within the document.
            content: Text content of the chunk.
            metadata: Additional chunk metadata stored as JSON.
            embedding: Vector representation of the chunk content.
        """
    
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO document_chunks (
                    document_name,
                    chunk_index,
                    content,
                    metadata,
                    embedding
                )
                VALUES (%s, %s, %s, %s, %s)
                """,(
                    document_name,
                    chunk_index,
                    content,
                    Jsonb(metadata),
                    embedding
                )
            )
            self.conn.commit()

    def replace_document(self, document_name: str, chunks: list[tuple]) -> None:
        """Atomically replace all chunks belonging to one source document."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM document_chunks WHERE document_name = %s",
                (document_name,),
            )
            cur.executemany(
                """
                INSERT INTO document_chunks (
                    document_name, chunk_index, content, metadata, embedding
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (name, index, content, Jsonb(metadata), embedding)
                    for name, index, content, metadata, embedding in chunks
                ],
            )

    def close(self) -> None:
        close_database_connection(self.conn)

    def expand_parent_contexts(
        self,
        chunks: list[RetrievedChunk],
        company: str | None = None,
        roles: list[str] | None = None,
        radius: int = 2,
    ) -> dict[tuple[str, int], dict]:
        """Expand candidate children with nearby chunks from their section/page.

        Authorization is repeated here: parent expansion must not fetch siblings
        that the current role could not retrieve as a first-stage candidate.
        """
        if not chunks:
            return {}
        if radius < 0 or radius > 10:
            raise ValueError("radius must be between 0 and 10")

        anchors = [
            {
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "section_title": chunk.metadata.get("section_title") or None,
                "page_number": (
                    str(chunk.metadata["page_number"])
                    if chunk.metadata.get("page_number") is not None else None
                ),
            }
            for chunk in chunks
        ]
        filters = []
        parameters = [Jsonb(anchors), radius, radius]
        if company is not None:
            filters.append("d.company = %s::text")
            parameters.append(company)
        if roles is not None:
            filters.append("(d.allowed_roles && %s::text[] OR 'admin' = ANY(%s::text[]))")
            parameters.extend((roles, roles))
        filter_sql = " AND " + " AND ".join(filters) if filters else ""

        query = f"""
            WITH anchors AS (
                SELECT *
                FROM jsonb_to_recordset(%s::jsonb) AS a(
                    document_id text, chunk_index integer,
                    section_title text, page_number text
                )
            )
            SELECT a.document_id, a.chunk_index AS anchor_index,
                   c.chunk_index, c.content
            FROM anchors AS a
            JOIN public.documents AS d ON d.document_id = a.document_id
            JOIN public.document_chunks AS c
              ON c.metadata->>'document_id' = a.document_id
             AND c.chunk_index BETWEEN a.chunk_index - %s AND a.chunk_index + %s
             AND c.metadata->>'section_title' IS NOT DISTINCT FROM a.section_title
             AND c.metadata->>'page_number' IS NOT DISTINCT FROM a.page_number
            WHERE coalesce(d.processing_status, 'ready') = 'ready'{filter_sql}
            ORDER BY a.document_id, a.chunk_index, c.chunk_index
        """
        with self.conn.cursor() as cursor:
            cursor.execute(query, parameters)
            rows = cursor.fetchall()

        grouped: dict[tuple[str, int], list[tuple[int, str]]] = {}
        for document_id, anchor_index, chunk_index, content in rows:
            grouped.setdefault((document_id, anchor_index), []).append((chunk_index, content))

        contexts = {}
        for chunk in chunks:
            key = (chunk.document_id, chunk.chunk_index)
            siblings = grouped.get(key, [(chunk.chunk_index, chunk.content)])
            contexts[key] = {
                "text": "\n".join(content for _, content in siblings),
                "chunk_indices": [index for index, _ in siblings],
                "parent_chunk_count": len(siblings),
                "parent_context_type": "section_window" if chunk.metadata.get("section_title") else "page_window",
            }
        return contexts

    def similarity_search(
        self, query_embedding: list[float] | None, limit: int, company: str | None = None,
        roles: list[str] | None = None, query: str | None = None,
        method: Literal["dense", "bm25", "hybrid"] = "hybrid",
        dense_weight: float = 1.0, bm25_weight: float = 2.0, rrf_k: int = 60,
    ) -> list[RetrievedChunk]:
        """Return full chunks ranked with dense, BM25, or hybrid retrieval.

        Map database rows at this boundary. Missing metadata.document_id raises
        a validation error, including when SQL NULL metadata becomes {}.
        """
        if method not in {"dense", "bm25", "hybrid"}:
            raise ValueError("method must be dense, bm25, or hybrid")
        if method != "bm25" and query_embedding is None:
            raise ValueError("query_embedding is required for dense and hybrid retrieval")
        if dense_weight <= 0 or bm25_weight <= 0 or rrf_k < 0:
            raise ValueError("hybrid weights must be positive and rrf_k must be non-negative")
        query_vector = np.array(query_embedding, dtype=np.float32) if query_embedding is not None else None
        lexical_query = _lexical_tsquery(query)
        fiscal_year = _explicit_fiscal_year(query)
        with self.conn.cursor() as cur:
            filters = ""
            parameters = []
            if method != "bm25":
                parameters.extend((query_vector, query_vector))
            parameters.extend((fiscal_year, fiscal_year))
            if company is not None:
                filters += " AND d.company = %s::text"
                parameters.append(company)
            if roles is not None:
                filters += " AND (d.allowed_roles && %s::text[] OR 'admin' = ANY(%s::text[]))"
                parameters.extend((roles, roles))
            eligible_vector = ""
            if method != "bm25":
                eligible_vector = """
                    1 - (c.embedding <=> %s) AS similarity_score,
                    c.embedding <=> %s AS vector_distance,
                """
            bm25_eligible = ", to_tsvector('simple', c.content) AS document_vector" if method != "dense" else ""
            ctes = [f"""
                eligible AS MATERIALIZED (
                    SELECT c.id, c.document_name, c.chunk_index, c.content,
                           c.metadata || jsonb_build_object('document_type', d.document_type) AS metadata,
                           {eligible_vector}
                           coalesce(%s::text IS NOT NULL AND d.fiscal_year = %s, false) AS year_match
                           {bm25_eligible}
                    FROM document_chunks AS c
                    JOIN documents AS d ON d.document_id = c.metadata->>'document_id'
                    WHERE coalesce(d.processing_status, 'ready') = 'ready' {filters}
                )
            """]
            if method != "dense":
                ctes.extend(("""
                    query_terms AS (
                        SELECT lexeme
                        FROM unnest(to_tsvector('simple', %s)) AS terms(lexeme, positions, weights)
                    )
                """, """
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
                """))
            if method != "bm25":
                ctes.append("""
                    vector_candidates AS (
                        SELECT id, similarity_score, vector_distance, year_match,
                               row_number() OVER (ORDER BY year_match DESC, vector_distance, id) AS candidate_rank
                        FROM eligible
                        ORDER BY year_match DESC, vector_distance, id
                        LIMIT %s
                    )
                """)
            if method != "dense":
                ctes.append("""
                    bm25_candidates AS (
                        SELECT id, bm25_score,
                               row_number() OVER (ORDER BY year_match DESC, bm25_score DESC, id) AS candidate_rank
                        FROM bm25_scores
                        ORDER BY year_match DESC, bm25_score DESC, id
                        LIMIT %s
                    )
                """)
            if method == "dense":
                final_query = """
                    SELECT e.document_name, e.chunk_index, e.content, e.metadata,
                           v.similarity_score AS retrieval_score
                    FROM vector_candidates AS v JOIN eligible AS e ON e.id = v.id
                    ORDER BY v.candidate_rank
                    LIMIT %s
                """
            elif method == "bm25":
                final_query = """
                    SELECT e.document_name, e.chunk_index, e.content, e.metadata,
                           b.bm25_score AS retrieval_score
                    FROM bm25_candidates AS b JOIN eligible AS e ON e.id = b.id
                    ORDER BY b.candidate_rank
                    LIMIT %s
                """
            else:
                final_query = """
                    , combined AS (
                    SELECT id, %s / (%s + candidate_rank) AS rrf_score
                    FROM vector_candidates
                    UNION ALL
                    SELECT id, %s / (%s + candidate_rank) AS rrf_score
                    FROM bm25_candidates
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
            if method != "dense":
                parameters.append(lexical_query)
            if method != "bm25":
                parameters.append(limit * 10)
            if method != "dense":
                parameters.append(limit * 10)
            if method == "hybrid":
                parameters.extend((dense_weight, rrf_k, bm25_weight, rrf_k))
            parameters.append(limit)
            cur.execute("WITH " + ",".join(ctes) + final_query, parameters)
            return [
                RetrievedChunk(
                    document_name=document_name,
                    chunk_index=chunk_index,
                    content=content,
                    metadata={} if metadata is None else metadata,
                    retrieval_score=retrieval_score,
                )
                for document_name, chunk_index, content, metadata, retrieval_score
                in cur.fetchall()
            ]
