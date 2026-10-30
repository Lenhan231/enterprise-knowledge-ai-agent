"""Persist upload-pipeline test runs separately from the indexed corpus."""

from __future__ import annotations

import os
import uuid
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core.database.connection_limit import close_database_connection, connect_database

load_dotenv()


class UploadTestRepository:
    def __init__(self, connection: psycopg.Connection | None = None):
        self.connection = connection or connect_database(os.environ["DATABASE_URL"])
        self._owns_connection = connection is None

    def save_run(
        self,
        run_id: uuid.UUID,
        *,
        source_filename: str,
        source_sha256: str,
        uploaded_by: str,
        processor_config: dict[str, Any],
        runtime_info: dict[str, Any],
        page_previews: list[bytes],
        elements: list[dict[str, Any]],
        tables: list[dict[str, Any]],
    ) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO document_preprocessing_test.upload_test_runs
                   (run_id, source_filename, source_sha256, uploaded_by,
                    processor_config, runtime_info, page_count, element_count, table_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    run_id, source_filename, source_sha256, uploaded_by,
                    Jsonb(processor_config), Jsonb(runtime_info), len(page_previews),
                    len(elements), len(tables),
                ),
            )
            cursor.executemany(
                """INSERT INTO document_preprocessing_test.upload_test_pages (run_id, page_number, preview_png)
                   VALUES (%s, %s, %s)""",
                [(run_id, index + 1, image) for index, image in enumerate(page_previews)],
            )
            cursor.executemany(
                """INSERT INTO document_preprocessing_test.upload_test_elements
                   (run_id, element_index, content, metadata) VALUES (%s, %s, %s, %s)""",
                [
                    (run_id, index, element.get("text", ""), Jsonb(element.get("metadata", {})))
                    for index, element in enumerate(elements)
                ],
            )
            cursor.executemany(
                """INSERT INTO document_preprocessing_test.upload_test_tables
                   (run_id, table_index, page_number, columns, context, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [
                    (
                        run_id, index, table.get("page_number"),
                        Jsonb(table.get("columns", [])),
                        Jsonb({
                            **table.get("context", {}),
                            "source_filename": source_filename,
                            **({"page_number": table["page_number"]} if table.get("page_number") is not None else {}),
                            "section_title": next((
                                element.get("metadata", {}).get("section_title")
                                for element in elements
                                if element.get("metadata", {}).get("element_type") == "table"
                                and all(
                                    element.get("metadata", {}).get(key) == table.get(key)
                                    for key in ("page_number", "sheet_name", "slide_number", "paragraph_index", "table_index")
                                    if table.get(key) is not None
                                )
                                and element.get("metadata", {}).get("section_title")
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
            cursor.executemany(
                """INSERT INTO document_preprocessing_test.upload_test_records
                   (run_id, table_index, row_index, data) VALUES (%s, %s, %s, %s)""",
                [
                    (run_id, table_index, row_index, Jsonb(row))
                    for table_index, table in enumerate(tables)
                    for row_index, row in enumerate(table.get("rows", []))
                ],
            )

    def list_runs(self, limit: int = 20) -> list[dict]:
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT run_id, source_filename, source_sha256, processor_config, runtime_info,
                          page_count, element_count, table_count, created_at
                   FROM document_preprocessing_test.upload_test_runs
                   ORDER BY created_at DESC LIMIT %s""",
                (limit,),
            )
            return cursor.fetchall()

    def get_run(self, run_id: uuid.UUID) -> dict | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM document_preprocessing_test.upload_test_runs WHERE run_id = %s", (run_id,))
            run = cursor.fetchone()
            if run is None:
                return None
            cursor.execute(
                """SELECT element_index, content, metadata
                   FROM document_preprocessing_test.upload_test_elements WHERE run_id = %s ORDER BY element_index""",
                (run_id,),
            )
            run["elements"] = cursor.fetchall()
            cursor.execute(
                """SELECT t.table_index, t.page_number,
                          jsonb_build_object(
                              'columns', t.columns,
                              'rows', coalesce((
                                  SELECT jsonb_agg(r.data ORDER BY r.row_index)
                                  FROM document_preprocessing_test.upload_test_records r
                                  WHERE r.run_id = t.run_id AND r.table_index = t.table_index
                              ), '[]'::jsonb)
                          ) AS structured_data,
                          t.context, t.metadata,
                          (SELECT count(*) FROM document_preprocessing_test.upload_test_records r
                           WHERE r.run_id = t.run_id AND r.table_index = t.table_index) AS row_count
                   FROM document_preprocessing_test.upload_test_tables t
                   WHERE t.run_id = %s ORDER BY t.table_index""",
                (run_id,),
            )
            run["tables"] = cursor.fetchall()
            cursor.execute(
                """SELECT page_number FROM document_preprocessing_test.upload_test_pages
                   WHERE run_id = %s ORDER BY page_number""",
                (run_id,),
            )
            run["pages"] = [row["page_number"] for row in cursor.fetchall()]
            return run

    def get_page_preview(self, run_id: uuid.UUID, page_number: int) -> bytes | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT preview_png FROM document_preprocessing_test.upload_test_pages
                   WHERE run_id = %s AND page_number = %s""",
                (run_id, page_number),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def close(self) -> None:
        if self._owns_connection:
            close_database_connection(self.connection)
