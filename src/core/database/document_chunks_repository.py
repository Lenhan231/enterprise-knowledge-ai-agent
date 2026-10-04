import os
from typing import Literal
from psycopg.types.json import Jsonb

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from core.database.connection_limit import close_database_connection, connect_database
from core.retrieval.retrieval import RetrievedChunk
from core.retrieval.methods.common import (
    explicit_fiscal_year as _explicit_fiscal_year,
    lexical_tsquery as _lexical_tsquery,
)

load_dotenv()

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

    def replace_document(self, document_id: str, chunks: list[tuple]) -> None:
        """Atomically replace all chunks for a stable document ID."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM document_chunks WHERE metadata->>'document_id' = %s",
                (document_id,),
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

    def get_document_chunks(
        self, document_id: str, limit: int = 25, offset: int = 0,
        company: str | None = None,
    ) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        with self.conn.cursor() as cursor:
            cursor.execute(
                """SELECT c.chunk_index, c.content, c.metadata,
                          'embedded'::text AS processing_status,
                          NULL::text AS processing_error
                   FROM public.document_chunks c
                   JOIN public.documents d ON d.document_id = c.metadata->>'document_id'
                   WHERE d.document_id = %s
                     AND coalesce(d.processing_status, 'ready') = 'ready'
                     AND (%s::text IS NULL OR d.company = %s::text)
                   ORDER BY c.chunk_index LIMIT %s OFFSET %s""",
                (document_id, company, company, limit, offset),
            )
            columns = [column.name for column in cursor.description]
            return [dict(row) if isinstance(row, dict) else dict(zip(columns, row))
                    for row in cursor.fetchall()]

    def get_document_chunk(
        self, chunk_id: int, document_id: str, company: str | None = None,
    ) -> dict | None:
        """Load one indexed passage by its persisted provenance key."""
        with self.conn.cursor() as cursor:
            cursor.execute(
                """SELECT c.chunk_index, c.content, c.metadata,
                          'embedded'::text AS processing_status,
                          NULL::text AS processing_error
                   FROM public.document_chunks c
                   JOIN public.documents d ON d.document_id = c.metadata->>'document_id'
                   WHERE c.id = %s AND d.document_id = %s
                     AND coalesce(d.processing_status, 'ready') = 'ready'
                     AND (%s::text IS NULL OR d.company = %s::text)
                   LIMIT 1""",
                (chunk_id, document_id, company, company),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            columns = [column.name for column in cursor.description]
            return dict(row) if isinstance(row, dict) else dict(zip(columns, row))

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
        metadata_filter: dict | None = None,
        method: Literal["dense", "bm25", "hybrid"] = "hybrid",
        dense_weight: float = 1.0, bm25_weight: float = 2.0, rrf_k: int = 60,
    ) -> list[RetrievedChunk]:
        """Compatibility boundary dispatching to the method-specific SQL modules."""
        if method not in {"dense", "bm25", "hybrid"}:
            raise ValueError("method must be dense, bm25, or hybrid")
        if method != "bm25" and query_embedding is None:
            raise ValueError("query_embedding is required for dense and hybrid retrieval")
        if dense_weight <= 0 or bm25_weight <= 0 or rrf_k < 0:
            raise ValueError("hybrid weights must be positive and rrf_k must be non-negative")
        from core.retrieval.methods import bm25, dense, hybrid

        options = {"query": query, "company": company, "roles": roles, "metadata_filter": metadata_filter}
        if method == "dense":
            return dense.search(self, query_embedding, limit, **options)
        if method == "bm25":
            return bm25.search(self, limit, **options)
        return hybrid.search(
            self, query_embedding, limit, dense_weight=dense_weight,
            bm25_weight=bm25_weight, rrf_k=rrf_k, **options,
        )
