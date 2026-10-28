"""Persist normalized document-processing output before chunking."""

from __future__ import annotations

import os
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core.database.connection_limit import close_database_connection, connect_database
from document_processing.element_taxonomy import normalize_element_label

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

        text_elements: list[dict[str, Any]] = []
        figures: list[dict[str, Any]] = []
        text_rows = []
        figure_rows = []
        for index, element in enumerate(elements):
            normalized = dict(element)
            element_metadata = dict(element.get("metadata") or {})
            element_metadata.pop("word_style", None)
            element_metadata.pop("word_style_id", None)
            element_type = normalize_element_label(
                element_metadata.get("element_type")
                or element_metadata.get("layout_type")
                or element.get("element_type")
            )
            element_metadata.update({"element_type": element_type, "layout_type": element_type})
            normalized["metadata"] = element_metadata
            if "element_type" in normalized:
                normalized["element_type"] = element_type
            page_number = element_metadata.get("page_number")
            page_number = int(page_number) if page_number is not None else None
            bbox = Jsonb(element_metadata["bbox"]) if element_metadata.get("bbox") is not None else None
            if element_type in {"figure", "seal"}:
                normalized.pop("text", None)
                figures.append(normalized)
                figure_rows.append((
                    document_id, index, element_type, page_number, bbox, Jsonb(element_metadata),
                ))
            elif element_type != "table":
                text_elements.append(normalized)
                text_rows.append((
                    document_id, index, element_type, element.get("text"),
                    page_number, bbox, Jsonb(element_metadata),
                ))

        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM public.document_processing_text_elements WHERE document_id = %s",
                (document_id,),
            )
            cursor.execute(
                "DELETE FROM public.document_processing_figures WHERE document_id = %s",
                (document_id,),
            )
            if text_rows:
                cursor.executemany(
                    """INSERT INTO public.document_processing_text_elements
                       (document_id, element_index, element_type, text, page_number, bbox, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    text_rows,
                )
            if figure_rows:
                cursor.executemany(
                    """INSERT INTO public.document_processing_figures
                       (document_id, element_index, element_type, page_number, bbox, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    figure_rows,
                )
            cursor.execute(
                """INSERT INTO public.document_processing_outputs
                   (document_id, pipeline_id, text_elements, figures, structured_tables, document_metadata)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (document_id) DO UPDATE SET
                       pipeline_id = EXCLUDED.pipeline_id,
                       text_elements = EXCLUDED.text_elements,
                       figures = EXCLUDED.figures,
                       structured_tables = EXCLUDED.structured_tables,
                       document_metadata = EXCLUDED.document_metadata,
                       updated_at = now()""",
                (
                    document_id,
                    pipeline_id,
                    Jsonb(text_elements),
                    Jsonb(figures),
                    Jsonb(tables),
                    Jsonb(metadata),
                ),
            )

    def get_document_output(self, document_id: str, *, company: str) -> dict[str, Any] | None:
        with self.connection.transaction(), self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT o.pipeline_id, o.text_elements, o.figures,
                          o.structured_tables, o.document_metadata
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
            "elements": [*(row["text_elements"] or []), *(row["figures"] or [])],
            "tables": row["structured_tables"],
        }

    def close(self) -> None:
        if self._owns_connection:
            close_database_connection(self.connection)
