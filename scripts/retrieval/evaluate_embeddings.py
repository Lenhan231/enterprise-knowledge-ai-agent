#!/usr/bin/env python3
"""Compare proposal embedding models on the same role-filtered corpus and cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
try:
    import resource
except ImportError:
    resource = None
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.evaluation.retrieval_metrics import (  # noqa: E402
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

MODELS = {
    "bge-m3": {
        "model_id": "BAAI/bge-m3",
        "query_prefix": "",
        "passage_prefix": "",
        "instruction": None,
    },
    "qwen3-embedding": {
        "model_id": "Qwen/Qwen3-Embedding-0.6B",
        "query_prefix": "",
        "passage_prefix": "",
        "instruction": "Given a search query, retrieve relevant passages that answer the query",
    },
    "e5-large-v2": {
        "model_id": "intfloat/e5-large-v2",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "instruction": None,
    },
}


def _rss_peak_mb() -> float | None:
    if resource is None:
        return None  # Windows does not expose POSIX getrusage.
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(value / (1024 if sys.platform != "darwin" else 1024 * 1024), 1)


def _load_corpus(database_url: str, company: str) -> list[dict]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.content, c.metadata->>'document_id' AS document_id,
                       d.allowed_roles
                FROM public.document_chunks AS c
                JOIN public.documents AS d
                  ON d.document_id = c.metadata->>'document_id'
                WHERE d.company = %s
                  AND coalesce(d.processing_status, 'ready') = 'ready'
                  AND nullif(btrim(c.content), '') IS NOT NULL
                ORDER BY d.document_id, c.chunk_index, c.id
                """,
                (company,),
            )
            return cursor.fetchall()


def _visible(row: dict, roles: list[str]) -> bool:
    document_roles = row["allowed_roles"] or []
    return "admin" in roles or bool(set(document_roles) & set(roles))


def _sample_per_document(rows: list[dict], limit: int) -> list[dict]:
    """Choose evenly spaced chunks so every document remains a candidate."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["document_id"]].append(row)
    sampled = []
    for document_id in sorted(grouped):
        document_rows = grouped[document_id]
        if len(document_rows) <= limit:
            sampled.extend(document_rows)
            continue
        if limit == 1:
            positions = [len(document_rows) // 2]
        else:
            positions = [round(index * (len(document_rows) - 1) / (limit - 1)) for index in range(limit)]
        sampled.extend(document_rows[position] for position in positions)
    return sampled


def _load_public_corpus(path: Path, manifest_ids: set[str]) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("Public embedding corpus is empty")
    for row in rows:
        if row.get("document_id") not in manifest_ids:
            raise ValueError(f"Corpus document is not allowlisted by the public manifest: {row.get('document_id')}")
        if not isinstance(row.get("content"), str) or not row["content"].strip():
            raise ValueError("Every corpus row must contain non-empty text")
        if not isinstance(row.get("allowed_roles"), list):
            raise ValueError("Every corpus row must preserve allowed_roles")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=["baseline", *sorted(MODELS)])
    parser.add_argument("--model-id", help="Explicit configured model ID for the baseline")
    parser.add_argument("--cases", type=Path, default=REPO_ROOT / "data/evaluation/vinamilk_retrieval_cases.json")
    parser.add_argument("--corpus", type=Path, help="Optional public-manifest JSONL; avoids live database credentials")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--company", default="Công ty Cổ phần Sữa Việt Nam (Vinamilk)")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--max-chunks-per-document", type=int, default=32)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    if args.batch_size < 1 or not 1 <= args.top_k <= 100 or args.max_chunks_per_document < 1:
        parser.error("--batch-size and --max-chunks-per-document must be positive; --top-k must be between 1 and 100")

    case_bytes = args.cases.read_bytes()
    cases = json.loads(case_bytes)["cases"]
    if not cases:
        parser.error("No labeled cases found")
    if args.corpus:
        manifest_path = REPO_ROOT / "data/vietnam_enterprises/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        documents = manifest["documents"] if isinstance(manifest, dict) else manifest
        manifest_ids = {item["document_id"] for item in documents}
        try:
            full_corpus = _load_public_corpus(args.corpus, manifest_ids)
        except (ValueError, json.JSONDecodeError) as error:
            parser.error(str(error))
        corpus_source = "public_manifest_jsonl"
    else:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            parser.error("DATABASE_URL is required unless --corpus is supplied")
        full_corpus = _load_corpus(database_url, args.company)
        corpus_source = "live_database"
    if not full_corpus:
        parser.error(f"No ready chunks found for {args.company}")
    corpus = _sample_per_document(full_corpus, args.max_chunks_per_document)
    all_corpus_chunks_included = len(corpus) == len(full_corpus)
    sample_strategy = (
        "all eligible passages per document (corpus fits per-document cap)"
        if all_corpus_chunks_included else
        "evenly spaced passages per document"
    )
    corpus_sha256 = hashlib.sha256(
        "\n".join(
            f"{row['document_id']}\0{row['content']}" for row in corpus
        ).encode("utf-8")
    ).hexdigest()

    if args.model == "baseline":
        if not args.model_id:
            parser.error("--model-id is required for the baseline")
        spec = {"model_id": args.model_id, "query_prefix": "", "passage_prefix": "", "instruction": None}
    else:
        if args.model_id:
            parser.error("--model-id is only supported for the baseline")
        spec = MODELS[args.model]
    from sentence_transformers import SentenceTransformer
    import torch

    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA was requested but is unavailable")
    load_started = time.perf_counter()
    model = SentenceTransformer(spec["model_id"], device=args.device)
    model.max_seq_length = min(model.max_seq_length, 512)
    if args.device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    model_load_seconds = time.perf_counter() - load_started
    revision = getattr(model[0].auto_model.config, "_commit_hash", None)

    passage_inputs = [spec["passage_prefix"] + row["content"] for row in corpus]
    embed_started = time.perf_counter()
    passage_vectors = model.encode(
        passage_inputs,
        batch_size=args.batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    corpus_embedding_seconds = time.perf_counter() - embed_started

    method_results = []
    for case in cases:
        eligible_indices = [index for index, row in enumerate(corpus) if _visible(row, case["allowed_roles"])]
        if not eligible_indices:
            raise RuntimeError(f"No chunks visible to role for case {case['id']}")
        query = spec["query_prefix"] + case["question"]
        if spec["instruction"]:
            query = f"Instruct: {spec['instruction']}\nQuery: {query}"
        query_started = time.perf_counter()
        query_vector = model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )[0]
        scores = passage_vectors[eligible_indices] @ query_vector
        scored_documents: dict[str, float] = {}
        for index, score in zip(eligible_indices, scores):
            document_id = corpus[index]["document_id"]
            scored_documents[document_id] = max(scored_documents.get(document_id, -1.0), float(score))
        ranked = [doc_id for doc_id, _ in sorted(scored_documents.items(), key=lambda item: (-item[1], item[0]))[:args.top_k]]
        query_latency_ms = (time.perf_counter() - query_started) * 1000
        relevant = set(case["relevant_document_ids"])
        method_results.append({
            "id": case["id"],
            "role": case["role"],
            "eligible_chunks": len(eligible_indices),
            "ranked_document_ids": ranked,
            "relevant_document_ids": sorted(relevant),
            "latency_ms": round(query_latency_ms, 2),
            "metrics": {
                **{f"precision@{k}": precision_at_k(relevant, ranked, k) for k in (1, 3, 5)},
                **{f"recall@{k}": recall_at_k(relevant, ranked, k) for k in (1, 3, 5)},
                "mrr": reciprocal_rank(relevant, ranked),
                **{f"ndcg@{k}": ndcg_at_k(relevant, ranked, k) for k in (1, 3, 5)},
            },
        })
        print(f"{case['id']} finished in {query_latency_ms:.0f} ms", file=sys.stderr, flush=True)

    metric_keys = method_results[0]["metrics"]
    aggregate = {
        key: round(sum(result["metrics"][key] for result in method_results) / len(method_results), 4)
        for key in metric_keys
    }
    if args.device == "cuda":
        torch.cuda.synchronize()
        peak_gpu_allocated_mb = round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1)
        peak_gpu_reserved_mb = round(torch.cuda.max_memory_reserved() / (1024 * 1024), 1)
        gpu_name = torch.cuda.get_device_name(0)
    else:
        peak_gpu_allocated_mb = peak_gpu_reserved_mb = None
        gpu_name = None
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_level": "document; maximum chunk cosine per document",
        "model_key": args.model,
        "model_id": spec["model_id"],
        "model_revision": revision,
        "case_count": len(cases),
        "case_file": args.cases.name,
        "case_file_sha256": hashlib.sha256(case_bytes).hexdigest(),
        "sampled_corpus_sha256": corpus_sha256,
        "corpus_source": corpus_source,
        "corpus_file_sha256": hashlib.sha256(args.corpus.read_bytes()).hexdigest() if args.corpus else None,
        "company": args.company,
        "corpus_chunks": len(corpus),
        "full_company_corpus_chunks": len(full_corpus),
        "all_corpus_chunks_included": all_corpus_chunks_included,
        "sampled_chunks_per_document": args.max_chunks_per_document,
        "max_sequence_length": model.max_seq_length,
        "configuration": {
            "device": args.device,
            "batch_size": args.batch_size,
            "max_sequence_length": model.max_seq_length,
            "sample_strategy": sample_strategy,
            "document_score": "maximum eligible chunk cosine per document",
        },
        "query_instruction": spec["instruction"],
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "device": args.device,
            "gpu_available": torch.cuda.is_available(),
            "gpu_name": gpu_name,
            "peak_gpu_memory_allocated_mb": peak_gpu_allocated_mb,
            "peak_gpu_memory_reserved_mb": peak_gpu_reserved_mb,
            "peak_rss_mb": _rss_peak_mb(),
        },
        "timing_seconds": {
            "model_load": round(model_load_seconds, 2),
            "corpus_embeddings": round(corpus_embedding_seconds, 2),
            "mean_query": round(sum(item["latency_ms"] for item in method_results) / len(method_results) / 1000, 4),
        },
        "aggregate": aggregate,
        "results": method_results,
        "limitations": (
            "Small document-level Vinamilk smoke set using every available corpus passage. No database writes are made. Query-time includes query embedding and in-memory cosine scoring, but excludes model loading and corpus embedding. No human judgment or passage-level labels."
            if all_corpus_chunks_included else
            f"Small document-level Vinamilk smoke set using an evenly spaced sample capped at {args.max_chunks_per_document} passages per source; this is not full-corpus retrieval. No database writes are made. Query-time includes query embedding and in-memory cosine scoring, but excludes model loading and corpus embedding. No human judgment or passage-level labels."
        ),
    }
    output = args.output or REPO_ROOT / "artifacts/evaluation" / f"vinamilk-embedding-{args.model}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "aggregate": aggregate}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
