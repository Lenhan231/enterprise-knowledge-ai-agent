"""Store PDF upload jobs and commit one checkpoint per completed page range."""

from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core.database.connection_limit import close_database_connection, connect_database

# A two-key PostgreSQL advisory lock identifies the worker for each PDF job.
# The application's session pool preserves the lock across checkpoint commits.
PDF_LOCK_NAMESPACE = 324176
_JOB_STATUS = f"""
    CASE WHEN d.processing_status = 'processing'
          AND j.queued_at < now() - interval '30 seconds'
          AND NOT EXISTS (
              SELECT 1 FROM pg_locks l
              WHERE l.locktype = 'advisory' AND l.granted AND l.objsubid = 2
                AND l.classid = {PDF_LOCK_NAMESPACE}::oid AND l.objid = j.lock_id::oid
                AND l.database = (SELECT oid FROM pg_database WHERE datname = current_database())
          )
         THEN 'failed'
         ELSE d.processing_status
    END
"""


@contextmanager
def pdf_jobs():
    connection = connect_database(autocommit=True, row_factory=dict_row)
    try:
        yield PdfJobRepository(connection)
    finally:
        close_database_connection(connection)


class PdfJobRepository:
    def __init__(self, connection):
        self.connection = connection

    def enqueue(self, document_id, filename, source_hash, config, metadata, handoff, page_count, batch_size):
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.document_pdf_jobs
                    (document_id, filename, source_sha256, parser_config, document_metadata,
                     parser_handoff, page_count, batch_size)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (document_id, filename, source_hash, Jsonb(config), Jsonb(metadata),
                  handoff, page_count, batch_size))
            self.set_status(document_id, "processing")

    def list_pending(self, uploader, is_admin):
        with self.connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT j.document_id, d.title, j.page_count, j.pages_processed, j.failed_page,
                       {_JOB_STATUS} AS processing_status
                FROM public.document_pdf_jobs j
                JOIN public.documents d USING (document_id)
                WHERE j.result IS NULL AND (%s OR d.uploaded_by = %s)
                ORDER BY j.queued_at DESC
            """, (is_admin, uploader))
            return cursor.fetchall()

    def get(self, document_id, uploader=None, is_admin=False):
        with self.connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT j.*, d.title, d.storage_path, {_JOB_STATUS} AS processing_status
                FROM public.document_pdf_jobs j
                JOIN public.documents d USING (document_id)
                WHERE j.document_id = %s AND (%s OR d.uploaded_by = %s)
            """, (document_id, is_admin, uploader))
            return cursor.fetchone()

    def retry(self, document_id, uploader, is_admin):
        with self.connection.transaction(), self.connection.cursor() as cursor:
            job = self.get(document_id, uploader, is_admin)
            if job is None or job["processing_status"] != "failed" or job["result"] is not None:
                return None
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s, %s) AS acquired",
                           (PDF_LOCK_NAMESPACE, job["lock_id"]))
            if not cursor.fetchone()["acquired"]:
                return None
            cursor.execute("""
                UPDATE public.document_pdf_jobs
                SET attempt = attempt + 1, queued_at = now(), failed_page = NULL
                WHERE document_id = %s AND attempt = %s
                RETURNING attempt
            """, (document_id, job["attempt"]))
            row = cursor.fetchone()
            if row is None:
                return None
            self.set_status(document_id, "processing")
            return row["attempt"]

    def claim(self, document_id, attempt):
        job = self.get(document_id, is_admin=True)
        if job is None or job["attempt"] != attempt or job["result"] is not None:
            return None
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s) AS acquired",
                           (PDF_LOCK_NAMESPACE, job["lock_id"]))
            if not cursor.fetchone()["acquired"]:
                return None
        current = self.get(document_id, is_admin=True)
        if current is None or current["attempt"] != attempt or current["processing_status"] != "processing":
            return None
        return current

    def save_checkpoint(self, document_id, first_page, last_page, output):
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.document_pdf_checkpoints (document_id, first_page, output)
                VALUES (%s, %s, %s)
            """, (document_id, first_page, Jsonb(output)))
            cursor.execute("""
                UPDATE public.document_pdf_jobs SET pages_processed = %s WHERE document_id = %s
            """, (last_page, document_id))

    def checkpoints(self, document_id):
        with self.connection.cursor() as cursor:
            cursor.execute("""
                SELECT first_page, output FROM public.document_pdf_checkpoints
                WHERE document_id = %s ORDER BY first_page
            """, (document_id,))
            return cursor.fetchall()

    def set_status(self, document_id, status):
        with self.connection.cursor() as cursor:
            cursor.execute("UPDATE public.documents SET processing_status = %s WHERE document_id = %s",
                           (status, document_id))

    def fail(self, document_id, first_page):
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute("UPDATE public.document_pdf_jobs SET failed_page = %s WHERE document_id = %s",
                           (first_page, document_id))
            self.set_status(document_id, "failed")

    def complete(self, document_id, result):
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute("UPDATE public.document_pdf_jobs SET result = %s WHERE document_id = %s",
                           (Jsonb(result), document_id))
            self.set_status(document_id, result["processing_status"])
            cursor.execute("DELETE FROM public.document_pdf_checkpoints WHERE document_id = %s",
                           (document_id,))
