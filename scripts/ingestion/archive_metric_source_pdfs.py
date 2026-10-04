#!/usr/bin/env python3
"""Archive and parser-backfill public PDFs that support verified metrics."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
import fitz

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from core.database.document_repository import DocumentRepository  # noqa: E402
from core.database.processed_chunks_repository import ProcessedChunksRepository  # noqa: E402
from scripts.processing.process_vinamilk_business_metrics import process_business_source  # noqa: E402

MAX_PDF_BYTES = 50 * 1024 * 1024
DEFAULT_BUCKET = "enterprise-documents"


def _normalized(text: str) -> str:
    return " ".join(re.sub(r"\s+", " ", text).casefold().split())


def verify_source(document_id: str, content: bytes, evidence: list[dict]) -> str:
    """Require every verified quote to occur on its recorded physical page."""
    source_hash = hashlib.sha256(content).hexdigest()
    with fitz.open(stream=content, filetype="pdf") as pdf:
        unmatched = [
            row for row in evidence
            if not 1 <= row["page_number"] <= len(pdf)
            or _normalized(row["source_quote"])
            not in _normalized(pdf[row["page_number"] - 1].get_text())
        ]
    if unmatched:
        raise ValueError(
            f"{document_id}: {len(unmatched)} verified quotes do not match the local PDF pages"
        )
    return source_hash


def archive_one(document: dict, path: Path, repository: DocumentRepository,
                storage, bucket: str, parsed_repository: ProcessedChunksRepository) -> dict:
    content = path.read_bytes()
    if len(content) > MAX_PDF_BYTES:
        raise ValueError(f"{document['document_id']}: PDF exceeds the bucket's 50 MiB limit")
    if not content.startswith(b"%PDF-"):
        raise ValueError(f"{document['document_id']}: file is not a PDF")

    with repository.conn.transaction(), repository.conn.cursor() as cursor:
        cursor.execute(
            """SELECT d.title, d.company, d.source_type, d.format, d.processing_status,
                      d.storage_path, d.allowed_roles,
                      array_agg(DISTINCT c.metadata->>'source_sha256')
                        FILTER (WHERE c.metadata->>'source_sha256' IS NOT NULL) AS known_source_hashes
               FROM public.documents d
               JOIN public.business_metric_evidence e
                 ON e.source_document_id = d.document_id AND e.status = 'verified'
               LEFT JOIN public.document_chunks c
                 ON c.metadata->>'document_id' = d.document_id
               WHERE d.document_id = %s
               GROUP BY d.document_id""",
            (document["document_id"],),
        )
        stored = cursor.fetchone()
        if (not stored or stored["company"] != document["company"]
                or stored["source_type"] != "public_enterprise_document"
                or stored["format"] != "PDF" or stored["processing_status"] != "ready"):
            raise ValueError(f"{document['document_id']}: expected a ready public PDF with verified metrics")
        evidence = cursor.execute(
            """SELECT page_number, source_quote
               FROM public.business_metric_evidence
               WHERE source_document_id = %s AND status = 'verified'
               ORDER BY page_number, id""",
            (document["document_id"],),
        ).fetchall()

    source_hash = verify_source(document["document_id"], content, evidence)
    known_hashes = set(stored["known_source_hashes"] or [])
    if known_hashes and known_hashes != {source_hash}:
        raise ValueError(f"{document['document_id']}: local PDF SHA-256 differs from indexed source metadata")
    storage_path = f"{document['document_id']}/{path.name}"
    if stored["storage_path"] not in (None, storage_path):
        raise ValueError(f"{document['document_id']}: an archive already exists at another Storage path")

    with parsed_repository.connection.transaction(), parsed_repository.connection.cursor() as cursor:
        cursor.execute(
            """SELECT count(*), count(*) FILTER (
                      WHERE metadata->>'source_sha256' = %s::text
                  )
               FROM public.processed_document_chunks WHERE document_id = %s""",
            (source_hash, document["document_id"]),
        )
        parser_count, matching_parser_count = cursor.fetchone()
    parser_chunks = None
    if parser_count and parser_count == matching_parser_count:
        parser_chunk_count = matching_parser_count
    else:
        processed, parsed_hash = process_business_source(document["document_id"], document, path)
        if parsed_hash != source_hash or not processed.get("chunks"):
            raise ValueError(f"{document['document_id']}: parser result is empty or has a different source hash")
        parser_chunks = [
            {"text": chunk["text"], "metadata": chunk["metadata"]}
            for chunk in processed["chunks"]
        ]
        parser_chunk_count = len(parser_chunks)

    bucket_api = storage.storage.from_(bucket)
    existing_objects = bucket_api.list(document["document_id"], {"limit": 100})
    object_exists = any(item.get("name") == path.name for item in existing_objects)
    if not object_exists:
        bucket_api.upload(
            storage_path, content,
            {"content-type": "application/pdf", "upsert": "true"},
        )
    archived = bucket_api.download(storage_path)
    if hashlib.sha256(archived).hexdigest() != source_hash:
        raise ValueError(f"{document['document_id']}: Storage read-back hash mismatch")

    if parser_chunks is not None:
        parsed_repository.replace_document(document["document_id"], parser_chunks)
    indexed_count = repository.archive_public_metric_source(
        document["document_id"], document["company"], storage_path, source_hash,
    )
    return {
        "document_id": document["document_id"],
        "source_sha256": source_hash,
        "source_bytes": len(content),
        "verified_quotes": len(evidence),
        "parser_chunks": parser_chunk_count,
        "indexed_chunks_fingerprinted": indexed_count,
        "storage_path": storage_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="+", required=True, help="Manifest PDF IDs with verified business metrics")
    parser.add_argument("--input", type=Path, default=ROOT / "data/raw/vietnam_enterprises")
    parser.add_argument("--bucket", default=os.getenv("SUPABASE_DOCUMENT_BUCKET", DEFAULT_BUCKET))
    args = parser.parse_args()

    import json

    manifest = json.loads((ROOT / "data/vietnam_enterprises/manifest.json").read_text(encoding="utf-8"))
    documents = {row["document_id"]: row for row in manifest["documents"]}
    unknown = set(args.ids) - documents.keys()
    if unknown:
        parser.error(f"Unknown manifest document IDs: {', '.join(sorted(unknown))}")
    if not os.getenv("SUPABASE_URL") or not (
        os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    ):
        parser.error("SUPABASE_URL and SUPABASE_SECRET_KEY are required")

    from supabase import create_client

    storage = create_client(
        os.environ["SUPABASE_URL"],
        os.getenv("SUPABASE_SECRET_KEY") or os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    repository = DocumentRepository()
    parsed_repository = ProcessedChunksRepository()
    failures = 0
    try:
        for document_id in args.ids:
            document = documents[document_id]
            if document.get("format", "PDF").upper() != "PDF":
                parser.error(f"{document_id} is not a PDF")
            path = args.input / document["ticker"].lower() / f"{document_id.lower()}.pdf"
            try:
                result = archive_one(document, path, repository, storage, args.bucket, parsed_repository)
                print(json.dumps(result, ensure_ascii=False))
            except Exception as error:
                failures += 1
                print(f"{document_id}: {type(error).__name__}: {error}", file=sys.stderr)
    finally:
        parsed_repository.close()
        repository.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
