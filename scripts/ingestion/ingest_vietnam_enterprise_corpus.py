#!/usr/bin/env python3
"""Parse, embed, and persist the manifest-backed Vietnam public corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.database.document_chunks_repository import DocumentChunkRepository  # noqa: E402
from core.database.document_repository import DocumentRepository  # noqa: E402
from core.database.processed_chunks_repository import ProcessedChunksRepository  # noqa: E402
from core.document_processing.ingest_documents import Ingestion  # noqa: E402
from core.database.structured_store import StructuredDataStore  # noqa: E402
from core.embeddings import EmbeddingService  # noqa: E402
from scripts.ingestion.source_downloaders.registry import source_extension  # noqa: E402


def ingest_one_document(
    item: dict,
    input_path: Path,
    output_root: Path,
    ingestor: Ingestion,
    embedding_service: EmbeddingService,
    documents: DocumentRepository,
    chunks_repository: DocumentChunkRepository,
    parsed_chunks_repository: ProcessedChunksRepository,
    storage,
    bucket: str,
) -> tuple[int, int, int]:
    """Keep a seed document out of retrieval until chunks and tables are ready."""
    document_id = item["document_id"]
    source_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
    expected_sha256 = item.get("source_sha256")
    if expected_sha256 and source_sha256 != expected_sha256:
        raise ValueError(
            f"{document_id}: source SHA-256 mismatch; refusing to ingest changed PDF bytes"
        )
    storage_path = None
    if input_path.suffix.lower() == ".pdf":
        storage_path = f"{document_id}/{input_path.name}"
        storage.storage.from_(bucket).upload(
            storage_path, input_path.read_bytes(),
            {"content-type": "application/pdf", "upsert": "true"},
        )
    documents.upsert_document({
        **item,
        "company": item["company"],
        "source_type": "public_enterprise_document",
        "allowed_roles": item["rbac"]["allowed_roles"],
        "storage_path": storage_path,
        "processing_status": "processing",
    })
    try:
        chunks, extracted_tables = ingestor.ingestion(
            input_path,
            output_root / item["ticker"].lower(),
            document_id=document_id,
            extra_metadata={
                "company": item["company"],
                "ticker": item["ticker"],
                "domain": item["domain"],
                "title": item["title"],
                "document_type": item["document_type"],
                "fiscal_year": item["fiscal_year"],
                "language": item["language"],
                "source_type": "public_enterprise_document",
                "year_or_version": item["year_or_version"],
                "source_url": item["source_url"],
                "source_sha256": source_sha256,
                "rbac": item["rbac"],
            },
            include_tables=True,
        )
        if not chunks:
            raise ValueError("No text chunks extracted from source")
        parsed_chunks_repository.replace_document(document_id, [
            {
                "text": chunk.page_content,
                "metadata": {**chunk.metadata, "source_sha256": source_sha256},
            }
            for chunk in chunks
        ])
        parsed_chunks_repository.set_status(document_id, "embedding")
        vectors = embedding_service.embed_documents([chunk.page_content for chunk in chunks])
        for chunk in chunks:
            chunk.metadata["allowed_roles"] = item["rbac"]["allowed_roles"]
            chunk.metadata["embedding_model"] = embedding_service.model_name
        rows = [
            (input_path.name, chunk.metadata["chunk_index"], chunk.page_content, chunk.metadata, vector)
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        chunks_repository.replace_document(document_id, rows)
        parsed_chunks_repository.set_status(document_id, "embedded")
        structured_store = StructuredDataStore()
        try:
            table_count, record_count = structured_store.save_document_tables(
                document_id, item["title"], extracted_tables
            )
        finally:
            structured_store.close()
        documents.update_processing_status(document_id, "ready")
        return len(rows), table_count, record_count
    except Exception:
        documents.update_processing_status(document_id, "failed")
        parsed_chunks_repository.set_status(document_id, "failed", "Seed ingestion did not complete")
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path, default=Path("data/raw/vietnam_enterprises")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/processed/vietnam_enterprises")
    )
    parser.add_argument(
        "--ids", nargs="+", help="Ingest only these manifest document IDs"
    )
    parser.add_argument(
        "--chunking-strategy", choices=("sentence", "fixed"), default="sentence",
        help="Use paragraph/sentence boundaries (default) or fixed character windows for PDF chunks.",
    )
    args = parser.parse_args()
    manifest_path = REPO_ROOT / "data/vietnam_enterprises/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if args.ids:
        by_id = {item["document_id"]: item for item in manifest["documents"]}
        unknown = sorted(set(args.ids) - by_id.keys())
        if unknown:
            parser.error(f"unknown document IDs: {', '.join(unknown)}")
        manifest["documents"] = [by_id[document_id] for document_id in args.ids]
    embedding_service = EmbeddingService()
    ingestor = Ingestion(embedding_service, chunking_strategy=args.chunking_strategy)
    bucket = os.getenv("SUPABASE_DOCUMENT_BUCKET", "enterprise-documents")
    storage = None
    if any(item.get("format", "").upper() == "PDF" for item in manifest["documents"]):
        from supabase import create_client

        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not supabase_url or not supabase_key:
            parser.error("SUPABASE_URL and SUPABASE_SECRET_KEY are required to archive source PDFs")
        storage = create_client(supabase_url, supabase_key)
    documents = DocumentRepository()
    chunks_repository = DocumentChunkRepository()
    parsed_chunks_repository = ProcessedChunksRepository()
    failures = 0

    try:
        for item in manifest["documents"]:
            input_path = (
                args.input / item["ticker"].lower()
                / (item["document_id"].lower() + source_extension(item))
            )
            if not input_path.is_file():
                print(f"missing    {input_path}", file=sys.stderr)
                failures += 1
                continue

            try:
                chunk_count, table_count, record_count = ingest_one_document(
                    item,
                    input_path,
                    args.output,
                    ingestor,
                    embedding_service,
                    documents,
                    chunks_repository,
                    parsed_chunks_repository,
                    storage,
                    bucket,
                )
                print(
                    f"ingested   {item['document_id']}: {chunk_count} chunks, "
                    f"{table_count} tables/{record_count} rows"
                )
            except Exception as error:
                print(f"failed     {item['document_id']}: {error}", file=sys.stderr)
                failures += 1
    finally:
        chunks_repository.close()
        parsed_chunks_repository.close()
        documents.close()

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
