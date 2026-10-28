#!/usr/bin/env python3
"""Preview stored parser output as chunks, without inference or database writes."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from core.chunking.processor import ChunkingProcessor
from core.chunking.processing_output import map_output


def preview(row: dict, document: dict, counter, model: str, limit: int = 512) -> dict:
    from core.tokenization.embedding_chunker import build_embedding_chunks

    parsed, warnings = map_output(row, document)
    parser_chunks = ChunkingProcessor().process(parsed)["chunks"]
    if not parser_chunks:
        raise ValueError("Parser output produced no text/table chunks")
    for chunk in parser_chunks:
        chunk["metadata"]["parser_chunk_index"] = chunk["metadata"]["chunk_index"]
        chunk["metadata"].update({"chunking_applied": True, "embeddings_created": False})
    bounded = build_embedding_chunks(parser_chunks, counter, limit - 4, model)
    counts = [len(counter.tokenizer.encode("passage: " + c["text"], add_special_tokens=True)) for c in bounded]
    if not bounded or any(n > limit for n in counts):
        raise ValueError("Final passages exceed the E5 input budget or are empty")
    for chunk, count in zip(bounded, counts, strict=True):
        chunk["metadata"]["prefixed_input_tokens"] = count
    return {
        "dry_run": True,
        "database_writes": False,
        "embeddings_created": False,
        "document": document,
        "source_output": row,
        "normalized_metadata": parsed["metadata"],
        "warnings": warnings + [
            "source_elements identifies the contributing parser group, not exact per-fragment character spans.",
            "Figures are retained in source_output but excluded from text embedding previews.",
        ],
        "summary": {
            "text_elements": sum(e["metadata"].get("element_type") != "table" for e in parsed["elements"]),
            "tables": len(parsed["tables"]),
            "figures": (sum((e.get("metadata") or {}).get("element_type", e.get("element_type")) in {"figure", "seal"}
                            for e in row["elements"]) if "elements" in row else len(row["figures"])),
            "parser_chunks": len(parser_chunks),
            "embedding_passages": len(bounded), "max_prefixed_input_tokens": max(counts),
            "input_token_limit": limit, "model": model,
            "chunk_types": dict(Counter(c["metadata"].get("element_type", "text") for c in parser_chunks)),
            "chunks_without_page": sum(c["metadata"].get("page_number") is None for c in parser_chunks),
            "reading_order_method": parsed["metadata"]["reading_order_method"],
        },
        "parser_chunks": parser_chunks,
        "embedding_passages": bounded,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_id")
    parser.add_argument("--output", type=Path, required=True, help="Local JSON report; also writes a Markdown preview")
    args = parser.parse_args()
    markdown_path = args.output.with_suffix(".md")
    if args.output.suffix != ".json" or args.output.exists() or markdown_path.exists():
        parser.error("Use a new .json output path; existing reports are not overwritten")

    from dotenv import load_dotenv
    import psycopg
    from psycopg.rows import dict_row
    from transformers import AutoTokenizer
    from core.embeddings.settings import E5_MODEL, E5_REVISION
    from core.tokenization.token_counter import TokenCounter

    load_dotenv(ROOT / ".env")
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10,
                        options="-c default_transaction_read_only=on -c statement_timeout=15000",
                        row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.document_processing_outputs WHERE document_id=%s", (args.document_id,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError("No stored parser output for this document_id")
            cursor.execute("""SELECT document_id,title,domain,document_type,allowed_roles,
                              processing_status,knowledge_base_active FROM public.documents WHERE document_id=%s""",
                           (args.document_id,))
            document = cursor.fetchone()
            if document is None:
                raise ValueError("Document record is missing")

    counter = TokenCounter.__new__(TokenCounter)
    counter.tokenizer = AutoTokenizer.from_pretrained(E5_MODEL, revision=E5_REVISION, use_fast=True, local_files_only=True)
    report = preview(row, document, counter, E5_MODEL)
    report["summary"]["tokenizer_revision"] = E5_REVISION
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    with markdown_path.open("x", encoding="utf-8") as handle:
        handle.write(f"# Chunking preview: {document['title']}\n\nRead-only dry run; no embeddings created.\n\n")
        handle.write("```json\n" + json.dumps(report["summary"], ensure_ascii=False, indent=2) + "\n```\n\n")
        for warning in report["warnings"]:
            handle.write(f"- {warning}\n")
        for chunk in report["embedding_passages"]:
            m = chunk["metadata"]
            handle.write(f"\n## Passage {m['chunk_index']} — page {m.get('page_number')} — {m['prefixed_input_tokens']} input tokens\n\n")
            handle.write(f"Parser chunk: {m['parser_chunk_index']}; sources: {json.dumps(m.get('source_elements', []))}\n\n")
            handle.write(chunk["text"] + "\n")
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"Reports: {args.output} and {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
