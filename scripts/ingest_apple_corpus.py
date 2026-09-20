#!/usr/bin/env python3
"""Parse, chunk, embed, and persist the five-document Apple vertical slice."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.database.document_chunks_repository import DocumentChunkRepository  # noqa: E402
from core.document_processing.ingest_documents import Ingestion  # noqa: E402
from download_apple_corpus import DEFAULT_MANIFEST, read_manifest, safe_filename  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/raw/apple"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/apple"))
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_rows = read_manifest(args.manifest)
    manifest_by_filename = {safe_filename(row): row for row in manifest_rows}
    pdfs = sorted(args.input.glob("**/*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found below {args.input}")

    ingestor = Ingestion()
    repository = DocumentChunkRepository()
    try:
        for pdf in pdfs:
            manifest = manifest_by_filename.get(pdf.name)
            if manifest is None:
                raise ValueError(f"Downloaded PDF is not represented in manifest: {pdf}")
            domain = pdf.parent.name
            output_dir = args.output / domain
            chunks = ingestor.ingestion(
                pdf,
                output_dir,
                document_id=manifest["document_id"],
                extra_metadata={
                    "domain": domain,
                    "title": manifest["title"],
                    "year_or_version": manifest["year_or_version"],
                    "official_url": manifest["official_url"],
                },
            )
            embeddings = ingestor.embedding_service.embed_documents(
                [chunk.page_content for chunk in chunks]
            )
            rows = [
                (
                    pdf.name,
                    chunk.metadata["chunk_index"],
                    chunk.page_content,
                    chunk.metadata,
                    embedding,
                )
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            ]
            repository.replace_document(pdf.name, rows)
            print(f"ingested {pdf.name}: {len(rows)} chunks")
    finally:
        repository.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
