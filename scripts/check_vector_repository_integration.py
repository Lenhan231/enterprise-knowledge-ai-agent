#!/usr/bin/env python3
"""Opt-in read-only PostgreSQL check; no model download or test-data writes."""

import json
import os
import sys
from pathlib import Path

import numpy as np
import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.database.document_chunks_repository import DocumentChunkRepository
from core.retrieval.retrieval import RetrievedChunk


def check_connection(conn) -> dict:
    """Caller owns rollback/close; all reads use one read-only snapshot."""
    # Establish a stable, read-only snapshot before pgvector queries its type catalog.
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    register_vector(conn)
    with conn.cursor() as cur:
        # Read the embedding type/dimension and metadata nullability/default.
        cur.execute("""
            SELECT a.attname, t.typname, a.atttypmod, a.attnotnull,
                   pg_get_expr(d.adbin, d.adrelid)
            FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid
            LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
            WHERE a.attrelid = 'public.document_chunks'::regclass
              AND a.attname IN ('embedding', 'metadata') AND NOT a.attisdropped
        """)
        columns = {row[0]: row[1:] for row in cur.fetchall()}

        # List usable plain indexes so their method, columns and operator class
        # can be checked without relying only on index names.
        cur.execute("""
            SELECT am.amname, i.indisunique, i.indnkeyatts,
                   a1.attname, a2.attname, op.opcname
            FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
            JOIN pg_am am ON am.oid = c.relam
            JOIN pg_opclass op ON op.oid = i.indclass[0]
            JOIN pg_attribute a1 ON a1.attrelid = i.indrelid AND a1.attnum = i.indkey[0]
            LEFT JOIN pg_attribute a2 ON a2.attrelid = i.indrelid AND a2.attnum = i.indkey[1]
            WHERE i.indrelid = 'public.document_chunks'::regclass
              AND i.indisvalid AND i.indisready
              AND i.indpred IS NULL AND i.indexprs IS NULL
        """)
        indexes = cur.fetchall()
        schema = {
            "vector_384": columns.get("embedding", ())[:2] == ("vector", 384),
            "metadata_not_null_default": columns.get("metadata") ==
                ("jsonb", -1, True, "'{}'::jsonb"),
            "unique_document_chunk": any(
                row[:5] == ("btree", True, 2, "document_name", "chunk_index")
                for row in indexes),
            "hnsw_cosine": any(
                row[0] == "hnsw" and row[2] == 1 and row[3] == "embedding"
                and row[5] == "vector_cosine_ops" for row in indexes),
        }

        # Count rows that would violate retrieval assumptions or the unique key.
        cur.execute("""
            SELECT count(*), count(*) FILTER (WHERE metadata IS NULL),
                   count(*) FILTER (WHERE NOT COALESCE(
                       jsonb_typeof(metadata -> 'document_id') = 'string'
                       AND metadata ->> 'document_id' ~ '[^[:space:]]', false)),
                   (SELECT count(*) FROM (
                       SELECT 1 FROM public.document_chunks
                       GROUP BY document_name, chunk_index HAVING count(*) > 1
                   ) duplicates)
            FROM public.document_chunks
        """)
        total, null_metadata, missing_ids, duplicates = cur.fetchone()
        report = {"schema": schema, "rows": total, "null_metadata": null_metadata,
                  "missing_document_id": missing_ids, "duplicate_keys": duplicates}

        # Reuse one stored nonzero embedding to avoid model downloads or test writes.
        cur.execute("""
            SELECT embedding::text FROM public.document_chunks
            WHERE vector_norm(embedding) > 0 ORDER BY id LIMIT 1
        """)
        sample = cur.fetchone()
        if sample is None:
            report["retrieval"] = "not_checked_no_nonzero_vector"
            return report

        # Force an exact reference result for deterministic comparison. This does
        # not measure HNSW recall or prove which plan production queries will use.
        cur.execute("SET LOCAL enable_indexscan = off")
        cur.execute("SET LOCAL enable_bitmapscan = off")
        vector = np.fromstring(sample[0].strip("[]"), sep=",", dtype=np.float32)

        # Run the repository's cosine ordering and tie-break as reference SQL.
        cur.execute("""
            SELECT document_name, chunk_index, content, metadata,
                   1 - (embedding <=> %s) AS similarity_score
            FROM public.document_chunks
            ORDER BY embedding <=> %s ASC, id ASC LIMIT %s
        """, (vector, vector, 5))
        rows = cur.fetchall()

    # Exercise the real method on this connection without opening another one.
    repository = DocumentChunkRepository.__new__(DocumentChunkRepository)
    repository.conn = conn
    try:
        actual = repository.similarity_search(vector.tolist(), 5)
        expected = [RetrievedChunk(document_name=name, chunk_index=index,
                                   content=text, metadata={} if metadata is None else metadata,
                                   similarity_score=score)
                    for name, index, text, metadata, score in rows]
        report["retrieval"] = "pass" if actual == expected else "mapping_mismatch"
    except ValidationError:
        report["retrieval"] = "validation_failed"
    return report


def passed(report: dict) -> bool:
    return (all(report["schema"].values()) and report["null_metadata"] == 0
            and report["missing_document_id"] == 0 and report["duplicate_keys"] == 0
            and report["retrieval"] == "pass")


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required (value not displayed).", file=sys.stderr)
        return 2
    conn = None
    try:
        conn = psycopg.connect(
            database_url, connect_timeout=10,
            options="-c default_transaction_read_only=on -c search_path=public,extensions "
                    "-c statement_timeout=15000",
        )
        report = check_connection(conn)
        print(json.dumps(report, sort_keys=True))
        return 0 if passed(report) else 1
    except Exception:
        # Raw database/validation errors may include URLs or source content.
        print("Integration check failed; connection/schema/query error. Details suppressed.",
              file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            try:
                conn.rollback()
            except psycopg.Error:
                # Closing the connection also discards the read-only transaction.
                pass
            finally:
                conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
