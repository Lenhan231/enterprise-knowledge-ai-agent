"""Persist raw parser output before the chunking stage."""

from __future__ import annotations

import os
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from core.database.connection_limit import close_database_connection, connect_database
from document_processing.element_taxonomy import normalize_element_label

load_dotenv()


class DocumentProcessingOutputRepository:
    """Store normalized elements and structured tables without chunking."""

    def __init__(self, connection: psycopg.Connection | None = None):
        self.connection = connection or connect_database(os.environ["DATABASE_URL"])
        self._owns_connection = connection is None

    def save_parser_output(
        self,
        *,
        document_id: str,
        title: str,
        file_format: str,
        source_sha256: str,
        pipeline_id: str,
        elements: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        document_metadata: dict[str, Any],
    ) -> tuple[int, int]:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.documents
                       (document_id, domain, title, format, verification,
                        document_type, source_type, allowed_roles,
                        processing_status, knowledge_base_active)
                   VALUES (%s, 'general_knowledge', %s, %s, %s,
                           'parser_output_preview', 'parser_preview', '{}',
                           'parsed', false)
                   ON CONFLICT (document_id) DO UPDATE SET
                       title = EXCLUDED.title,
                       format = EXCLUDED.format,
                       verification = EXCLUDED.verification,
                       document_type = EXCLUDED.document_type,
                       source_type = EXCLUDED.source_type,
                       allowed_roles = EXCLUDED.allowed_roles,
                       processing_status = EXCLUDED.processing_status,
                       knowledge_base_active = false""",
                (
                    document_id,
                    title,
                    file_format,
                    f"Local parser output only · SHA-256 {source_sha256} · not chunked or indexed",
                ),
            )
            normalized_elements = self._normalize_elements(elements)
            self._write_output(
                cursor, document_id, pipeline_id, normalized_elements,
                tables, document_metadata,
            )
        return len(normalized_elements), len(tables)

    def replace_document(self, document_id: str, parsed: dict[str, Any]) -> tuple[int, int]:
        """Persist the parser's canonical ``elements`` and ``tables`` payload."""
        metadata = dict(parsed.get("metadata") or {})
        elements = self._normalize_elements(parsed.get("elements") or [])
        tables = parsed.get("tables") or []
        pipeline_id = str(metadata.get("pipeline_id") or metadata.get("parser_engine") or "docling")
        with self.connection.transaction(), self.connection.cursor() as cursor:
            self._write_output(cursor, document_id, pipeline_id, elements, tables, metadata)
        return len(elements), len(tables)

    @staticmethod
    def _normalize_elements(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for element in elements:
            item = dict(element)
            metadata = dict(element.get("metadata") or {})
            metadata.pop("word_style", None)
            metadata.pop("word_style_id", None)
            element_type = normalize_element_label(
                metadata.get("element_type") or metadata.get("layout_type") or element.get("element_type")
            )
            metadata.update({"element_type": element_type, "layout_type": element_type})
            item["metadata"] = metadata
            if "element_type" in item:
                item["element_type"] = element_type
            normalized.append(item)
        return normalized

    @staticmethod
    def _write_output(cursor, document_id, pipeline_id, elements, tables, document_metadata) -> None:
        cursor.execute(
            """INSERT INTO public.document_processing_outputs
                   (document_id, pipeline_id, elements, tables, document_metadata)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (document_id) DO UPDATE SET
                   pipeline_id = EXCLUDED.pipeline_id,
                   elements = EXCLUDED.elements,
                   tables = EXCLUDED.tables,
                   document_metadata = EXCLUDED.document_metadata,
                   updated_at = now()""",
            (
                document_id, pipeline_id, Jsonb(elements), Jsonb(tables),
                Jsonb(document_metadata),
            ),
        )

    def close(self) -> None:
        if self._owns_connection:
            close_database_connection(self.connection)
