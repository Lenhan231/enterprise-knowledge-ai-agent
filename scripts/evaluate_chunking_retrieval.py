#!/usr/bin/env python3
"""Read-only dense retrieval comparison: current fixed vectors vs sentence chunks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import resource
import sys
import tempfile
import time
import unicodedata
from sys import stderr
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.document_processing.ingest_documents import Ingestion  # noqa: E402
from core.embeddings.embedding_service import (  # noqa: E402
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_MAX_SEQUENCE_LENGTH,
    EmbeddingService,
)
from core.evaluation.retrieval_metrics import (  # noqa: E402
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from scripts.source_downloaders.registry import source_extension  # noqa: E402

COMPANY = "Công ty Cổ phần Sữa Việt Nam (Vinamilk)"


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.findall(r"\w+", normalized, flags=re.UNICODE)


def _trigrams(text: str) -> set[tuple[str, ...]]:
    words = _tokens(text)
    return set(zip(words, words[1:], words[2:]))


def transfer_passage_labels(
    reference_chunks: list[dict],
    candidate_chunks: list[dict],
    minimum_reference_trigram_coverage: float = 0.5,
) -> tuple[set[str], dict]:
    """Map reviewed fixed passages to alternate chunks by same-page text overlap."""
    labels: set[str] = set()
    mapping = {}
    for reference in reference_chunks:
        reference_grams = _trigrams(reference["content"])
        matches = []
        if reference_grams:
            for candidate in candidate_chunks:
                if candidate.get("page_number") != reference.get("page_number"):
                    continue
                coverage = len(reference_grams & _trigrams(candidate["content"])) / len(reference_grams)
                if coverage >= minimum_reference_trigram_coverage:
                    matches.append((candidate["chunk_id"], round(coverage, 4)))
        mapping[reference["chunk_id"]] = matches
        labels.update(chunk_id for chunk_id, _ in matches)
    return labels, mapping


def _metrics(relevant: set[str], ranked: list[str]) -> dict[str, float]:
    return {
        **{f"precision@{k}": precision_at_k(relevant, ranked, k) for k in (1, 3, 5)},
        **{f"recall@{k}": recall_at_k(relevant, ranked, k) for k in (1, 3, 5)},
        "mrr": reciprocal_rank(relevant, ranked),
        **{f"ndcg@{k}": ndcg_at_k(relevant, ranked, k) for k in (1, 3, 5)},
    }


def _aggregate(rows: list[dict], field: str) -> dict[str, float]:
    return {
        name: round(sum(row[field][name] for row in rows) / len(rows), 4)
        for name in rows[0][field]
    }


def _rank_chunks(chunks: list[dict], query_vector: np.ndarray, fiscal_year: str | None) -> list[dict]:
    if not chunks:
        return []
    matrix = np.asarray([row["embedding"] for row in chunks], dtype=np.float32)
    query = np.asarray(query_vector, dtype=np.float32)
    scores = matrix @ query / np.maximum(
        np.linalg.norm(matrix, axis=1) * np.linalg.norm(query), 1e-12
    )
    ranked = []
    for row, score in zip(chunks, scores, strict=True):
        ranked.append((fiscal_year is not None and row.get("fiscal_year") == fiscal_year, float(score), row))
    ranked.sort(key=lambda item: (not item[0], -item[1], item[2]["chunk_id"]))
    return [dict(item[2], similarity=item[1]) for item in ranked]


def _peak_rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(value / (1024 if sys.platform != "darwin" else 1024 * 1024), 1)


def _as_vector(value) -> np.ndarray:
    return value.to_numpy() if hasattr(value, "to_numpy") else np.asarray(value, dtype=np.float32)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=REPO_ROOT / "data/evaluation/vinamilk_retrieval_cases.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-ids", nargs="+", help="Finance case subset; default is all five annual-report cases")
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--min-label-overlap", type=float, default=0.5)
    args = parser.parse_args()
    if not 1 <= args.top_k <= 100 or not 0 < args.min_label_overlap <= 1:
        parser.error("top-k must be 1..100 and min-label-overlap must be in (0, 1]")

    load_dotenv(REPO_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required")
    cases_bytes = args.cases.read_bytes()
    all_cases = json.loads(cases_bytes)["cases"]
    finance_cases = [case for case in all_cases if case["id"].startswith("finance-revenue-profit-")]
    if args.case_ids:
        requested = set(args.case_ids)
        finance_cases = [case for case in finance_cases if case["id"] in requested]
        if requested != {case["id"] for case in finance_cases}:
            parser.error("case-ids must name existing finance-revenue-profit cases")
    if not finance_cases:
        parser.error("No finance retrieval cases selected")
    document_ids = sorted({doc_id for case in finance_cases for doc_id in case["relevant_document_ids"]})
    reference_ids = sorted({chunk_id for case in finance_cases for chunk_id in case.get("relevant_chunk_ids", [])})

    manifest = json.loads((REPO_ROOT / "data/vietnam_enterprises/manifest.json").read_text(encoding="utf-8"))
    manifest_docs = {item["document_id"]: item for item in manifest["documents"]}
    missing_docs = set(document_ids) - manifest_docs.keys()
    if missing_docs:
        parser.error(f"Finance source documents missing from manifest: {sorted(missing_docs)}")

    # Read the active fixed vectors and reviewed passage source text under the
    # same company/role boundary used by the application. No database writes.
    fixed_by_document: dict[str, list[dict]] = {doc_id: [] for doc_id in document_ids}
    references: dict[str, dict] = {}
    database_snapshot = {}
    with psycopg.connect(database_url) as connection:
        register_vector(connection)
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                """
                SELECT c.document_name, c.chunk_index, c.content, c.metadata,
                       c.embedding, d.fiscal_year, d.allowed_roles
                FROM public.document_chunks AS c
                JOIN public.documents AS d ON d.document_id = c.metadata->>'document_id'
                WHERE d.company = %s AND d.processing_status = 'ready'
                  AND d.document_id = ANY(%s::text[])
                  AND d.allowed_roles && ARRAY['finance_analyst']::text[]
                ORDER BY d.document_id, c.chunk_index
                """,
                (COMPANY, document_ids),
            )
            for document_name, index, content, metadata, vector, fiscal_year, roles in cursor.fetchall():
                document_id = metadata["document_id"]
                fixed_by_document[document_id].append({
                    "chunk_id": f"{document_id}::chunk::{index}",
                    "document_id": document_id,
                    "document_name": document_name,
                    "chunk_index": index,
                    "content": content,
                    "page_number": metadata.get("page_number"),
                    "fiscal_year": fiscal_year,
                    "allowed_roles": roles,
                    "embedding": _as_vector(vector),
                })
            cursor.execute(
                """
                SELECT c.document_name, c.chunk_index, c.content, c.metadata,
                       d.fiscal_year, d.allowed_roles
                FROM public.document_chunks AS c
                JOIN public.documents AS d ON d.document_id = c.metadata->>'document_id'
                WHERE d.company = %s AND d.processing_status = 'ready'
                  AND d.allowed_roles && ARRAY['finance_analyst']::text[]
                  AND c.metadata->>'document_id' || '::chunk::' || c.chunk_index::text = ANY(%s::text[])
                """,
                (COMPANY, reference_ids),
            )
            for document_name, index, content, metadata, fiscal_year, roles in cursor.fetchall():
                chunk_id = f"{metadata['document_id']}::chunk::{index}"
                references[chunk_id] = {
                    "chunk_id": chunk_id,
                    "document_id": metadata["document_id"],
                    "content": content,
                    "page_number": metadata.get("page_number"),
                    "fiscal_year": fiscal_year,
                    "allowed_roles": roles,
                }
            cursor.execute(
                """
                SELECT count(*), count(DISTINCT d.document_id), min(vector_dims(c.embedding)),
                       max(vector_dims(c.embedding)), array_agg(DISTINCT c.metadata->>'embedding_model')
                FROM public.document_chunks AS c
                JOIN public.documents AS d ON d.document_id = c.metadata->>'document_id'
                WHERE d.company = %s AND d.processing_status = 'ready'
                  AND d.document_id = ANY(%s::text[])
                  AND d.allowed_roles && ARRAY['finance_analyst']::text[]
                """,
                (COMPANY, document_ids),
            )
            count, document_count, min_dim, max_dim, models = cursor.fetchone()
            database_snapshot = {
                "authorized_fixed_chunks": count,
                "authorized_documents": document_count,
                "vector_dimensions": [min_dim, max_dim],
                "embedding_models": models,
            }
    if set(fixed_by_document) != set(document_ids) or any(not fixed_by_document[doc_id] for doc_id in document_ids):
        raise RuntimeError("At least one selected finance source has no ready, role-authorized fixed chunks")
    if set(references) != set(reference_ids):
        raise RuntimeError("Some reviewed passage references are stale or not finance-role-visible")
    if database_snapshot["vector_dimensions"][0] != database_snapshot["vector_dimensions"][1]:
        raise RuntimeError("Selected documents do not have a consistent embedding dimension")
    if database_snapshot["embedding_models"] != [DEFAULT_EMBEDDING_MODEL]:
        raise RuntimeError(f"Stored vectors do not match configured embedding model: {database_snapshot['embedding_models']}")

    embedding_service = EmbeddingService()
    query_vectors = {
        case["id"]: np.asarray(embedding_service.embed_query(case["question"]), dtype=np.float32)
        for case in finance_cases
    }

    source_root = REPO_ROOT / "data/raw/vietnam_enterprises"
    class TokenizerOnly:
        model_name = DEFAULT_EMBEDDING_MODEL
        max_sequence_length = EMBEDDING_MAX_SEQUENCE_LENGTH
    # Table outputs do not affect text chunking or dense retrieval; keep this
    # experiment focused on shared page text and avoid unrelated table analysis.
    ingestor = Ingestion(TokenizerOnly(), chunking_strategy="sentence", extract_tables=False)
    sentence_chunks = []
    parse_started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="chunking-ablation-") as temp_dir:
        for document_id in document_ids:
            item = manifest_docs[document_id]
            source = source_root / item["ticker"].lower() / (document_id.lower() + source_extension(item))
            if not source.is_file():
                raise FileNotFoundError(source)
            chunks = ingestor.ingestion(
                source,
                Path(temp_dir) / item["ticker"].lower(),
                document_id=document_id,
                extra_metadata={
                    "company": COMPANY,
                    "document_id": document_id,
                    "fiscal_year": item["fiscal_year"],
                    "allowed_roles": item["rbac"]["allowed_roles"],
                    "embedding_model": DEFAULT_EMBEDDING_MODEL,
                },
            )
            print(f"parsed {document_id}: {len(chunks)} sentence chunks", file=stderr, flush=True)
            sentence_chunks.extend({
                "chunk_id": f"{document_id}::chunk::{chunk.metadata['chunk_index']}",
                "document_id": document_id,
                "document_name": source.name,
                "chunk_index": chunk.metadata["chunk_index"],
                "content": chunk.page_content,
                "page_number": chunk.metadata.get("page_number"),
                "fiscal_year": item["fiscal_year"],
                "allowed_roles": item["rbac"]["allowed_roles"],
            } for chunk in chunks)
    corpus_parse_seconds = round(time.perf_counter() - parse_started, 2)

    sentence_texts = [row["content"] for row in sentence_chunks]
    sentence_vectors = []
    embedding_started = time.perf_counter()
    for start in range(0, len(sentence_texts), 32):
        sentence_vectors.extend(embedding_service.embed_documents(sentence_texts[start:start + 32]))
    corpus_embedding_seconds = round(time.perf_counter() - embedding_started, 2)
    for row, vector in zip(sentence_chunks, sentence_vectors, strict=True):
        row["embedding"] = np.asarray(vector, dtype=np.float32)
    sentence_chunks.sort(key=lambda row: (row["document_id"], row["chunk_index"]))

    strategy_chunks = {
        "fixed": [row for values in fixed_by_document.values() for row in values],
        "sentence": sentence_chunks,
    }
    strategies = {}
    case_results = {strategy: [] for strategy in strategy_chunks}
    for strategy, chunks in strategy_chunks.items():
        result_rows = []
        for case in finance_cases:
            relevant_passages = set(case.get("relevant_chunk_ids", []))
            mapping = None
            if strategy == "sentence":
                refs = [references[chunk_id] for chunk_id in sorted(relevant_passages)]
                relevant_passages, mapping = transfer_passage_labels(
                    refs,
                    [row for row in chunks if row["document_id"] in case["relevant_document_ids"]],
                    args.min_label_overlap,
                )
                if not relevant_passages:
                    raise RuntimeError(f"No sentence-chunk passage labels transferred for {case['id']}")
            fiscal_year_match = re.search(r"\b(?:19|20)\d{2}\b", case["question"])
            ranked = _rank_chunks(chunks, query_vectors[case["id"]], fiscal_year_match.group(0) if fiscal_year_match else None)
            ranked = ranked[:args.top_k]
            passage_ids = [row["chunk_id"] for row in ranked]
            document_ids_ranked = list(dict.fromkeys(row["document_id"] for row in ranked))
            row = {
                "id": case["id"],
                "relevant_passage_count": len(relevant_passages),
                "relevant_document_ids": case["relevant_document_ids"],
                "ranked_document_ids": document_ids_ranked,
                "document_metrics": _metrics(set(case["relevant_document_ids"]), document_ids_ranked),
                "passage_metrics": _metrics(relevant_passages, passage_ids),
                "top_passages": [
                    {"chunk_id": item["chunk_id"], "document_id": item["document_id"],
                     "page_number": item["page_number"], "similarity": round(item["similarity"], 6)}
                    for item in ranked[:5]
                ],
            }
            if mapping is not None:
                row["label_transfer"] = mapping
            result_rows.append(row)
        case_results[strategy] = result_rows
        strategies[strategy] = {
            "chunk_count": len(chunks),
            "document_count": len({row["document_id"] for row in chunks}),
            "aggregate_document": _aggregate(result_rows, "document_metrics"),
            "aggregate_passage": _aggregate(result_rows, "passage_metrics"),
            "case_count": len(result_rows),
        }

    candidate_hashes = {}
    for strategy, chunks in strategy_chunks.items():
        payload = [
            (row["chunk_id"], hashlib.sha256(row["content"].encode("utf-8")).hexdigest())
            for row in chunks
        ]
        candidate_hashes[strategy] = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark": "fixed-vs-sentence-aware dense retrieval; read-only live baseline plus in-memory alternate chunks",
        "company": COMPANY,
        "role": "finance_analyst",
        "document_ids": document_ids,
        "case_ids": [case["id"] for case in finance_cases],
        "case_file": str(args.cases.relative_to(REPO_ROOT) if args.cases.is_relative_to(REPO_ROOT) else args.cases),
        "case_file_sha256": hashlib.sha256(cases_bytes).hexdigest(),
        "embedding_model": DEFAULT_EMBEDDING_MODEL,
        "max_sequence_length": EMBEDDING_MAX_SEQUENCE_LENGTH,
        "top_k": args.top_k,
        "label_transfer": {
            "method": "same page and fraction of reviewed reference trigram set present in a sentence-aware candidate",
            "minimum_reference_trigram_coverage": args.min_label_overlap,
            "limitations": "The fixed labels were manually reviewed; sentence-strategy labels are transferred heuristically and require independent human review. Scores are diagnostic, not a final chunking selection.",
        },
        "database_snapshot": database_snapshot,
        "corpus_parse_seconds": corpus_parse_seconds,
        "alternate_embedding_seconds": corpus_embedding_seconds,
        "candidate_sha256": candidate_hashes,
        "environment": {
            "python": sys.version.split()[0],
            "device": "cpu",
            "gpu_available": False,
            "peak_rss_mb": _peak_rss_mb(),
        },
        "strategies": strategies,
        "results": case_results,
        "limitations": "Only five finance questions and their five annual reports were compared. Dense retrieval only; no BM25/hybrid/reranker/QA comparison. Current database vectors are the fixed baseline and alternate chunks/vectors were computed in memory; this script performs no persistent writes. Exact-year ordering matches the application's fiscal-year boost. Transferred sentence passage judgments are heuristic.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "database_snapshot": database_snapshot,
        "strategies": strategies,
        "candidate_sha256": candidate_hashes,
        "peak_rss_mb": report["environment"]["peak_rss_mb"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
