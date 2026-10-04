#!/usr/bin/env python3
"""Link verified financial metrics to uniquely matching saved parser chunks."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from core.database.document_repository import link_financial_metric_source_chunk  # noqa: E402


def backfill(apply: bool, document_ids: list[str] | None = None) -> dict:
    load_dotenv(ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required")

    updates = []
    skipped = []
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT m.id, m.document_id, m.metric_name, m.metric_label,
                          m.fiscal_year, m.page_number, m.source_quote,
                          c.candidate_values
                   FROM public.extracted_financial_metrics m
                   LEFT JOIN public.extracted_metric_candidates c
                     ON c.document_id = m.document_id
                    AND c.metric_name = m.metric_name
                    AND c.source_quote_hash = m.source_quote_hash
                   WHERE m.status = 'verified' AND m.source_chunk_id IS NULL
                     AND (%s::text[] IS NULL OR m.document_id = ANY(%s::text[]))
                   ORDER BY m.document_id, m.page_number, m.id""",
                (document_ids, document_ids),
            )
            metrics = cursor.fetchall()
            chunks_by_document = {}
            for metric in metrics:
                document_id = metric["document_id"]
                if document_id not in chunks_by_document:
                    cursor.execute(
                        """SELECT id, chunk_index, content, metadata,
                                  metadata->>'page_number' AS page_number
                           FROM public.document_chunks
                           WHERE metadata->>'document_id' = %s
                           ORDER BY chunk_index""",
                        (document_id,),
                    )
                    chunks_by_document[document_id] = cursor.fetchall()
                candidate_values = metric.get("candidate_values")
                if not candidate_values:
                    skipped.append({"metric_id": metric["id"], "reason": "missing_candidate_values"})
                    continue
                match = link_financial_metric_source_chunk(
                    {**metric, "candidate_values": candidate_values},
                    chunks_by_document[document_id],
                )
                if match[0] is None:
                    skipped.append({"metric_id": metric["id"], "reason": "no_unique_same_page_chunk"})
                    continue
                updates.append({"metric_id": metric["id"], "source_chunk_id": match[0],
                                "source_chunk_index": match[1], "source_content_hash": match[2]})

        if apply and updates:
            with connection.transaction(), connection.cursor() as cursor:
                cursor.executemany(
                    """UPDATE public.extracted_financial_metrics
                       SET source_chunk_id = %s, source_chunk_index = %s,
                           source_content_hash = %s
                       WHERE id = %s AND status = 'verified' AND source_chunk_id IS NULL""",
                    [(row["source_chunk_id"], row["source_chunk_index"],
                      row["source_content_hash"], row["metric_id"]) for row in updates],
                )
    return {"mode": "apply" if apply else "dry_run", "matched": updates, "skipped": skipped}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist exact/unique chunk links (default: dry run)")
    parser.add_argument("--document-id", action="append", dest="document_ids",
                        help="Limit to a document ID; repeat to select multiple")
    args = parser.parse_args()
    result = backfill(args.apply, args.document_ids)
    print(f"{result['mode']}: matched={len(result['matched'])}, skipped={len(result['skipped'])}")
    for row in result["skipped"]:
        print(f"skipped metric {row['metric_id']}: {row['reason']}")
    for row in result["matched"]:
        print(f"metric {row['metric_id']} -> chunk {row['source_chunk_id']} (index {row['source_chunk_index']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
