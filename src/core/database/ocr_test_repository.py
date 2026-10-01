"""Persist OCR-only inspection runs separately from the indexed corpus."""

from __future__ import annotations

import os
import uuid

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core.database.connection_limit import close_database_connection, connect_database

load_dotenv()


class OcrTestRepository:
    def __init__(self, connection: psycopg.Connection | None = None):
        self.connection = connection or connect_database(os.environ["DATABASE_URL"])
        self._owns_connection = connection is None

    def save_run(
        self, run_id: uuid.UUID, *, source_filename: str, source_sha256: str,
        uploaded_by: str, processor_config: dict, runtime_info: dict,
        page_previews: list[bytes], chunks: list[dict], tables: list[dict],
    ) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.ocr_test_runs
                   (run_id, source_filename, source_sha256, uploaded_by,
                    processor_config, runtime_info, page_count, chunk_count, table_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (run_id, source_filename, source_sha256, uploaded_by,
                 Jsonb(processor_config), Jsonb(runtime_info), len(page_previews),
                 len(chunks), len(tables)),
            )
            cursor.executemany(
                """INSERT INTO public.ocr_test_pages (run_id, page_number, preview_png)
                   VALUES (%s, %s, %s)""",
                [(run_id, index + 1, image) for index, image in enumerate(page_previews)],
            )
            cursor.executemany(
                """INSERT INTO public.ocr_test_chunks (run_id, chunk_index, content, metadata)
                   VALUES (%s, %s, %s, %s)""",
                [(run_id, index, chunk["text"], Jsonb(chunk["metadata"]))
                 for index, chunk in enumerate(chunks)],
            )
            cursor.executemany(
                """INSERT INTO public.ocr_test_tables
                   (run_id, table_index, page_number, structured_data, context, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [
                    (
                        run_id, index, table.get("page_number"),
                        Jsonb({"columns": table.get("columns", []), "rows": table.get("rows", [])}),
                        Jsonb({
                            **table.get("context", {}),
                            "source_filename": source_filename,
                            "page_number": table.get("page_number"),
                            "section_title": next((
                                chunk.get("metadata", {}).get("section_title")
                                for chunk in chunks
                                if chunk.get("metadata", {}).get("page_number") == table.get("page_number")
                                and chunk.get("metadata", {}).get("section_title")
                            ), None),
                        }),
                        Jsonb({
                            key: value for key, value in table.get("metadata", {}).items()
                            if key not in {"filename", "format", "source_type", "source_sha256"}
                        }),
                    )
                    for index, table in enumerate(tables)
                ],
            )

    def list_runs(self, limit: int = 20) -> list[dict]:
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT run_id, source_filename, source_sha256, processor_config,
                          page_count, chunk_count, table_count, created_at
                   FROM public.ocr_test_runs
                   ORDER BY created_at DESC LIMIT %s""",
                (limit,),
            )
            return cursor.fetchall()

    def get_run(self, run_id: uuid.UUID) -> dict | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM public.ocr_test_runs WHERE run_id = %s", (run_id,),
            )
            run = cursor.fetchone()
            if run is None:
                return None
            cursor.execute(
                """SELECT chunk_index, content, metadata
                   FROM public.ocr_test_chunks WHERE run_id = %s ORDER BY chunk_index""",
                (run_id,),
            )
            run["chunks"] = cursor.fetchall()
            cursor.execute(
                """SELECT table_index, page_number, structured_data, context, metadata
                   FROM public.ocr_test_tables WHERE run_id = %s ORDER BY table_index""",
                (run_id,),
            )
            run["tables"] = cursor.fetchall()
            cursor.execute(
                """SELECT page_number FROM public.ocr_test_pages
                   WHERE run_id = %s ORDER BY page_number""",
                (run_id,),
            )
            run["pages"] = [row["page_number"] for row in cursor.fetchall()]
            return run

    def get_page_preview(self, run_id: uuid.UUID, page_number: int) -> bytes | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT preview_png FROM public.ocr_test_pages
                   WHERE run_id = %s AND page_number = %s""",
                (run_id, page_number),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def close(self) -> None:
        if self._owns_connection:
            close_database_connection(self.connection)
