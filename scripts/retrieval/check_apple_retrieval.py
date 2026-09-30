#!/usr/bin/env python3
"""Measure the document-level dense-retrieval baseline on Apple questions."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.retrieval.retrieval import (  # noqa: E402
    RetrievalRequest,
    RetrievalResponse,
    make_chunk_id,
)
from core.retrieval.retrieval_service import RetrievalService  # noqa: E402


TOP_K = 5
K_VALUES = (1, 3, 5)
DEFAULT_FIXTURE = REPO_ROOT / "tests/fixtures/apple_dense_retrieval_cases.json"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts/review1/dense_retrieval_baseline.json"


def validate_cases(payload: object) -> list[dict]:
    if not isinstance(payload, list) or not payload:
        raise ValueError("fixture must be a non-empty list")

    cases = []
    for index, case in enumerate(payload, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"case {index} must be an object")
        question = case.get("question")
        expected = case.get("expected_document_ids")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"case {index} question must be non-empty")
        if (not isinstance(expected, list) or not expected
                or any(not isinstance(item, str) or not item.strip() for item in expected)):
            raise ValueError(f"case {index} expected_document_ids must be non-empty")
        cases.append({
            "question": question,
            "expected_document_ids": list(dict.fromkeys(expected)),
        })
    return cases


def load_cases(path: Path) -> list[dict]:
    return validate_cases(json.loads(path.read_text(encoding="utf-8")))


def result_provenance(result) -> dict:
    """Map retrieval fields needed later by the answer/evidence layer."""
    return {
        "rank": result.rank,
        "chunk_id": result.chunk_id,
        "document_id": result.document_id,
        "chunk_index": result.location.chunk_index,
        "source_document": result.source,
        "page_number": result.location.page_number,
        "section_title": result.location.section_title,
        "official_url": result.metadata.get("official_url"),
        "content": result.text,
        "similarity_score": result.score,
    }


def validate_response(response: RetrievalResponse, top_k: int = TOP_K) -> None:
    if len(response.results) > top_k:
        raise ValueError("response contains more results than top_k")
    if [result.rank for result in response.results] != list(
        range(1, len(response.results) + 1)
    ):
        raise ValueError("result ranks must be consecutive from 1")
    if any(
        current.score < following.score
        for current, following in zip(response.results, response.results[1:])
    ):
        raise ValueError("similarity scores must not increase with rank")

    for result in response.results:
        if result.chunk_id != make_chunk_id(
            result.document_id, result.location.chunk_index
        ):
            raise ValueError("chunk identity does not match document and index")
        provenance = result_provenance(result)
        for field in ("chunk_id", "document_id", "source_document"):
            if not provenance[field]:
                raise ValueError(f"result is missing {field}")
        if "citation_id" in result.model_dump():
            raise ValueError("citation_id belongs to the answer layer")


def evaluate_response(
    response: RetrievalResponse,
    expected_document_ids: list[str],
) -> dict:
    if not expected_document_ids:
        raise ValueError("expected_document_ids must be non-empty")
    validate_response(response)
    expected = set(expected_document_ids)
    hits = {}
    recalls = {}
    for k in K_VALUES:
        retrieved = {result.document_id for result in response.results[:k]}
        matched = retrieved & expected
        hits[k] = int(bool(matched))
        recalls[k] = len(matched) / len(expected)
    return {
        "question": response.query,
        "expected_document_ids": sorted(expected),
        "results": [result_provenance(result) for result in response.results],
        "hit": hits,
        "recall": recalls,
        "latency_ms": response.latency_ms,
    }


def evaluate_cases(retrieval, cases: list[dict]) -> tuple[list[dict], dict]:
    rows = []
    for case in validate_cases(cases):
        response = retrieval.retrieve(
            RetrievalRequest(query=case["question"], top_k=TOP_K)
        )
        rows.append(evaluate_response(response, case["expected_document_ids"]))

    summary = {
        "queries": len(rows),
        "hit": {k: statistics.mean(row["hit"][k] for row in rows) for k in K_VALUES},
        "recall": {
            k: statistics.mean(row["recall"][k] for row in rows) for k in K_VALUES
        },
        "mean_latency_ms": statistics.mean(row["latency_ms"] for row in rows),
        "median_latency_ms": statistics.median(row["latency_ms"] for row in rows),
    }
    return rows, summary


def print_report(rows: list[dict], summary: dict) -> None:
    for row in rows:
        print(f"\nQuestion: {row['question']}")
        print(f"Expected document IDs: {row['expected_document_ids']}")
        for rank, result in enumerate(row["results"], start=1):
            print(
                f"  Rank {rank} | Document {result['document_id']} | "
                f"Chunk {result['chunk_id']} | Score {result['similarity_score']:.4f}"
            )
        print(
            "  " + " | ".join(
                f"Hit@{k}={row['hit'][k]} Recall@{k}={row['recall'][k]:.3f}"
                for k in K_VALUES
            )
        )
        print(f"  Latency: {row['latency_ms']:.1f} ms")

    print("\nAggregate")
    print(f"Queries: {summary['queries']}")
    for k in K_VALUES:
        print(f"Hit@{k}: {summary['hit'][k]:.3f}")
    for k in K_VALUES:
        print(f"Recall@{k}: {summary['recall'][k]:.3f}")
    print(f"Mean latency: {summary['mean_latency_ms']:.1f} ms")
    print(f"Median latency: {summary['median_latency_ms']:.1f} ms")


def build_artifact(
    rows: list[dict], summary: dict, embedding_model: str, fixture_path: Path
) -> dict:
    resolved_fixture = fixture_path.resolve()
    fixture = (
        resolved_fixture.relative_to(REPO_ROOT)
        if resolved_fixture.is_relative_to(REPO_ROOT)
        else resolved_fixture
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip(),
        "embedding_model": embedding_model,
        "top_k": TOP_K,
        "fixture": str(fixture),
        "summary": {
            "queries": summary["queries"],
            **{f"hit_at_{k}": summary["hit"][k] for k in K_VALUES},
            **{f"recall_at_{k}": summary["recall"][k] for k in K_VALUES},
            "mean_latency_ms": summary["mean_latency_ms"],
            "median_latency_ms": summary["median_latency_ms"],
        },
        "results": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    retrieval = None
    try:
        cases = load_cases(args.fixture)
        retrieval = RetrievalService()
        # pgvector registration only reads catalogs; all evaluation queries after
        # this point are enforced as read-only on the existing connection.
        retrieval.repository.conn.rollback()
        retrieval.repository.conn.read_only = True
        rows, summary = evaluate_cases(retrieval, cases)
        print_report(rows, summary)
        artifact = build_artifact(
            rows, summary, retrieval.embedding_service.model_name, args.fixture
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Artifact written to: {args.output}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Evaluation failed: {error}", file=sys.stderr)
        return 2
    except Exception:
        print("Evaluation failed; retrieval error. Details suppressed.", file=sys.stderr)
        return 2
    finally:
        if retrieval is not None:
            retrieval.close()


if __name__ == "__main__":
    raise SystemExit(main())
