"""Claim parsed documents and persist character-based chunks, without embedding."""

from __future__ import annotations

import argparse
import logging
import math
import os
import signal
from threading import Event

from psycopg.rows import dict_row

from core.chunking.processing_output import map_output
from core.chunking.processor import ChunkingProcessor
from core.database.connection_limit import close_database_connection, connect_database
from core.database.parser_chunks_repository import ParserChunksRepository

log = logging.getLogger(__name__)


def check_schema(connection) -> None:
    """Refuse to consume documents before the status migration is applied."""
    with connection.cursor() as cursor:
        cursor.execute("""SELECT pg_get_constraintdef(oid) FROM pg_constraint
                          WHERE conrelid='public.documents'::regclass
                            AND conname='documents_processing_status_check'""")
        constraint = cursor.fetchone()
    if constraint is None or "'chunked'" not in constraint[0]:
        raise RuntimeError("Apply 20261028090548_add_chunking_document_statuses.sql before starting the worker")
    with connection.cursor() as cursor:
        cursor.execute("""SELECT column_name FROM information_schema.columns
                          WHERE table_schema='public' AND table_name='document_processing_outputs'""")
        columns = {row[0] for row in cursor.fetchall()}
    if not {"elements", "tables"} <= columns:
        raise RuntimeError("Apply 20261028091543_align_processing_outputs_with_parser.sql before starting the worker")


def process_next(connection, processor: ChunkingProcessor) -> str | None:
    """Lock one source/document pair until its chunks and status commit together."""
    with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("""
            SELECT d.document_id, d.title, d.domain, d.document_type,
                   d.allowed_roles, d.knowledge_base_active,
                   o.document_metadata, o.elements, o.tables
            FROM public.documents d
            JOIN public.document_processing_outputs o USING (document_id)
            WHERE d.processing_status = 'parsed'
            ORDER BY o.updated_at, d.document_id
            LIMIT 1
            FOR UPDATE OF d, o SKIP LOCKED
        """)
        row = cursor.fetchone()
        if row is None:
            return None
        document_id = row["document_id"]
        log.info("Claimed document %s", document_id)
        try:
            # A savepoint retains old chunks on processing/write failure while
            # the outer row locks remain held for the failed-status update.
            with connection.transaction():
                parsed, warnings = map_output(row, row)
                chunks = processor.process(parsed)["chunks"]
                if not chunks or any(not c["text"].strip() for c in chunks):
                    raise ValueError("Parser output produced no usable chunks")
                for chunk in chunks:
                    chunk["metadata"].update({
                        "document_id": document_id,
                        "chunking_applied": True,
                        "embeddings_created": False,
                        "reading_order_method": parsed["metadata"]["reading_order_method"],
                    })
                ParserChunksRepository(connection).replace_document(document_id, chunks)
                cursor.execute("UPDATE public.documents SET processing_status='chunked' WHERE document_id=%s",
                               (document_id,))
        except Exception:
            cursor.execute("UPDATE public.documents SET processing_status='failed' WHERE document_id=%s",
                           (document_id,))
            log.exception("Chunking failed for document %s; previous chunks retained", document_id)
            status = "failed"
        else:
            status = "chunked"
    if status == "chunked":
        log.info("Chunked document %s: %s chunks", document_id, len(chunks))
        for warning in warnings:
            log.warning("Document %s: %s", document_id, warning)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one eligible document and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    interval = float(os.getenv("CHUNKING_POLL_INTERVAL_SECONDS", "5"))
    if not math.isfinite(interval) or interval <= 0:
        parser.error("CHUNKING_POLL_INTERVAL_SECONDS must be positive and finite")
    processor = ChunkingProcessor({"chunking_strategy": os.getenv("DOCUMENT_CHUNKING_STRATEGY", "sentence")})
    stop = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        try:
            connection = connect_database(autocommit=True)
            try:
                check_schema(connection)
                while not stop.is_set():
                    result = process_next(connection, processor)
                    if args.once:
                        return 1 if result == "failed" else 0
                    if result is None:
                        stop.wait(interval)
            finally:
                close_database_connection(connection)
        except Exception:
            log.exception("Chunking worker database connection/transaction failed")
            if args.once:
                return 1
            stop.wait(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
