#!/usr/bin/env python3
"""Measure role-filtered retrieval against labelled source-document cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from time import perf_counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.evaluation.retrieval_metrics import ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank  # noqa: E402
from core.retrieval.retrieval import RetrievalRequest  # noqa: E402
from core.retrieval.retrieval_service import RetrievalService  # noqa: E402


def ranked_passage_ids(results) -> list[str]:
    """Flatten returned chunks or parent windows to ordered child passage IDs."""
    passages = []
    for item in results:
        indices = item.metadata.get("parent_chunk_indices", [item.location.chunk_index])
        for chunk_index in indices:
            chunk_id = f"{item.document_id}::chunk::{chunk_index}"
            if chunk_id not in passages:
                passages.append(chunk_id)
    return passages


def parent_context_metrics(results, relevant_passages: set[str]) -> dict[str, float]:
    """Score returned parent windows as contexts, not as serial child chunks."""
    ranked_contexts = []
    relevant_contexts = set()
    covered_by_context = []
    for rank, item in enumerate(results, start=1):
        context_id = item.metadata.get("parent_id", item.chunk_id)
        ranked_contexts.append(context_id)
        indices = item.metadata.get("parent_chunk_indices", [item.location.chunk_index])
        covered = {
            f"{item.document_id}::chunk::{chunk_index}"
            for chunk_index in indices
        } & relevant_passages
        covered_by_context.append(covered)
        if covered:
            relevant_contexts.add(context_id)
    metrics = {
        **{f"context_precision@{k}": precision_at_k(relevant_contexts, ranked_contexts, k) for k in (1, 3, 5)},
        **{f"context_recall@{k}": recall_at_k(relevant_contexts, ranked_contexts, k) for k in (1, 3, 5)},
        "context_mrr": reciprocal_rank(relevant_contexts, ranked_contexts),
        **{f"context_ndcg@{k}": ndcg_at_k(relevant_contexts, ranked_contexts, k) for k in (1, 3, 5)},
    }
    for k in (1, 3, 5):
        covered_passages = set().union(*covered_by_context[:k]) if covered_by_context[:k] else set()
        metrics[f"gold_passage_coverage_recall@{k}"] = len(covered_passages) / len(relevant_passages) if relevant_passages else 0.0
    return metrics


def validate_passage_labels(service: RetrievalService, cases: list[dict], company: str) -> None:
    """Fail if passage judgments no longer point to ready, role-visible chunks."""
    for case in cases:
        labels = case.get("relevant_chunk_ids", [])
        if not labels:
            continue
        relevant_documents = set(case["relevant_document_ids"])
        for label in labels:
            document_id, separator, raw_index = label.rpartition("::chunk::")
            if not separator or document_id not in relevant_documents or not raw_index.isdecimal():
                raise ValueError(f"Invalid passage judgment in {case['id']}: {label}")
        roles = case.get("allowed_roles", [case["role"]])
        with service.repository.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT label.id
                FROM unnest(%s::text[]) AS label(id)
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM public.document_chunks AS c
                    JOIN public.documents AS d
                      ON d.document_id = c.metadata->>'document_id'
                    WHERE d.document_id = split_part(label.id, '::chunk::', 1)
                      AND c.chunk_index = split_part(label.id, '::chunk::', 2)::integer
                      AND d.company = %s
                      AND d.processing_status = 'ready'
                      AND (d.allowed_roles && %s::text[] OR 'admin' = ANY(%s::text[]))
                )
                """,
                (labels, company, roles, roles),
            )
            stale = [row[0] for row in cursor.fetchall()]
        if stale:
            raise RuntimeError(
                f"Passage judgments are missing, not ready, or not visible for {case['id']}: {stale}"
            )


def gpu_metadata() -> dict:
    try:
        import torch
    except ImportError:
        return {"available": False, "devices": []}
    available = torch.cuda.is_available()
    return {
        "available": available,
        "devices": [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())]
        if available else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=REPO_ROOT / "data/evaluation/vinamilk_retrieval_cases.json")
    parser.add_argument("--output", type=Path, help="Optional path for the JSON run report")
    parser.add_argument("--top-k", type=int, default=30, help="Passage candidates before document deduplication")
    parser.add_argument("--methods", nargs="+", choices=("dense", "bm25", "hybrid", "parent"), default=("dense", "bm25", "hybrid"))
    parser.add_argument("--case-ids", nargs="+", help="Optional subset of labeled case IDs")
    parser.add_argument("--hybrid-weights", nargs="+", default=["1:2:60"], metavar="DENSE:BM25:RRF_K",
                        help="Hybrid RRF configurations to evaluate; e.g. 1:1:60 2:1:60")
    args = parser.parse_args()
    if not 1 <= args.top_k <= 100:
        parser.error("--top-k must be between 1 and 100")
    cases_bytes = args.cases.read_bytes()
    cases_sha256 = hashlib.sha256(cases_bytes).hexdigest()
    cases = json.loads(cases_bytes)["cases"]
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case["id"] in selected]
        missing = selected - {case["id"] for case in cases}
        if missing:
            parser.error(f"Unknown case IDs: {', '.join(sorted(missing))}")
    if not cases:
        parser.error("No evaluation cases selected")
    try:
        hybrid_configs = []
        for raw in args.hybrid_weights:
            dense_weight, bm25_weight, rrf_k = raw.split(":")
            config = (float(dense_weight), float(bm25_weight), int(rrf_k))
            if config[0] <= 0 or config[1] <= 0 or config[2] < 0:
                raise ValueError
            hybrid_configs.append(config)
    except (ValueError, TypeError):
        parser.error("--hybrid-weights values must be positive DENSE:BM25 weights and non-negative RRF_K")
    service = RetrievalService()
    results = {}
    database_snapshot = {}
    try:
        company = "Công ty Cổ phần Sữa Việt Nam (Vinamilk)"
        validate_passage_labels(service, cases, company)
        method_configs = [(method, None) for method in args.methods if method != "hybrid"]
        if "hybrid" in args.methods:
            method_configs.extend(("hybrid", config) for config in hybrid_configs)
        for method, fusion_config in method_configs:
            if fusion_config and service.embedding_service is None:
                service.retrieve(
                    RetrievalRequest(query="warm-up query, excluded from scoring", top_k=1),
                    company=company, roles=["finance_analyst"], method="dense",
                )
            method_name = method if fusion_config is None else (
                f"hybrid-d{fusion_config[0]:g}-b{fusion_config[1]:g}-k{fusion_config[2]}"
            )
            method_started = perf_counter()
            method_results = []
            for case in cases:
                response = service.retrieve(
                    RetrievalRequest(query=case["question"], top_k=args.top_k),
                    company=company,
                    roles=case.get("allowed_roles", [case["role"]]),
                    method=method,
                    **({
                        "dense_weight": fusion_config[0],
                        "bm25_weight": fusion_config[1],
                        "rrf_k": fusion_config[2],
                    } if fusion_config else {}),
                )
                ranked_documents = list(dict.fromkeys(item.document_id for item in response.results))
                ranked_passages = ranked_passage_ids(response.results)
                relevant = set(case["relevant_document_ids"])
                case_result = {
                    "id": case["id"],
                    "role": case["role"],
                    "latency_ms": round(response.latency_ms, 2),
                    "ranked_document_ids": ranked_documents,
                    "relevant_document_ids": sorted(relevant),
                    "metrics": {
                        **{f"precision@{k}": precision_at_k(relevant, ranked_documents, k) for k in (1, 3, 5)},
                        **{f"recall@{k}": recall_at_k(relevant, ranked_documents, k) for k in (1, 3, 5)},
                        "mrr": reciprocal_rank(relevant, ranked_documents),
                        **{f"ndcg@{k}": ndcg_at_k(relevant, ranked_documents, k) for k in (1, 3, 5)},
                    },
                }
                passage_labels = set(case.get("relevant_chunk_ids", []))
                if passage_labels:
                    case_result["relevant_passage_ids"] = sorted(passage_labels)
                    if method == "parent":
                        case_result["parent_context_metrics"] = parent_context_metrics(response.results, passage_labels)
                    else:
                        case_result["ranked_passage_ids"] = ranked_passages
                        case_result["passage_metrics"] = {
                            **{f"precision@{k}": precision_at_k(passage_labels, ranked_passages, k) for k in (1, 3, 5)},
                            **{f"recall@{k}": recall_at_k(passage_labels, ranked_passages, k) for k in (1, 3, 5)},
                            "mrr": reciprocal_rank(passage_labels, ranked_passages),
                            **{f"ndcg@{k}": ndcg_at_k(passage_labels, ranked_passages, k) for k in (1, 3, 5)},
                        }
                method_results.append(case_result)
                print(
                    f"{method}: {case['id']} finished in {response.latency_ms:.0f} ms",
                    file=sys.stderr,
                    flush=True,
                )
            averages = {
                key: round(sum(case["metrics"][key] for case in method_results) / len(method_results), 4)
                for key in method_results[0]["metrics"]
            } if method_results else {}
            results[method_name] = {
                "aggregate": averages,
                "passage_case_count": sum("passage_metrics" in case for case in method_results),
                "passage_aggregate": {
                    key: round(sum(case["passage_metrics"][key] for case in method_results if "passage_metrics" in case)
                               / sum("passage_metrics" in case for case in method_results), 4)
                    for key in next((case["passage_metrics"].keys() for case in method_results if "passage_metrics" in case), [])
                },
                "parent_context_case_count": sum("parent_context_metrics" in case for case in method_results),
                "parent_context_aggregate": {
                    key: round(sum(case["parent_context_metrics"][key] for case in method_results if "parent_context_metrics" in case)
                               / sum("parent_context_metrics" in case for case in method_results), 4)
                    for key in next((case["parent_context_metrics"].keys() for case in method_results if "parent_context_metrics" in case), [])
                },
                "mean_latency_ms": round(sum(case["latency_ms"] for case in method_results) / len(method_results), 2) if method_results else None,
                "total_latency_ms": round((perf_counter() - method_started) * 1000, 2),
                "results": method_results,
            }
        with service.repository.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT current_setting('server_version'),
                       (SELECT count(*) FROM public.documents),
                       (SELECT count(*) FROM public.document_chunks),
                       count(DISTINCT d.document_id), count(c.id)
                FROM public.document_chunks AS c
                JOIN public.documents AS d
                  ON d.document_id = c.metadata->>'document_id'
                WHERE d.company = %s AND coalesce(d.processing_status, 'ready') = 'ready'
                """,
                ("Công ty Cổ phần Sữa Việt Nam (Vinamilk)",),
            )
            server_version, documents, chunks, company_documents, company_chunks = cursor.fetchone()
            database_snapshot = {
                "postgres_version": server_version,
                "all_documents": documents,
                "all_chunks": chunks,
                "evaluated_company": "Công ty Cổ phần Sữa Việt Nam (Vinamilk)",
                "company_ready_documents": company_documents,
                "company_ready_chunks": company_chunks,
            }
    finally:
        service.close()

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_level": "document and passage where labeled",
        "passage_judgments": {
            "enabled": any(case.get("relevant_chunk_ids") for case in cases),
            "case_count": sum(bool(case.get("relevant_chunk_ids")) for case in cases),
            "label_basis": json.loads(cases_bytes).get("passage_judgment_basis"),
        },
        "retrieval_methods": list(results),
        "case_count": len(cases),
        "case_file": args.cases.name,
        "case_file_sha256": cases_sha256,
        "candidate_passages_per_query": args.top_k,
        "model": service.embedding_service.model_name if service.embedding_service else None,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.system(),
            "architecture": platform.machine(),
            "gpu": gpu_metadata(),
        },
        "database_snapshot": database_snapshot,
        "configuration": {
            "authorization": "database allowed_roles filter before retrieval ranking",
            "fiscal_year_boost": "exact document fiscal_year match when query names one year",
            "bm25": {"k1": 1.2, "b": 0.75},
            "hybrid": [
                {"dense_weight": dense_weight, "bm25_weight": bm25_weight, "rrf_k": rrf_k}
                for dense_weight, bm25_weight, rrf_k in hybrid_configs
            ],
            "parent": {
                "first_stage": "dense child-chunk ranking",
                "child_candidates_per_query": min(args.top_k * 5, 100),
                "parent_context": "up to 2 neighboring chunks on either side with the same section title and page; same-page fallback when no section title exists",
                "max_parent_results": args.top_k,
            },
            "latency_note": "Dense, hybrid, and parent latency include first-use embedding model initialization on their first query; BM25 does not load the embedding model.",
        },
        "methods": results,
        "limitations": f"{len(cases)}-case demo set with manually assigned passage IDs tied to the current chunk-index snapshot; document and passage judgments are limited and need broader independent review. BM25 is a SQL implementation with k1=1.2 and b=0.75. Parent mode expands retrieved contexts, so its passage ranking is flattened from the returned child indices. No reranker or answer-generation comparison is included.",
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
