#!/usr/bin/env python3
"""Audit manifest metadata propagation into ready document rows and chunks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

DOCUMENT_FIELDS = (
    "domain", "title", "year_or_version", "format", "ingestion_format",
    "official_url", "verification", "rag_value", "document_type",
    "fiscal_year", "company", "source_type", "allowed_roles", "access_scope",
)
CHUNK_FIELDS = (
    "company", "ticker", "domain", "title", "document_type", "fiscal_year",
    "language", "source_type", "year_or_version", "official_url", "allowed_roles",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expected_document_metadata(item: dict) -> dict:
    return {
        **{key: item.get(key) for key in DOCUMENT_FIELDS if key not in {"allowed_roles", "access_scope", "source_type"}},
        "source_type": "public_enterprise_document",
        "allowed_roles": item["rbac"]["allowed_roles"],
        "access_scope": item["rbac"]["classification"],
    }


def expected_chunk_metadata(item: dict) -> dict:
    return {
        **{key: item.get(key) for key in CHUNK_FIELDS if key not in {"allowed_roles", "source_type"}},
        "source_type": "public_enterprise_document",
        "allowed_roles": item["rbac"]["allowed_roles"],
    }


def mismatches(expected: dict, actual: dict, fields: tuple[str, ...]) -> dict:
    return {key: {"expected": expected[key], "actual": actual.get(key)}
            for key in fields if actual.get(key) != expected[key]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "data/vietnam_enterprises/manifest.json")
    parser.add_argument("--raw", type=Path, default=REPO_ROOT / "data/raw/vietnam_enterprises")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "artifacts/evaluation/vinamilk-corpus-metadata-audit.json")
    args = parser.parse_args()
    load_dotenv(REPO_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is not set")

    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    items = manifest["documents"]
    item_by_id = {item["document_id"]: item for item in items}
    ids = list(item_by_id)
    source_hashes = {}
    for item in items:
        matches = list((args.raw / item["ticker"].lower()).glob(item["document_id"].lower() + ".*"))
        if len(matches) == 1:
            source_hashes[item["document_id"]] = sha256(matches[0].read_bytes())

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT document_id, processing_status, domain, title, year_or_version,
                          format, ingestion_format, official_url, verification, rag_value,
                          document_type, fiscal_year, company, source_type, allowed_roles, access_scope
                   FROM public.documents WHERE document_id = ANY(%s)""",
                (ids,),
            )
            documents = {row["document_id"]: row for row in cursor.fetchall()}
            cursor.execute(
                """SELECT d.document_id, c.chunk_index, c.metadata
                   FROM public.documents AS d
                   JOIN public.document_chunks AS c
                     ON c.metadata->>'document_id' = d.document_id
                   WHERE d.document_id = ANY(%s) AND d.processing_status = 'ready'
                   ORDER BY d.document_id, c.chunk_index""",
                (ids,),
            )
            chunk_rows = cursor.fetchall()
            cursor.execute(
                """SELECT current_setting('server_version') AS postgres_version,
                          (SELECT count(*) FROM public.documents) AS all_documents,
                          (SELECT count(*) FROM public.document_chunks) AS all_chunks,
                          count(DISTINCT d.document_id) AS ready_manifest_documents,
                          count(c.id) AS ready_manifest_chunks
                   FROM public.documents AS d
                   LEFT JOIN public.document_chunks AS c
                     ON c.metadata->>'document_id' = d.document_id
                   WHERE d.document_id = ANY(%s) AND d.processing_status = 'ready'""",
                (ids,),
            )
            snapshot = cursor.fetchone()

    document_results = []
    for item in items:
        row = documents.get(item["document_id"])
        result = {"document_id": item["document_id"], "status": row["processing_status"] if row else "missing"}
        if row:
            result["field_mismatches"] = mismatches(expected_document_metadata(item), row, DOCUMENT_FIELDS)
        result["source_sha256"] = source_hashes.get(item["document_id"])
        document_results.append(result)

    chunk_results = []
    rows_by_id: dict[str, list[dict]] = {}
    for row in chunk_rows:
        rows_by_id.setdefault(row["document_id"], []).append(row)
    for document_id, rows in rows_by_id.items():
        expected = expected_chunk_metadata(item_by_id[document_id])
        errors: dict[str, list[dict]] = {}
        for row in rows:
            for key, mismatch in mismatches(expected, row["metadata"], CHUNK_FIELDS).items():
                errors.setdefault(key, []).append({"chunk_index": row["chunk_index"], **mismatch})
        chunk_results.append({
            "document_id": document_id,
            "chunk_count": len(rows),
            "checked_fields_per_chunk": len(CHUNK_FIELDS),
            "field_checks": len(rows) * len(CHUNK_FIELDS),
            "field_mismatch_count": sum(len(values) for values in errors.values()),
            "mismatches_by_field": {
                key: {"count": len(values), "example": values[0]}
                for key, values in errors.items()
            },
        })

    document_checks = sum(len(DOCUMENT_FIELDS) for result in document_results if result["status"] != "missing")
    document_mismatch_count = sum(len(result.get("field_mismatches", {})) for result in document_results)
    chunk_checks = sum(result["field_checks"] for result in chunk_results)
    chunk_mismatch_count = sum(result["field_mismatch_count"] for result in chunk_results)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation": "manifest metadata propagation, not automatic metadata extraction accuracy",
        "manifest": str(args.manifest.relative_to(REPO_ROOT)) if args.manifest.is_relative_to(REPO_ROOT) else args.manifest.name,
        "manifest_sha256": sha256(manifest_bytes),
        "company": manifest["company"],
        "database_snapshot": snapshot,
        "summary": {
            "manifest_document_count": len(items),
            "documents_found": len(documents),
            "documents_ready": sum(row["processing_status"] == "ready" for row in documents.values()),
            "documents_missing_or_not_ready": sum(result["status"] != "ready" for result in document_results),
            "document_metadata_field_checks": document_checks,
            "document_metadata_mismatches": document_mismatch_count,
            "ready_chunks_checked": sum(row["chunk_count"] for row in chunk_results),
            "chunk_metadata_field_checks": chunk_checks,
            "chunk_metadata_mismatches": chunk_mismatch_count,
        },
        "document_results": document_results,
        "chunk_results": chunk_results,
        "limitations": "Checks exact propagation of manifest-declared metadata for currently stored public corpus rows. It does not establish automatic metadata extraction accuracy or content/heading correctness. Missing or non-ready manifest items are reported separately, not treated as correct.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": report["summary"]}, ensure_ascii=False, indent=2))
    return 1 if document_mismatch_count or chunk_mismatch_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
