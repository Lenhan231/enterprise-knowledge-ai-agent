"""Persist invoice uploads independently from the searchable document corpus."""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core.analytics.invoices import normalize_invoice

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

    def start_retry(self, invoice_id: str) -> bool:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.invoice_extractions
                   SET processing_status = 'processing', error_message = NULL, updated_at = now()
                   WHERE invoice_id = %s AND processing_status = 'failed'""",
                (invoice_id,),
            )
            return cursor.rowcount == 1

    def get_invoice(self, invoice_id: str) -> dict | None:
        with self.connection.transaction(), self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT invoice_id, source_filename, source_format, source_sha256,
                          storage_path, uploaded_by, processing_status, schema_version, invoice_data,
                          ocr_elements, ocr_tables,
                          extraction_model, extraction_metadata, review_required,
                          error_message, created_at, updated_at
                   FROM public.invoice_extractions WHERE invoice_id = %s""",
                (invoice_id,),
            )
            return cursor.fetchone()

    def list_invoices(self, username: str, *, include_all: bool = False, limit: int = 100) -> list[dict]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT invoice_id, source_filename, source_format, uploaded_by,
                          processing_status, schema_version, invoice_data,
                          extraction_model, review_required, error_message, created_at, updated_at
                   FROM public.invoice_extractions
                   WHERE (%s OR uploaded_by = %s)
                   ORDER BY created_at DESC LIMIT %s""",
                (include_all, username, max(1, min(int(limit), 200))),
            )
            return cursor.fetchall()

    def save_review(self, invoice_id: str, invoice_data: dict, reviewer: str) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.invoice_extractions
                   SET invoice_data = %s,
                       extraction_metadata = COALESCE(extraction_metadata, '{}'::jsonb)
                           || jsonb_build_object('human_review', jsonb_build_object(
                               'saved_by', %s::text, 'saved_at', now())),
                       updated_at = now()
                   WHERE invoice_id = %s AND processing_status = 'review_required'""",
                (Jsonb(invoice_data), reviewer, invoice_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Only completed, unapproved invoices can be edited")

    def reject(self, invoice_id: str, reviewer: str) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.invoice_extractions
                   SET processing_status = 'rejected', review_required = false,
                       extraction_metadata = COALESCE(extraction_metadata, '{}'::jsonb)
                           || jsonb_build_object('human_review',
                               COALESCE(extraction_metadata->'human_review', '{}'::jsonb)
                               || jsonb_build_object('rejected_by', %s::text, 'rejected_at', now())),
                       updated_at = now()
                   WHERE invoice_id = %s AND processing_status = 'review_required'""",
                (reviewer, invoice_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Only pending invoices can be rejected")

    def approve(self, invoice_id, *, invoice_data: dict | None = None, reviewer: str | None = None):
        """Explicit administrative review action; never called by the SQL agent."""
        with self.connection.transaction(), self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('SELECT invoice_id, invoice_data, source_filename, source_sha256, '
                           'schema_version, processing_status FROM public.invoice_extractions '
                           'WHERE invoice_id = %s FOR UPDATE', (invoice_id,))
            extraction = cursor.fetchone()
            if extraction is None:
                raise ValueError('Invoice extraction not found')
            if extraction['schema_version'] != 'invoice.v1':
                raise ValueError('Only invoice.v1 extractions are supported')
            if extraction['processing_status'] not in {'review_required', 'approved'}:
                raise ValueError('Only completed extractions can be approved')
            if reviewer is not None and extraction['processing_status'] != 'review_required':
                raise ValueError('This invoice was already approved')
            reviewed_data = invoice_data if invoice_data is not None else extraction['invoice_data']
            header, items = normalize_invoice(reviewed_data)
            if reviewer:
                cursor.execute(
                    """UPDATE public.invoice_extractions
                       SET invoice_data = %s,
                           extraction_metadata = COALESCE(extraction_metadata, '{}'::jsonb)
                               || jsonb_build_object('human_review', jsonb_build_object(
                                   'approved_by', %s::text, 'approved_at', now())),
                           processing_status = 'approved', review_required = false, updated_at = now()
                       WHERE invoice_id = %s""",
                    (Jsonb(reviewed_data), reviewer, invoice_id),
                )
            else:
                cursor.execute(
                    """UPDATE public.invoice_extractions
                       SET processing_status = 'approved', review_required = false, updated_at = now()
                       WHERE invoice_id = %s""",
                    (invoice_id,),
                )
            # The invalidation trigger removes an earlier projection in this same transaction.
            cursor.execute('INSERT INTO commerce.invoices '
                           '(invoice_id, source_filename, source_sha256, invoice_no, invoice_date, '
                           'buyer, seller, subtotal, tax_amount, total_amount, currency) '
                           'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                           (invoice_id, extraction['source_filename'], extraction['source_sha256'],
                            *(header[name] for name in ('invoice_no', 'invoice_date', 'buyer', 'seller',
                                                       'subtotal', 'tax_amount', 'total_amount', 'currency'))))
            if items:
                cursor.executemany('INSERT INTO commerce.invoice_items '
                                   '(invoice_id, line_no, description, unit, quantity, unit_price, amount) '
                                   'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                                   [(invoice_id, *(item[name] for name in
                                     ('line_no', 'description', 'unit', 'quantity', 'unit_price', 'amount')))
                                    for item in items])
        return len(items)

    def close(self) -> None:
        if self._owns_connection:
            close_database_connection(self.connection)
