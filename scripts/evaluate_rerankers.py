#!/usr/bin/env python3
"""Evaluate cross-encoder rerankers on identical role-filtered dense candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.evaluation.retrieval_metrics import (  # noqa: E402
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

MODELS = {
    "bge-reranker-v2-m3": "BAAI/bge-reranker-v2-m3",
    "qwen3-reranker-0.6b": "Qwen/Qwen3-Reranker-0.6B",
}


def _ranked_documents(items: list[dict]) -> list[str]:
    return list(dict.fromkeys(item["document_id"] for item in items))


def _ranked_passages(items: list[dict]) -> list[str]:
    return [item["chunk_id"] for item in items]


def _passage_cutoffs(candidate_counts: list[int]) -> tuple[int, ...]:
    minimum = min(candidate_counts, default=0)
    if minimum <= 0:
        return ()
    if minimum < 3:
        return tuple(range(1, minimum + 1))
    return tuple(k for k in (1, 3, 5) if k <= minimum)


def _metrics(
    relevant: set[str],
    ranked: list[str],
    cutoffs: tuple[int, ...] = (1, 3, 5),
) -> dict[str, float]:
    return {
        **{f"precision@{k}": precision_at_k(relevant, ranked, k) for k in cutoffs},
        **{f"recall@{k}": recall_at_k(relevant, ranked, k) for k in cutoffs},
        "mrr": reciprocal_rank(relevant, ranked),
        **{f"ndcg@{k}": ndcg_at_k(relevant, ranked, k) for k in cutoffs},
    }


def _aggregate(results: list[dict], key: str) -> dict[str, float]:
    metric_names = results[0][key]
    return {
        name: round(sum(item[key][name] for item in results) / len(results), 4)
        for name in metric_names
    }


def _peak_rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(value / (1024 if sys.platform != "darwin" else 1024 * 1024), 1)


def _available_memory_mb() -> int | None:
    """Read host available memory without adding a runtime dependency."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _candidate_sha256(candidates: list[dict]) -> str:
    payload = [
        {"id": case["id"], "items": [{"chunk_id": item["chunk_id"], "text": item["text"]} for item in case["items"]]}
        for case in candidates
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _load_candidate_bundle(path: Path, cases: list[dict], cases_bytes: bytes, candidate_k: int) -> tuple[list[dict], str]:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    if bundle.get("schema") != "vinamilk-role-filtered-reranker-candidates-v1":
        raise ValueError("Unsupported candidate bundle schema")
    expected_case_hash = hashlib.sha256(cases_bytes).hexdigest()
    if bundle.get("case_file_sha256") != expected_case_hash:
        raise ValueError("Candidate bundle was built for a different labeled case file")
    by_id = {case["id"]: case for case in cases}
    bundled = {case["id"]: case for case in bundle.get("cases", [])}
    if len(bundled) != len(bundle.get("cases", [])) or bundled.keys() != by_id.keys():
        raise ValueError("Candidate bundle case IDs do not exactly match the selected labels")

    candidates = []
    for case_id, label in by_id.items():
        candidate = bundled[case_id]
        if (
            candidate.get("query") != label["question"]
            or candidate.get("role") != label["role"]
            or set(candidate.get("relevant_document_ids", [])) != set(label["relevant_document_ids"])
            or set(candidate.get("relevant_passage_ids", [])) != set(label.get("relevant_chunk_ids", []))
        ):
            raise ValueError(f"Candidate bundle labels or query changed for {case_id}")
        items = candidate.get("items")
        if not isinstance(items, list) or not items or len(items) > candidate_k:
            raise ValueError(f"Invalid candidate count for {case_id}")
        if any(not item.get("chunk_id") or not item.get("text") for item in items):
            raise ValueError(f"Candidate text is missing for {case_id}")
        if len({item["chunk_id"] for item in items}) != len(items):
            raise ValueError(f"Duplicate passage IDs for {case_id}")
        candidates.append(candidate)

    candidate_sha256 = _candidate_sha256(candidates)
    if bundle.get("candidate_sha256") != candidate_sha256:
        raise ValueError("Candidate bundle content hash does not match its metadata")
    return candidates, candidate_sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(MODELS))
    parser.add_argument("--cases", type=Path, default=REPO_ROOT / "data/evaluation/vinamilk_retrieval_cases.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate-input", type=Path, help="Use a hash-verified role-filtered dense candidate bundle; avoids database access")
    parser.add_argument("--export-candidates", type=Path, help="Export public role-filtered dense candidates without loading a reranker")
    parser.add_argument("--company", default="Công ty Cổ phần Sữa Việt Nam (Vinamilk)")
    parser.add_argument("--candidate-k", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--case-ids", nargs="+", help="Optional subset of labeled case IDs")
    parser.add_argument("--output-suffix", help="Optional artifact suffix for partial/smoke runs")
    parser.add_argument("--max-sequence-length", type=int, default=512)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument(
        "--max-memory-mb", type=int,
        help="Optional hard CPU memory budget measured from a completed pilot peak RSS, in MiB.",
    )
    args = parser.parse_args()
    if args.candidate_input and args.export_candidates:
        parser.error("--candidate-input and --export-candidates cannot be used together")
    if not args.export_candidates and not args.model:
        parser.error("--model is required unless exporting candidates")
    if not 1 <= args.candidate_k <= 100 or args.batch_size < 1 or args.max_sequence_length < 8:
        parser.error("candidate-k must be 1..100; batch-size positive; max-sequence-length at least 8")

    if args.max_memory_mb is not None and args.max_memory_mb < 1:
        parser.error("--max-memory-mb must be positive")

    load_dotenv(REPO_ROOT / ".env")
    if not args.candidate_input and not os.getenv("DATABASE_URL"):
        parser.error("DATABASE_URL is required")
    cases_bytes = args.cases.read_bytes()
    cases = json.loads(cases_bytes)["cases"]
    if args.case_ids:
        wanted = set(args.case_ids)
        cases = [case for case in cases if case["id"] in wanted]
        missing = wanted - {case["id"] for case in cases}
        if missing:
            parser.error(f"Unknown case IDs: {', '.join(sorted(missing))}")
    if not cases:
        parser.error("No labeled cases selected")

    if args.candidate_input:
        try:
            candidates, candidate_sha256 = _load_candidate_bundle(args.candidate_input, cases, cases_bytes, args.candidate_k)
        except (OSError, ValueError, KeyError, TypeError) as error:
            parser.error(f"invalid candidate bundle: {error}")
    else:
        from core.retrieval.retrieval import RetrievalRequest
        from core.retrieval.retrieval_service import RetrievalService
        from scripts.evaluate_retrieval import validate_passage_labels

        service = RetrievalService()
        candidates = []
        try:
            validate_passage_labels(service, cases, args.company)
            for case in cases:
                response = service.retrieve(
                    RetrievalRequest(query=case["question"], top_k=args.candidate_k),
                    company=args.company,
                    roles=case.get("allowed_roles", [case["role"]]),
                    method="dense",
                )
                items = [
                    {
                        "chunk_id": result.chunk_id,
                        "document_id": result.document_id,
                        "text": result.text,
                        "dense_score": result.score,
                    }
                    for result in response.results
                ]
                candidates.append({
                    "id": case["id"],
                    "query": case["question"],
                    "role": case["role"],
                    "relevant_document_ids": sorted(set(case["relevant_document_ids"])),
                    "relevant_passage_ids": sorted(set(case.get("relevant_chunk_ids", []))),
                    "retrieval_latency_ms": response.latency_ms,
                    "items": items,
                })
        finally:
            service.close()
    passage_cutoffs = _passage_cutoffs([len(case["items"]) for case in candidates])
    if not passage_cutoffs:
        parser.error("Dense retrieval returned no candidates for the selected cases")

    candidate_sha256 = _candidate_sha256(candidates)

    if args.export_candidates:
        export = {
            "schema": "vinamilk-role-filtered-reranker-candidates-v1",
            "case_file": args.cases.name,
            "case_file_sha256": hashlib.sha256(cases_bytes).hexdigest(),
            "candidate_sha256": candidate_sha256,
            "company": args.company,
            "candidate_method": "role-filtered-dense",
            "candidate_k": args.candidate_k,
            "cases": candidates,
            "limitations": "Public source excerpts only; candidates were retrieved with role filters before export. This bundle contains no database credentials or private uploads.",
        }
        args.export_candidates.parent.mkdir(parents=True, exist_ok=True)
        args.export_candidates.write_text(json.dumps(export, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.export_candidates), "case_count": len(candidates), "candidate_sha256": candidate_sha256}, ensure_ascii=False))
        return 0

    import torch
    from sentence_transformers import CrossEncoder

    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA was requested but is unavailable")
    available_memory_mb = _available_memory_mb()
    if (
        args.device == "cpu"
        and args.max_memory_mb is not None
        and available_memory_mb is not None
        and available_memory_mb < args.max_memory_mb
    ):
        parser.error(
            f"only {available_memory_mb} MiB is currently available, below the "
            f"pilot-measured --max-memory-mb budget ({args.max_memory_mb} MiB); "
            "wait for memory pressure to clear or lower the batch/sequence settings"
        )
    model_id = MODELS[args.model]
    load_started = time.perf_counter()
    model = CrossEncoder(model_id, max_length=args.max_sequence_length, device=args.device)
    model_load_seconds = time.perf_counter() - load_started
    model_revision = getattr(model.model.config, "_commit_hash", None)

    case_results = []
    for case in candidates:
        pairs = [(case["query"], item["text"]) for item in case["items"]]
        started = time.perf_counter()
        scores = np.asarray(model.predict(
            pairs,
            batch_size=args.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )).reshape(-1)
        rerank_latency_ms = (time.perf_counter() - started) * 1000
        reranked_items = sorted(
            (dict(item, rerank_score=float(score)) for item, score in zip(case["items"], scores)),
            key=lambda item: (-item["rerank_score"], item["chunk_id"]),
        )
        baseline_ranked = _ranked_documents(case["items"])
        reranked = _ranked_documents(reranked_items)
        relevant = set(case["relevant_document_ids"])
        result = {
            "id": case["id"],
            "role": case["role"],
            "candidate_count": len(case["items"]),
            "relevant_document_ids": sorted(relevant),
            "dense_ranked_document_ids": baseline_ranked,
            "reranked_document_ids": reranked,
            "dense_metrics": _metrics(relevant, baseline_ranked),
            "reranked_metrics": _metrics(relevant, reranked),
            "retrieval_latency_ms": round(case["retrieval_latency_ms"], 2),
            "rerank_latency_ms": round(rerank_latency_ms, 2),
        }
        relevant_passages = set(case["relevant_passage_ids"])
        if relevant_passages:
            dense_passages = _ranked_passages(case["items"])
            reranked_passages = _ranked_passages(reranked_items)
            result.update({
                "relevant_passage_ids": sorted(relevant_passages),
                "dense_ranked_passage_ids": dense_passages,
                "reranked_passage_ids": reranked_passages,
                "dense_passage_metrics": _metrics(relevant_passages, dense_passages, passage_cutoffs),
                "reranked_passage_metrics": _metrics(relevant_passages, reranked_passages, passage_cutoffs),
            })
        case_results.append(result)
        print(f"{case['id']} finished in {rerank_latency_ms:.0f} ms", file=sys.stderr, flush=True)

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_key": args.model,
        "model_id": model_id,
        "model_revision": model_revision,
        "case_count": len(cases),
        "case_file": args.cases.name,
        "case_file_sha256": hashlib.sha256(cases_bytes).hexdigest(),
        "candidate_sha256": candidate_sha256,
        "company": args.company,
        "candidate_method": "dense",
        "candidate_k": args.candidate_k,
        "max_sequence_length": args.max_sequence_length,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "device": args.device,
            "gpu_available": torch.cuda.is_available(),
            "peak_rss_mb": _peak_rss_mb(),
            "available_memory_at_model_load_mb": available_memory_mb,
            "max_memory_budget_mb": args.max_memory_mb,
        },
        "timing_seconds": {
            "model_load": round(model_load_seconds, 2),
            "mean_dense_retrieval": round(sum(item["retrieval_latency_ms"] for item in case_results) / len(case_results) / 1000, 4),
            "mean_rerank": round(sum(item["rerank_latency_ms"] for item in case_results) / len(case_results) / 1000, 4),
        },
        "aggregate": {
            "dense": _aggregate(case_results, "dense_metrics"),
            "reranked": _aggregate(case_results, "reranked_metrics"),
        },
        "passage_case_count": sum("dense_passage_metrics" in case for case in case_results),
        "passage_aggregate": {
            "dense": _aggregate(
                [case for case in case_results if "dense_passage_metrics" in case],
                "dense_passage_metrics",
            ),
            "reranked": _aggregate(
                [case for case in case_results if "reranked_passage_metrics" in case],
                "reranked_passage_metrics",
            ),
        } if any("dense_passage_metrics" in case for case in case_results) else {},
        "results": case_results,
        "limitations": "Small nine-query Vinamilk smoke set with selected, non-exhaustive passage judgments. Every model reranks the same dense top-k passages per case. Metrics measure ranking only, not answer quality, faithfulness, or user-perceived benefit. Full candidate and case hashes and model revision are recorded for comparability.",
    }
    suffix = f"-{args.output_suffix}" if args.output_suffix else ""
    output = args.output or REPO_ROOT / "artifacts/evaluation" / f"vinamilk-reranker-{args.model}{suffix}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "candidate_sha256": candidate_sha256, "aggregate": report["aggregate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
