"""Persistence for tables already extracted from uploaded source documents."""

from __future__ import annotations

import os
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from core.database.connection_limit import close_database_connection, connect_database

load_dotenv()


class StructuredDataStore:
    """Replace one document's extracted tables using the app's trusted DB role."""

    def __init__(self, connection: psycopg.Connection | None = None):
        self.connection = connection or connect_database(os.environ["DATABASE_URL"])
        self._owns_connection = connection is None

    def save_document_tables(self, document_id: str, document_name: str, tables: list[dict[str, Any]]) -> tuple[int, int]:
        records_count = 0
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute("DELETE FROM public.extracted_tables WHERE document_id = %s", (document_id,))
            for table in tables:
                page_number = int(table["page_number"])
                table_index = int(table["table_index"])
                table_id = f"{document_id}:page:{page_number}:table:{table_index}"
                cursor.execute(
                    """INSERT INTO public.extracted_tables
                       (id, document_id, document_name, page_number, table_index, columns, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (table_id, document_id, document_name, page_number, table_index,
                     Jsonb(table.get("columns", [])), Jsonb(table.get("metadata", {}))),
                )
                rows = table.get("rows", [])
                if rows:
                    cursor.executemany(
                        """INSERT INTO public.extracted_records (id, table_id, row_index, data)
                           VALUES (%s, %s, %s, %s)""",
                        [(f"{table_id}:row:{i}", table_id, i, Jsonb(row)) for i, row in enumerate(rows)],
                    )
                    records_count += len(rows)
        return len(tables), records_count

    def get_document_tables(
        self, document_id: str, *, company: str, table_offset: int = 0,
        table_limit: int = 50, row_offset: int = 0, row_limit: int = 100,
    ) -> list[dict[str, Any]]:
        if table_offset < 0 or row_offset < 0:
            raise ValueError("Offsets must be non-negative")
        if not 1 <= table_limit <= 50 or not 1 <= row_limit <= 100:
            raise ValueError("table_limit must be 1-50 and row_limit must be 1-100")
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT t.id, t.page_number, t.table_index, t.columns, t.metadata,
                          (SELECT count(*) FROM public.extracted_records r
                           WHERE r.table_id = t.id) AS row_count,
                          COALESCE((
                              SELECT jsonb_agg(page.data ORDER BY page.row_index)
                              FROM (
                                  SELECT r.row_index, r.data
                                  FROM public.extracted_records r
                                  WHERE r.table_id = t.id
                                  ORDER BY r.row_index
                                  LIMIT %s OFFSET %s
                              ) page
                          ), '[]'::jsonb) AS rows
                   FROM public.extracted_tables t
                   JOIN public.documents d ON d.document_id = t.document_id
                   WHERE t.document_id = %s AND d.company = %s
                   ORDER BY t.page_number, t.table_index
                   LIMIT %s OFFSET %s""",
                (row_limit, row_offset, document_id, company, table_limit, table_offset),
            )
            columns = [item.name for item in cursor.description]
            return [dict(row) if isinstance(row, dict) else dict(zip(columns, row))
                    for row in cursor.fetchall()]

    def close(self) -> None:
        if self._owns_connection:
            close_database_connection(self.connection)
