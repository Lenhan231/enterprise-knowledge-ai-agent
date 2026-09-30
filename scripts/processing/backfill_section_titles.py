#!/usr/bin/env python3
"""Backfill section titles only when current parsing exactly matches stored chunks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from core.document_processing.processors.pdf_processor import PDFProcessor  # noqa: E402
from core.embeddings.embedding_service import (  # noqa: E402
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_MAX_SEQUENCE_LENGTH,
)
from core.utils.token_counter import TokenCounter  # noqa: E402


def build_parsed_rows(item: dict, source: Path, counter: TokenCounter) -> list[dict]:
    parsed = PDFProcessor({
        "paddle_layout": False,
        "ocr_fallback": True,
        "ocr_language": "vie+eng",
        "extract_tables": False,
        "chunking_strategy": "sentence",
        "chunk_size": 1200,
        "chunk_overlap": 150,
    }).process({
        "content": source.read_bytes(),
        "metadata": {"document_id": item["document_id"]},
    })["chunks"]

    rows = []
    for chunk in parsed:
        for text in counter.split_text(
            chunk["text"], max_sequence_tokens=EMBEDDING_MAX_SEQUENCE_LENGTH,
        ):
            rows.append({
                "chunk_index": len(rows),
                "content": text,
                "section_title": chunk["metadata"].get("section_title"),
                "page_number": chunk["metadata"].get("page_number"),
            })
    return rows


def plan_updates(parsed_rows: list[dict], stored_rows: list[dict]) -> tuple[list[dict], str | None]:
    """Return exact-match section updates, or a reason to skip the document."""
    if len(parsed_rows) != len(stored_rows):
        return [], "chunk_count_mismatch"
    for parsed, stored in zip(parsed_rows, stored_rows, strict=True):
        if parsed["chunk_index"] != stored["chunk_index"] or parsed["content"] != stored["content"]:
            return [], f"content_mismatch_at_chunk_{parsed['chunk_index']}"

    updates = []
    for parsed, stored in zip(parsed_rows, stored_rows, strict=True):
        if parsed["section_title"] and not (stored["metadata"].get("section_title") or "").strip():
            updates.append({
                "id": stored["id"],
                "chunk_index": parsed["chunk_index"],
                "page_number": parsed["page_number"],
                "old_section_title": stored["metadata"].get("section_title"),
                "new_section_title": parsed["section_title"],
                "content": stored["content"],
            })
    return updates, None


def backfill(document_ids: list[str], apply: bool, output: Path) -> dict:
    load_dotenv(REPO_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    manifest = json.loads((REPO_ROOT / "data/vietnam_enterprises/manifest.json").read_text(encoding="utf-8"))
    items = {item["document_id"]: item for item in manifest["documents"]}
    unknown = sorted(set(document_ids) - items.keys())
    if unknown:
        raise ValueError(f"Unknown manifest document IDs: {', '.join(unknown)}")

    counter = TokenCounter(DEFAULT_EMBEDDING_MODEL)
    documents = []
    backup = []
    backup_path = output.with_name(output.stem + "-backup.json")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        for document_id in document_ids:
            item = items[document_id]
            if item.get("format", "").lower() != "pdf":
                documents.append({"document_id": document_id, "status": "skipped_non_pdf"})
                continue
            source = (
                REPO_ROOT / "data/raw/vietnam_enterprises"
                / item["ticker"].lower()
                / (document_id.lower() + ".pdf")
            )
            if not source.is_file():
                documents.append({"document_id": document_id, "status": "skipped_source_missing"})
                continue

            parsed = build_parsed_rows(item, source, counter)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT c.id, c.chunk_index, c.content, c.metadata
                       FROM public.document_chunks c
                       JOIN public.documents d ON d.document_id = c.metadata->>'document_id'
                       WHERE c.metadata->>'document_id' = %s
                         AND d.company = %s AND d.source_type = 'public_enterprise_document'
                         AND d.processing_status = 'ready'
                       ORDER BY c.chunk_index""",
                    (document_id, item["company"]),
                )
                stored = cursor.fetchall()
            updates, mismatch = plan_updates(parsed, stored)
            entry = {
                "document_id": document_id,
                "stored_chunks": len(stored),
                "parsed_chunks": len(parsed),
                "exact_content_match": mismatch is None,
                "status": "planned" if mismatch is None else "skipped_mismatch",
                "mismatch": mismatch,
                "eligible_updates": len(updates),
            }
            if apply and mismatch is None and updates:
                backup.extend({
                    "document_id": document_id,
                    **{key: update[key] for key in (
                        "id", "chunk_index", "old_section_title", "new_section_title",
                    )},
                } for update in updates)
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                with connection.transaction(), connection.cursor() as cursor:
                    for update in updates:
                        cursor.execute(
                            """UPDATE public.document_chunks
                               SET metadata = metadata || jsonb_build_object('section_title', %s::text)
                               WHERE id = %s AND metadata->>'document_id' = %s
                                 AND chunk_index = %s AND content = %s
                                 AND nullif(btrim(metadata->>'section_title'), '') IS NULL
                                 AND EXISTS (SELECT 1 FROM public.documents d
                                     WHERE d.document_id = %s AND d.company = %s
                                       AND d.source_type = 'public_enterprise_document'
                                       AND d.processing_status = 'ready')""",
                            (update["new_section_title"], update["id"], document_id,
                             update["chunk_index"], update["content"], document_id,
                             item["company"]),
                        )
                        if cursor.rowcount != 1:
                            raise RuntimeError(
                                f"Concurrent or changed chunk detected: {document_id}/{update['chunk_index']}"
                            )
                entry["status"] = "applied"
            documents.append(entry)

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if apply else "dry_run",
        "metadata_only": True,
        "documents": documents,
        "eligible_updates": sum(row["eligible_updates"] for row in documents),
        "applied_updates": sum(row.get("eligible_updates", 0) for row in documents if row["status"] == "applied"),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="+", required=True, help="Manifest PDF document IDs to inspect")
    parser.add_argument("--apply", action="store_true", help="Write section_title only after exact chunk/content match")
    parser.add_argument(
        "--output", type=Path,
        default=REPO_ROOT / "artifacts/evaluation/section-title-backfill.json",
    )
    args = parser.parse_args()
    try:
        report = backfill(args.ids, args.apply, args.output)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps({
        "output": str(args.output),
        "mode": report["mode"],
        "eligible_updates": report["eligible_updates"],
        "applied_updates": report["applied_updates"],
        "documents": report["documents"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
