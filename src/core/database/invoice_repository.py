"""Persist invoice uploads independently from the searchable document corpus."""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core.database.connection_limit import close_database_connection, connect_database

load_dotenv()


class InvoiceRepository:
    def __init__(self, connection: psycopg.Connection | None = None):
        self.connection = connection or connect_database(os.environ["DATABASE_URL"])
        self._owns_connection = connection is None

    def create_upload(self, invoice: dict) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.invoice_extractions
                   (invoice_id, source_filename, source_format, source_sha256,
                    storage_path, uploaded_by)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    invoice["invoice_id"], invoice["source_filename"],
                    invoice["source_format"], invoice["source_sha256"],
                    invoice["storage_path"], invoice["uploaded_by"],
                ),
            )

    def save_result(
        self,
        invoice_id: str,
        *,
        invoice_data: dict,
        ocr_elements: list[dict],
        ocr_tables: list[dict],
        extraction_model: str,
        extraction_metadata: dict,
        error_message: str | None = None,
    ) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.invoice_extractions
                   SET processing_status = 'review_required',
                       invoice_data = %s,
                       ocr_elements = %s,
                       ocr_tables = %s,
                       extraction_model = %s,
                       extraction_metadata = %s,
                       error_message = %s,
                       review_required = true,
                       updated_at = now()
                   WHERE invoice_id = %s""",
                (
                    Jsonb(invoice_data), Jsonb(ocr_elements), Jsonb(ocr_tables),
                    extraction_model, Jsonb(extraction_metadata), error_message,
                    invoice_id,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError("Invoice upload was not found")

    def mark_failed(self, invoice_id: str, message: str) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.invoice_extractions
                   SET processing_status = 'failed', error_message = %s,
                       updated_at = now()
                   WHERE invoice_id = %s""",
                (message[:1000], invoice_id),
            )

    def get_invoice(self, invoice_id: str) -> dict | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT invoice_id, source_filename, source_format, source_sha256,
                          uploaded_by, processing_status, schema_version, invoice_data,
                          extraction_model, extraction_metadata, review_required,
                          error_message, created_at, updated_at
                   FROM public.invoice_extractions WHERE invoice_id = %s""",
                (invoice_id,),
            )
            return cursor.fetchone()

    def close(self) -> None:
        if self._owns_connection:
            close_database_connection(self.connection)
