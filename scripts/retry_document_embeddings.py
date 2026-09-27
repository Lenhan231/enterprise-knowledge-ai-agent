#!/usr/bin/env python3
"""Rebuild retrieval vectors for a parsed upload without rerunning OCR/layout."""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_id", help="Uploaded document ID with persisted parsed chunks")
    args = parser.parse_args()

    from core.database.document_chunks_repository import DocumentChunkRepository
    from core.database.document_repository import DocumentRepository
    from core.database.processed_chunks_repository import ProcessedChunksRepository
    from core.embeddings.embedding_service import EmbeddingService

    parsed = ProcessedChunksRepository()
    vectors = DocumentChunkRepository()
    documents = DocumentRepository()
    try:
        rows = parsed.get_document(args.document_id)
        if not rows:
            raise ValueError(f"No persisted parsed chunks found for {args.document_id}")
        parsed.set_status(args.document_id, "embedding")
        embedder = EmbeddingService()
        from core.utils.token_counter import TokenCounter

        counter = TokenCounter(embedder.model_name)
        chunks = []
        for row in rows:
            for text in counter.split_text(
                row["content"], max_sequence_tokens=embedder.max_sequence_length,
            ):
                metadata = dict(row["metadata"] or {})
                metadata.update({
                    "chunk_index": len(chunks),
                    "token_count": counter.count(text),
                    "embedding_model": embedder.model_name,
                })
                chunks.append((args.document_id, len(chunks), text, metadata, None))
        embeddings = embedder.embed_documents([chunk[2] for chunk in chunks])
        chunks = [(*chunk[:4], embedding) for chunk, embedding in zip(chunks, embeddings, strict=True)]
        vectors.replace_document(args.document_id, chunks)
        parsed.replace_document(args.document_id, [
            {"text": chunk[2], "metadata": chunk[3]} for chunk in chunks
        ])
        parsed.set_status(args.document_id, "embedded")
        documents.update_processing_status(args.document_id, "ready")
        print(f"Embedded {len(chunks)} saved chunks for {args.document_id} using {embedder.model_name}")
        return 0
    except Exception as error:
        try:
            parsed.set_status(args.document_id, "failed", str(error))
            documents.update_processing_status(args.document_id, "failed")
        except Exception:
            pass
        raise
    finally:
        parsed.close()
        vectors.close()
        documents.close()


if __name__ == "__main__":
    raise SystemExit(main())
