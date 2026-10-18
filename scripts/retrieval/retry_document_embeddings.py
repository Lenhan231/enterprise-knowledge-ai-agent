#!/usr/bin/env python3
"""Rebuild explicitly selected uploads from retained parser output; never rerun OCR."""
import argparse
import sys
from contextlib import ExitStack
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))


def retry_document(document_id, parsed, vectors, documents, embedder, counter):
    from core.tokenization.embedding_chunker import build_embedding_chunks

    document = next((row for row in documents.list_knowledge_documents()
                     if row["document_id"] == document_id), None)
    if not document or document.get("source_type") != "user_upload":
        raise ValueError("Retry requires an existing uploaded document")
    if document.get("processing_status") not in {"failed", "parsed"}:
        raise ValueError("Retry only supports failed or parsed uploads; ready indexes are preserved")
    rows = parsed.get_document(document_id, company=document["company"])
    if not rows:
        raise ValueError("No retained parser output for this document")
    roles = list(document.get("allowed_roles") or [])
    if not roles:
        raise ValueError("Document must have at least one allowed reader role")
    filename = Path(str((rows[0].get("metadata") or {}).get("filename") or "")).name
    if not filename:
        raise ValueError("Retained parser output has no source filename")
    documents.update_processing_status(document_id, "processing")
    try:
        chunks = build_embedding_chunks(rows, counter, embedder.max_sequence_length, embedder.model_name)
        if not chunks:
            raise ValueError("Retained parser output has no embeddable text")
        for chunk in chunks:
            chunk["metadata"].update(document_id=document_id, allowed_roles=roles)
        embeddings = embedder.embed_documents([chunk["text"] for chunk in chunks])
        if len(embeddings) != len(chunks):
            raise ValueError("Embedding count differs from chunk count")
        vectors.replace_document(document_id, [
            (filename, index, chunk["text"], chunk["metadata"], embedding)
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        ])
        documents.update_processing_status(document_id, "ready")
    except Exception:
        documents.update_processing_status(document_id, "failed")
        raise
    # Parser chunks stay unchanged; they remain reusable across embedding models.
    return {"document_id": document_id, "parser_chunks": len(rows),
            "indexed_chunks": len(chunks), "model": embedder.model_name,
            "max_sequence_length": embedder.max_sequence_length}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_ids", nargs="+", help="Explicit failed/parsed upload IDs")
    args = parser.parse_args()
    from core.database.document_chunks_repository import DocumentChunkRepository
    from core.database.document_repository import DocumentRepository
    from core.database.parser_chunks_repository import ParserChunksRepository
    from core.embeddings.embedding_service import EmbeddingService
    from core.tokenization.token_counter import TokenCounter
    import json

    embedder = EmbeddingService()
    counter = TokenCounter(embedder.model_name)
    with ExitStack() as stack:
        parsed = ParserChunksRepository()
        stack.callback(parsed.close)
        vectors = DocumentChunkRepository()
        stack.callback(vectors.close)
        documents = DocumentRepository()
        stack.callback(documents.close)
        for document_id in dict.fromkeys(args.document_ids):
            print(json.dumps(retry_document(document_id, parsed, vectors, documents,
                                           embedder, counter)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
