import os
import queue
import threading
from types import SimpleNamespace
from core.latency import measure
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

# translated_hybrid runs 1 dense + 2 BM25 searches at once; Supabase is ~0.4 s per round trip from the VPS.
EXTRA_SEARCH_CONNECTIONS = 2


class DocumentChunkRepository:
    _search_lock = None  # no extra search connections unless __init__ opened the real database

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
        self._idle_search = queue.SimpleQueue()
        self._search_connections = []
        self._search_lock = threading.Lock()
        

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
                     AND (%s::text IS NULL OR c.metadata->>'company' = %s::text)
                   ORDER BY c.chunk_index LIMIT %s OFFSET %s""",
                (document_id, company, company, limit, offset),
            )
            columns = [column.name for column in cursor.description]
            return [dict(row) if isinstance(row, dict) else dict(zip(columns, row))
                    for row in cursor.fetchall()]

    def close(self) -> None:
        if self._search_lock is None:
            close_database_connection(self.conn)
            return
        try:
            with self._search_lock:
                extras, self._search_connections = self._search_connections, []
            for connection in extras:
                if connection is not None:
                    close_database_connection(connection)
        finally:
            close_database_connection(self.conn)

    def _borrow_search_connection(self):
        if self._search_lock is None:
            return self.conn
        try:
            return self._idle_search.get_nowait()
        except queue.Empty:
            pass
        with self._search_lock:
            if len(self._search_connections) >= EXTRA_SEARCH_CONNECTIONS:
                return self.conn  # psycopg serializes queries that share a connection
            self._search_connections.append(None)  # reserve the slot while connecting
        try:
            connection = connect_database(self.DATABASE_URL)
            try:
                register_vector(connection)
            except BaseException:
                close_database_connection(connection)
                raise
        except BaseException:
            with self._search_lock:
                self._search_connections.remove(None)
            raise
        with self._search_lock:
            self._search_connections[self._search_connections.index(None)] = connection
        return connection

    def _return_search_connection(self, connection) -> None:
        if connection is self.conn:
            return
        if not (connection.closed or connection.broken):
            try:
                if connection.info.transaction_status == psycopg.pq.TransactionStatus.INERROR:
                    connection.rollback()
                self._idle_search.put(connection)
                return
            except psycopg.Error:
                pass
        with self._search_lock:
            if connection in self._search_connections:
                self._search_connections.remove(connection)
        close_database_connection(connection)

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
            filters.append("c.metadata->>'company' = %s::text")
            parameters.append(company)
        if roles is not None:
            filters.append("(d.allowed_roles && %s::text[] OR 'admin' = ANY(%s::text[]))")
            parameters.extend((roles, roles))
        else:
            filters.append("cardinality(d.allowed_roles) > 0")
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
            WHERE d.processing_status = 'ready'
              AND d.knowledge_base_active IS TRUE{filter_sql}
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
            siblings = grouped.get(key)
            if not siblings:
                continue
            contexts[key] = {
                "text": "\n".join(content for _, content in siblings),
                "texts": [content for _, content in siblings],
                "chunk_indices": [index for index, _ in siblings],
                "parent_chunk_count": len(siblings),
                "parent_context_type": "section_window" if chunk.metadata.get("section_title") else "page_window",
            }
        return contexts

    @measure("database_retrieval")
    def similarity_search(
        self, query_embedding: list[float] | None, limit: int, company: str | None = None,
        roles: list[str] | None = None, query: str | None = None,
        method: Literal["dense", "bm25", "hybrid"] = "hybrid",
        dense_weight: float = 1.0, bm25_weight: float = 2.0, rrf_k: int = 60,
        document_ids: list[str] | None = None,
        metadata_filter: dict | None = None,
    ) -> list[RetrievedChunk]:
        """Compatibility boundary dispatching to the method-specific SQL modules."""
        if method not in {"dense", "bm25", "hybrid"}:
            raise ValueError("method must be dense, bm25, or hybrid")
        if method != "bm25" and query_embedding is None:
            raise ValueError("query_embedding is required for dense and hybrid retrieval")
        if dense_weight <= 0 or bm25_weight <= 0 or rrf_k < 0:
            raise ValueError("hybrid weights must be positive and rrf_k must be non-negative")
        from core.retrieval.methods import bm25, dense, hybrid

        options = {"query": query, "company": company, "roles": roles,
                   "document_ids": document_ids, "metadata_filter": metadata_filter}
        connection = self._borrow_search_connection()
        try:
            view = SimpleNamespace(conn=connection)  # the search modules only read .conn
            if method == "dense":
                return dense.search(view, query_embedding, limit, **options)
            if method == "bm25":
                return bm25.search(view, limit, **options)
            return hybrid.search(
                view, query_embedding, limit, dense_weight=dense_weight,
                bm25_weight=bm25_weight, rrf_k=rrf_k, **options,
            )
        finally:
            self._return_search_connection(connection)
