#!/usr/bin/env python3
"""Prepare blinded QA review packets and import validated human ratings."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from score_qa_artifact import summarize_human_reviews  # noqa: E402


SCORE_FIELDS = ("faithfulness", "answer_relevancy", "context_precision")
COUNT_FIELDS = ("hallucinated_claim_count", "factual_claim_count")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def prepare_review(runs: list[Path], packet_path: Path, key_path: Path, seed: int | None = None) -> None:
    if len(runs) < 2:
        raise ValueError("Blinded model comparison requires at least two run artifacts")
    if packet_path.resolve() == key_path.resolve():
        raise ValueError("Review packet and private mapping key must be different files")

    loaded = [(path, read_json(path)) for path in runs]
    labels = [str(run.get("llm_model") or path.stem) for path, run in loaded]
    if len(set(labels)) != len(labels):
        raise ValueError("Each model run must have a distinct llm_model label")
    indexed = []
    expected_ids = None
    context_by_case = {}
    question_by_case = {}
    for model_index, (path, run) in enumerate(loaded):
        rows = {
            row["id"]: row for row in run.get("results", [])
            if row.get("id") and isinstance(row.get("answer"), str)
        }
        answer_rows = [row for row in run.get("results", []) if row.get("id") and isinstance(row.get("answer"), str)]
        if len(rows) != len(answer_rows) or not rows:
            raise ValueError(f"Run must contain uniquely identified answered cases: {path}")
        case_ids = set(rows)
        if expected_ids is None:
            expected_ids = case_ids
        elif case_ids != expected_ids:
            raise ValueError("Model artifacts must contain the same answer case IDs")
        for case_id, row in rows.items():
            context_hash = row.get("context_sha256")
            if not context_hash:
                raise ValueError(f"Missing context_sha256 for {labels[model_index]} / {case_id}")
            if case_id in context_by_case and context_by_case[case_id] != context_hash:
                raise ValueError(f"Retrieved contexts differ for case {case_id}; paired LLM review is invalid")
            context_by_case[case_id] = context_hash
            question = row.get("question")
            if case_id in question_by_case and question_by_case[case_id] != question:
                raise ValueError(f"Question differs for case {case_id}")
            question_by_case[case_id] = question
            indexed.append((model_index, path, case_id, row))

    response_rows = []
    private_map = {}
    for model_index, path, case_id, row in indexed:
        response_id = secrets.token_urlsafe(12)
        source_rows = [
            {
                "source_id": source.get("source_id"),
                "page_number": source.get("page_number"),
                "section_title": source.get("section_title"),
                "evidence": source.get("content_preview", ""),
            }
            for source in row.get("sources", [])
        ]
        response_rows.append({
            "response_id": response_id,
            "case_id": case_id,
            "question": row.get("question", ""),
            "answer": row["answer"],
            "insufficient_context": bool(row.get("insufficient_context")),
            "sources": source_rows,
            "review": {
                "faithfulness": None,
                "answer_relevancy": None,
                "context_precision": None,
                "hallucinated_claim_count": None,
                "factual_claim_count": None,
                "reviewer": None,
                "notes": None,
            },
        })
        private_map[response_id] = {
            "run_path": str(path.resolve()),
            "run_index": model_index,
            "model_label": labels[model_index],
            "case_id": case_id,
        }

    # Shuffle answers so a reviewer cannot infer the model from grouped order.
    import random
    random.Random(seed).shuffle(response_rows)
    packet = {
        "review_packet_version": 1,
        "rubric": {
            "scale": "1-5; 1=poor, 3=partly meets, 5=fully meets",
            "faithfulness": "Are factual claims supported by the cited source evidence?",
            "answer_relevancy": "Does the answer directly and completely address the question?",
            "context_precision": "Is the provided/cited evidence relevant to the question and answer?",
            "hallucinated_claim_count": "Count factual claims unsupported or contradicted by evidence.",
            "factual_claim_count": "Count all verifiable factual claims; exclude correct abstentions.",
            "reviewer": "Enter an anonymous reviewer ID. Judge against evidence without guessing model identity.",
        },
        "responses": response_rows,
    }
    key = {
        "review_packet_version": 1,
        "models": labels,
        "responses": private_map,
    }
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(key_path, 0o600)


def validate_review(review: dict, reviewer: str) -> dict:
    if not isinstance(review, dict):
        raise ValueError("Every response must contain a review object")
    normalized = {"reviewer": reviewer, "notes": review.get("notes")}
    for field in SCORE_FIELDS:
        value = review.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
            raise ValueError(f"{field} must be an integer from 1 to 5")
        normalized[field] = value
    for field in COUNT_FIELDS:
        value = review.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{field} must be a non-negative integer")
        normalized[field] = value
    if normalized["hallucinated_claim_count"] > normalized["factual_claim_count"]:
        raise ValueError("hallucinated_claim_count cannot exceed factual_claim_count")
    return normalized


def import_reviews(packet_paths: list[Path], key_path: Path, output_dir: Path) -> None:
    key = read_json(key_path)
    expected = set(key.get("responses", {}))
    if not expected:
        raise ValueError("Private key contains no response mappings")
    reviews_by_response = {response_id: [] for response_id in expected}
    reviewers = set()
    for packet_path in packet_paths:
        packet = read_json(packet_path)
        actual_ids = [row.get("response_id") for row in packet.get("responses", [])]
        if set(actual_ids) != expected or len(actual_ids) != len(expected):
            raise ValueError(f"Packet response IDs do not match private key: {packet_path}")
        packet_reviewers = set()
        for row in packet["responses"]:
            review = row.get("review") or {}
            reviewer = review.get("reviewer")
            if not isinstance(reviewer, str) or not reviewer.strip():
                raise ValueError(f"Reviewer ID is required in {packet_path}")
            reviewer = reviewer.strip()
            packet_reviewers.add(reviewer)
            reviews_by_response[row["response_id"]].append(validate_review(review, reviewer))
        if len(packet_reviewers) != 1:
            raise ValueError(f"Every response in a packet must use the same reviewer ID: {packet_path}")
        reviewer = next(iter(packet_reviewers))
        if reviewer in reviewers:
            raise ValueError(f"Reviewer ID must be unique across packets: {reviewer}")
        reviewers.add(reviewer)

    outputs = {}
    basenames = set()
    for response_id, reviews in reviews_by_response.items():
        mapping = key["responses"][response_id]
        run_path = Path(mapping["run_path"])
        if run_path not in outputs:
            if run_path.name in basenames:
                raise ValueError("Input run artifacts must have unique filenames for output")
            basenames.add(run_path.name)
            outputs[run_path] = read_json(run_path)
        row = next((r for r in outputs[run_path].get("results", []) if r.get("id") == mapping["case_id"]), None)
        if row is None:
            raise ValueError(f"Case {mapping['case_id']} is missing from {run_path}")
        existing = row.get("human_reviews", [])
        if not isinstance(existing, list):
            existing = [existing] if isinstance(existing, dict) else []
        existing_reviewers = {entry.get("reviewer") for entry in existing if isinstance(entry, dict)}
        if existing_reviewers.intersection(review["reviewer"] for review in reviews):
            raise ValueError(f"Reviewer already annotated case {mapping['case_id']}")
        row["human_reviews"] = [*existing, *reviews]

    output_dir.mkdir(parents=True, exist_ok=True)
    for run_path, report in outputs.items():
        report.setdefault("generation_metric_summary", {})["human_review"] = summarize_human_reviews(report.get("results", []))
        target = output_dir / run_path.name
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Create a blinded review packet and separate private mapping key")
    prepare.add_argument("--runs", nargs="+", required=True, type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--key-output", required=True, type=Path)
    prepare.add_argument("--seed", type=int, help="Optional deterministic shuffle seed for reproducible packet generation")
    import_cmd = commands.add_parser("import", help="Validate reviewer packets and annotate run artifacts")
    import_cmd.add_argument("--packets", nargs="+", required=True, type=Path)
    import_cmd.add_argument("--key", required=True, type=Path)
    import_cmd.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare_review(args.runs, args.output, args.key_output, args.seed)
    else:
        import_reviews(args.packets, args.key, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
