#!/usr/bin/env python3
"""Read-only audit of verified business KPI quotes and parser/index provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import fitz
from dotenv import load_dotenv
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from core.analytics.business_metric_extraction import source_quote_matches  # noqa: E402
from core.database.connection_limit import close_database_connection, connect_database  # noqa: E402

DEFAULT_OUTPUT = ROOT / "artifacts/evaluation/analytics/verified-business-metric-provenance-audit.json"


def audit(base_dir: Path | None = None) -> dict:
    """Check all active-company verified rows against their PDF and saved chunks."""
    load_dotenv(ROOT / ".env")
    root = base_dir or ROOT
    manifest = json.loads(
        (root / "data/vietnam_enterprises/manifest.json").read_text(encoding="utf-8"),
    )
    company = manifest["company"]
    manifest_docs = {item["document_id"]: item for item in manifest["documents"]}
    connection = connect_database(row_factory=dict_row)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT e.id AS metric_id, e.company, e.domain, e.metric_name,
                          e.metric_label, e.fiscal_year, e.metric_value, e.unit, e.scope,
                          e.source_document_id, e.page_number, e.source_quote, e.source_url,
                          e.extraction_method, e.extractor_version, e.extraction_config,
                          e.source_chunk_id, e.source_chunk_index, e.source_content_hash,
                          c.id AS linked_chunk_id, c.chunk_index AS linked_chunk_index,
                          c.content AS linked_chunk_content, c.metadata AS linked_chunk_metadata
                   FROM public.business_metric_evidence e
                   LEFT JOIN public.document_chunks c ON c.id = e.source_chunk_id
                   WHERE e.status = 'verified' AND e.company = %s
                   ORDER BY e.domain, e.metric_name, e.fiscal_year, e.id""",
                (company,),
            )
            rows = cursor.fetchall()
            if not rows:
                raise ValueError(f"No verified business metrics found for manifest company {company!r}")
            cursor.execute(
                """SELECT document_id, chunk_index, content, metadata
                   FROM public.processed_document_chunks
                   WHERE document_id = ANY(%s)
                   ORDER BY document_id, chunk_index""",
                (sorted({row["source_document_id"] for row in rows}),),
            )
            parser_chunks = cursor.fetchall()
    finally:
        close_database_connection(connection)

    parser_by_document: dict[str, list[dict]] = defaultdict(list)
    for chunk in parser_chunks:
        parser_by_document[chunk["document_id"]].append(chunk)

    pdf_by_document = {}
    results = []
    for row in rows:
        document_id = row["source_document_id"]
        document = manifest_docs.get(document_id)
        if not document or row["source_url"] != document.get("source_url"):
            results.append({
                "metric_id": row["metric_id"], "document_id": document_id,
                "metric_name": row["metric_name"], "fiscal_year": row["fiscal_year"],
                "passed": False, "error": "source URL does not match an active manifest document",
            })
            continue

        pdf_path = root / "data/raw/vietnam_enterprises" / document["ticker"].lower() / f"{document_id.lower()}.pdf"
        if document_id not in pdf_by_document:
            if not pdf_path.is_file():
                pdf_by_document[document_id] = None
            else:
                content = pdf_path.read_bytes()
                pdf_by_document[document_id] = {
                    "bytes_hash": hashlib.sha256(content).hexdigest(),
                    "pdf": fitz.open(stream=content, filetype="pdf"),
                }
        pdf = pdf_by_document[document_id]
        if pdf is None:
            results.append({
                "metric_id": row["metric_id"], "document_id": document_id,
                "metric_name": row["metric_name"], "fiscal_year": row["fiscal_year"],
                "passed": False, "error": "archived source PDF is missing locally",
            })
            continue

        page_number = int(row["page_number"])
        valid_page = 1 <= page_number <= len(pdf["pdf"])
        page_text = pdf["pdf"][page_number - 1].get_text() if valid_page else ""
        linked_metadata = row.get("linked_chunk_metadata") or {}
        linked_content = row.get("linked_chunk_content") or ""
        parser_page_chunks = [
            chunk for chunk in parser_by_document.get(document_id, [])
            if str((chunk.get("metadata") or {}).get("page_number")) == str(page_number)
        ]
        parser_matches = [
            chunk["chunk_index"] for chunk in parser_page_chunks
            if source_quote_matches(chunk.get("content") or "", row["source_quote"])
        ]
        checks = {
            "manifest_pdf_hash_matches_saved_parser_hash": any(
                (chunk.get("metadata") or {}).get("source_sha256") == pdf["bytes_hash"]
                for chunk in parser_by_document.get(document_id, [])
            ),
            "source_quote_matches_pdf_page": valid_page and source_quote_matches(page_text, row["source_quote"]),
            "linked_vector_chunk_exists": row.get("linked_chunk_id") == row.get("source_chunk_id"),
            "linked_chunk_document_page_index_match": bool(
                row.get("linked_chunk_id") == row.get("source_chunk_id")
                and str(linked_metadata.get("document_id")) == document_id
                and str(linked_metadata.get("page_number")) == str(page_number)
                and row.get("linked_chunk_index") == row.get("source_chunk_index")
            ),
            "linked_chunk_content_hash_matches": bool(
                linked_content and hashlib.sha256(linked_content.encode("utf-8")).hexdigest()
                == row.get("source_content_hash")
            ),
            "source_quote_matches_linked_vector_chunk": bool(
                linked_content and source_quote_matches(linked_content, row["source_quote"])
            ),
            "source_quote_matches_saved_parser_chunk": bool(parser_matches),
        }
        results.append({
            "metric_id": row["metric_id"], "domain": row["domain"],
            "metric_name": row["metric_name"], "metric_label": row["metric_label"],
            "fiscal_year": row["fiscal_year"], "value": str(row["metric_value"]),
            "unit": row["unit"], "document_id": document_id, "page_number": page_number,
            "extraction_method": row["extraction_method"],
            "extractor_version": row["extractor_version"],
            "extraction_config": row.get("extraction_config") or {},
            "source_chunk_id": row["source_chunk_id"],
            "linked_chunk_index": row["linked_chunk_index"],
            "saved_parser_chunk_indices_matching_quote": parser_matches,
            "source_quote_sha256": hashlib.sha256(row["source_quote"].encode("utf-8")).hexdigest(),
            "source_pdf_sha256": pdf["bytes_hash"],
            "checks": checks,
            "passed": all(checks.values()),
        })

    for item in pdf_by_document.values():
        if item is not None:
            item["pdf"].close()

    check_names = (
        "manifest_pdf_hash_matches_saved_parser_hash",
        "source_quote_matches_pdf_page",
        "linked_vector_chunk_exists",
        "linked_chunk_document_page_index_match",
        "linked_chunk_content_hash_matches",
        "source_quote_matches_linked_vector_chunk",
        "source_quote_matches_saved_parser_chunk",
    )
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "read-only business_metric_evidence, processed_document_chunks, document_chunks, manifest and archived PDFs",
        "company": company,
        "verified_observation_count": len(rows),
        "distinct_metric_types": len({row["metric_name"] for row in rows}),
        "distinct_domains": len({row["domain"] for row in rows}),
        "extraction_method_counts": dict(Counter(row["extraction_method"] for row in rows)),
        "extractor_version_counts": dict(Counter(row["extractor_version"] for row in rows)),
        "checks": {
            name: {"passed": sum(bool(row.get("checks", {}).get(name)) for row in results),
                   "total": len(results)}
            for name in check_names
        },
        "passed": sum(bool(row.get("passed")) for row in results),
        "failed": sum(not bool(row.get("passed")) for row in results),
        "observations": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        result = audit()
    except Exception as error:
        raise SystemExit(f"Business metric provenance audit failed: {type(error).__name__}: {error}") from error
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output.relative_to(ROOT) if output.is_relative_to(ROOT) else output),
        "verified_observation_count": result["verified_observation_count"],
        "distinct_metric_types": result["distinct_metric_types"],
        "distinct_domains": result["distinct_domains"],
        "checks": result["checks"], "passed": result["passed"], "failed": result["failed"],
    }, ensure_ascii=False, indent=2))
    return 0 if result["failed"] == 0 and result["verified_observation_count"] == len(result["observations"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
