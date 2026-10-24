"""Persist normalized document-processing output before chunking."""

from __future__ import annotations

import os
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core.database.connection_limit import close_database_connection, connect_database

load_dotenv()


class DocumentProcessingOutputsRepository:
    def __init__(self, connection: psycopg.Connection | None = None):
        self.connection = connection or connect_database(os.environ["DATABASE_URL"])
        self._owns_connection = connection is None

    def replace_document(self, document_id: str, parsed: dict[str, Any]) -> None:
        metadata = parsed.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("Parsed output metadata must be an object")
        elements = parsed.get("elements")
        tables = parsed.get("tables")
        pipeline_id = metadata.get("pipeline_id") or metadata.get("parser_engine")
        if not isinstance(elements, list) or not isinstance(tables, list):
            raise ValueError("Parsed output must contain elements and tables lists")
        if not isinstance(pipeline_id, str) or not pipeline_id:
            raise ValueError("Parsed output must include document metadata and pipeline_id")

        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.document_processing_outputs
                   (document_id, pipeline_id, elements, structured_tables, document_metadata)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (document_id) DO UPDATE SET
                       pipeline_id = EXCLUDED.pipeline_id,
                       elements = EXCLUDED.elements,
                       structured_tables = EXCLUDED.structured_tables,
                       document_metadata = EXCLUDED.document_metadata,
                       updated_at = now()""",
                (
                    document_id,
                    pipeline_id,
                    Jsonb(elements),
                    Jsonb(tables),
                    Jsonb(metadata),
                ),
            )

    def get_document_output(self, document_id: str, *, company: str) -> dict[str, Any] | None:
        with self.connection.transaction(), self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT o.pipeline_id, o.elements, o.structured_tables, o.document_metadata
                   FROM public.document_processing_outputs o
                   JOIN public.documents d USING (document_id)
                   WHERE o.document_id = %s AND o.document_metadata->>'company' = %s""",
                (document_id, company),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "metadata": row["document_metadata"],
            "elements": row["elements"],
            "tables": row["structured_tables"],
        }

    def close(self) -> None:
        if self._owns_connection:
            close_database_connection(self.connection)
