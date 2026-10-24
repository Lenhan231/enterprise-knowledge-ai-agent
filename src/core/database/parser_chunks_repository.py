"""Persist parsed chunks independently from their retrieval embeddings."""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core.database.connection_limit import close_database_connection, connect_database

load_dotenv()


class ParserChunksRepository:
    def __init__(self, connection: psycopg.Connection | None = None):
        self.connection = connection or connect_database(os.environ["DATABASE_URL"])
        self._owns_connection = connection is None

    def replace_document(self, document_id: str, chunks: list[dict]) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM public.document_parser_chunks WHERE document_id = %s",
                (document_id,),
            )
            cursor.executemany(
                """INSERT INTO public.document_parser_chunks
                   (document_id, chunk_index, content, metadata)
                   VALUES (%s, %s, %s, %s)""",
                [
                    (
                        document_id,
                        index,
                        chunk["text"],
                        Jsonb({
                            key: value for key, value in chunk["metadata"].items()
                            if key not in {"embedding_model", "token_count"}
                        }),
                    )
                    for index, chunk in enumerate(chunks)
                ],
            )

    def get_document(
        self, document_id: str, limit: int | None = None, offset: int = 0,
        company: str | None = None,
    ) -> list[dict]:
        if limit is not None and not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        # Finish the implicit read transaction before callers perform writes;
        # otherwise their transaction() contexts become savepoints and close()
        # rolls back the apparent retry-state updates.
        with self.connection.transaction(), self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT c.chunk_index, c.content, c.metadata
                   FROM public.document_parser_chunks c
                   JOIN public.documents d USING(document_id)
                   WHERE c.document_id = %s
                     AND (%s::text IS NULL OR c.metadata->>'company' = %s::text)
                   ORDER BY c.chunk_index LIMIT %s OFFSET %s""",
                (document_id, company, company, limit, offset),
            )
            return cursor.fetchall()

    def close(self) -> None:
        if self._owns_connection:
            close_database_connection(self.connection)
