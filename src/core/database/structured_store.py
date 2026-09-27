"""Persistence for tables already extracted from uploaded source documents."""

from __future__ import annotations

import os
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

load_dotenv()


class StructuredDataStore:
    """Replace one document's extracted tables using the app's trusted DB role."""

    def __init__(self, connection: psycopg.Connection | None = None):
        self.connection = connection or psycopg.connect(os.environ["DATABASE_URL"])
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

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()
