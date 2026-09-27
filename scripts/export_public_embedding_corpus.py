#!/usr/bin/env python3
"""Export manifest-listed public passages for credential-free cloud evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]


def manifest_document_ids(path: Path) -> list[str]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    documents = manifest["documents"] if isinstance(manifest, dict) else manifest
    return [item["document_id"] for item in documents]


def export_rows(database_url: str, document_ids: list[str]) -> list[dict]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        rows = connection.execute(
            """
            SELECT c.content, c.metadata->>'document_id' AS document_id,
                   d.allowed_roles
            FROM public.document_chunks AS c
            JOIN public.documents AS d
              ON d.document_id = c.metadata->>'document_id'
            WHERE d.document_id = ANY(%s)
              AND coalesce(d.processing_status, 'ready') = 'ready'
              AND nullif(btrim(c.content), '') IS NOT NULL
            ORDER BY d.document_id, c.chunk_index, c.id
            """,
            (document_ids,),
        ).fetchall()

    unknown = sorted({row["document_id"] for row in rows} - set(document_ids))
    if unknown:
        raise ValueError(f"Database returned IDs outside the public manifest: {unknown}")
    return [
        {
            "document_id": row["document_id"],
            "allowed_roles": sorted(row["allowed_roles"] or []),
            "content": row["content"],
        }
        for row in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "data/evaluation/vinamilk_public_embedding_corpus.jsonl",
    )
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "data/vietnam_enterprises/manifest.json")
    args = parser.parse_args()
    load_dotenv(REPO_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required")

    rows = export_rows(database_url, manifest_document_ids(args.manifest))
    if not rows:
        parser.error("No ready public manifest chunks found")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    args.output.write_text(payload, encoding="utf-8")
    manifest_hash = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    corpus_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    metadata = {
        "format": "vinamilk-public-embedding-corpus/v1",
        "source": "ready database chunks restricted to document IDs in the public manifest",
        "manifest_sha256": manifest_hash,
        "corpus_sha256": corpus_hash,
        "chunk_count": len(rows),
        "document_count": len({row["document_id"] for row in rows}),
        "role_policy": "preserve each source document allowed_roles; apply eligibility before ranking",
    }
    metadata_path = args.output.with_suffix(args.output.suffix + ".metadata.json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **metadata}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
