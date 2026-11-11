#!/usr/bin/env python3
"""Re-embed every indexed passage with the configured model, atomically on apply."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
from core.embeddings.embedding_service import EmbeddingService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Atomically replace stored embeddings")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    load_dotenv(REPO_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        register_vector(connection)
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, content FROM public.document_chunks ORDER BY id")
            rows = cursor.fetchall()
    if not rows:
        raise SystemExit("No document chunks found")

    embedding_service = EmbeddingService()
    vectors = []
    for offset in range(0, len(rows), args.batch_size):
        batch = rows[offset : offset + args.batch_size]
        vectors.extend(embedding_service.embed_documents([row["content"] for row in batch]))
        print(f"embedded {min(offset + len(batch), len(rows))}/{len(rows)}")
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1 or dimensions != {384}:
        raise SystemExit(f"Expected vector(384), received dimensions {sorted(dimensions)}")

    print(f"prepared {len(rows)} vectors using {embedding_service.model_name}")
    if not args.apply:
        print("dry run only; pass --apply to replace the stored vectors")
        return 0

    model_metadata = Jsonb({"embedding_model": embedding_service.model_name, "embedding_dimension": 384})
    with psycopg.connect(database_url) as connection:
        register_vector(connection)
        with connection.transaction(), connection.cursor() as cursor:
            cursor.executemany(
                """UPDATE public.document_chunks
                   SET embedding = %s, metadata = metadata || %s
                   WHERE id = %s""",
                [(vector, model_metadata, row["id"]) for row, vector in zip(rows, vectors, strict=True)],
            )
    print(f"updated {len(rows)} document chunk embeddings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
