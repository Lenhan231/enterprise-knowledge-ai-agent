#!/usr/bin/env python3
"""Validate and summarize two reranker reports over an identical candidate set."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_pair(left: dict, right: dict) -> list[tuple[dict, dict]]:
    for field in ("case_file_sha256", "candidate_sha256", "case_count", "candidate_k", "max_sequence_length"):
        if left.get(field) != right.get(field):
            raise ValueError(f"Reranker reports differ on {field}")
    if left.get("model_id") == right.get("model_id"):
        raise ValueError("Reports must represent two different reranker models")
    left_env, right_env = left.get("environment", {}), right.get("environment", {})
    for field in ("device", "platform", "python"):
        if left_env.get(field) != right_env.get(field):
            raise ValueError(f"Reranker reports differ on environment.{field}")

    left_cases = {case["id"]: case for case in left.get("results", [])}
    right_cases = {case["id"]: case for case in right.get("results", [])}
    if len(left_cases) != left.get("case_count") or left_cases.keys() != right_cases.keys():
        raise ValueError("Reranker reports do not contain the same unique cases")
    pairs = []
    for case_id in left_cases:
        a, b = left_cases[case_id], right_cases[case_id]
        for field in (
            "role", "candidate_count", "relevant_document_ids", "relevant_passage_ids",
            "dense_ranked_document_ids", "dense_ranked_passage_ids", "dense_metrics", "dense_passage_metrics",
        ):
            if a.get(field) != b.get(field):
                raise ValueError(f"Dense candidate baseline differs for {case_id}.{field}")
        pairs.append((a, b))
    return pairs


def compare_reports(left: dict, right: dict, left_path: Path, right_path: Path, device_name: str | None = None) -> dict:
    pairs = _validate_pair(left, right)
    left_key = left.get("model_key", left["model_id"])
    right_key = right.get("model_key", right["model_id"])
    metric_names = sorted(pairs[0][0]["reranked_passage_metrics"])
    paired_deltas = {}
    for metric in metric_names:
        deltas = [b["reranked_passage_metrics"][metric] - a["reranked_passage_metrics"][metric] for a, b in pairs]
        paired_deltas[metric] = {
            "right_minus_left_mean": round(sum(deltas) / len(deltas), 4),
            "right_wins": sum(delta > 0 for delta in deltas),
            "ties": sum(delta == 0 for delta in deltas),
            "left_wins": sum(delta < 0 for delta in deltas),
        }
    return {
        "case_count": left["case_count"],
        "case_file_sha256": left["case_file_sha256"],
        "candidate_sha256": left["candidate_sha256"],
        "candidate_k": left["candidate_k"],
        "max_sequence_length": left["max_sequence_length"],
        "environment": {
            "device": left["environment"]["device"],
            "platform": left["environment"]["platform"],
            "python": left["environment"]["python"],
            "device_name": device_name,
        },
        "models": {
            left_key: {
                "model_id": left["model_id"],
                "model_revision": left.get("model_revision"),
                "passage_metrics": left["passage_aggregate"]["reranked"],
                "document_metrics": left["aggregate"]["reranked"],
                "mean_rerank_seconds_per_query": left["timing_seconds"]["mean_rerank"],
                "peak_process_rss_mb": left["environment"].get("peak_rss_mb"),
            },
            right_key: {
                "model_id": right["model_id"],
                "model_revision": right.get("model_revision"),
                "passage_metrics": right["passage_aggregate"]["reranked"],
                "document_metrics": right["aggregate"]["reranked"],
                "mean_rerank_seconds_per_query": right["timing_seconds"]["mean_rerank"],
                "peak_process_rss_mb": right["environment"].get("peak_rss_mb"),
            },
        },
        "common_dense_passage_metrics": left["passage_aggregate"]["dense"],
        "paired_passage_metric_deltas": paired_deltas,
        "source_reports": {
            str(left_path): hashlib.sha256(left_path.read_bytes()).hexdigest(),
            str(right_path): hashlib.sha256(right_path.read_bytes()).hexdigest(),
        },
        "timing_scope": "Rerank latency is measured on the Kaggle accelerator. Candidate retrieval was frozen on the source host before upload; dense retrieval latency is excluded from this model comparison.",
        "limitations": "Twelve cases with selected, non-exhaustive passage judgments. This is a paired ranking comparison, not semantic answer evaluation or a production model selection result.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--device-name", help="Hardware name recorded in the Kaggle run log")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/evaluation/vinamilk-reranker-kaggle-top30-paired-20260928.json")
    args = parser.parse_args()
    try:
        report = compare_reports(_read(args.left), _read(args.right), args.left, args.right, args.device_name)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(f"cannot compare reranker reports: {error}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "case_count": report["case_count"], "candidate_sha256": report["candidate_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
