#!/usr/bin/env python3
"""Paired extractive context-compression diagnostic on the blinded QA packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / "artifacts/evaluation/qa-review-packet-full-evidence.json"
CASES = ROOT / "data/evaluation/archive/qa/vinamilk_qa_cases.json"
OUTPUT = ROOT / "artifacts/evaluation/vinamilk-context-compression-20260928.json"
TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _normal(text: str) -> str:
    return " ".join(TOKEN_RE.findall(unicodedata.normalize("NFKC", text).casefold()))


def compress_extractively(question: str, text: str, target_ratio: float = 0.5) -> str:
    """Keep query-overlapping sentences in source order; never paraphrase evidence."""
    if not 0 < target_ratio < 1:
        raise ValueError("target_ratio must be between zero and one")
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
    if len(sentences) < 2:
        return text
    query_terms = set(_normal(question).split())
    ranked = [
        (sum(token in query_terms for token in set(_normal(sentence).split())), index, sentence)
        for index, sentence in enumerate(sentences)
    ]
    candidates = sorted((row for row in ranked if row[0] > 0), key=lambda row: (-row[0], row[1]))
    budget = max(1, int(len(text) * target_ratio))
    selected: set[int] = set()
    used = 0
    for _, index, sentence in candidates:
        extra = len(sentence) + (2 if selected else 0)
        if used + extra > budget:
            continue
        selected.add(index)
        used += extra
    if not selected:
        return text
    compressed = "\n\n".join(sentence for index, sentence in enumerate(sentences) if index in selected)
    return compressed if len(compressed) < len(text) else text


def _fact_groups_present(groups: list[list[str]], evidence: str) -> list[bool]:
    normalized = _normal(evidence)
    return [any(_normal(phrase) in normalized for phrase in group) for group in groups]


def _fact_coverage(groups: list[list[str]], original: str, compressed: str) -> dict:
    before = _fact_groups_present(groups, original)
    after = _fact_groups_present(groups, compressed)
    return {
        "before": before,
        "after": after,
        "baseline_unchanged": before == after,
        "all_expected_present_before": bool(groups) and all(before),
        "all_expected_present_after": bool(groups) and all(after),
    }


def build_report(packet: dict, cases: dict, target_ratio: float = 0.5) -> dict:
    by_question = {case["question"]: case for case in cases["cases"]}
    rows = []
    for response in packet["responses"]:
        case = by_question.get(response["question"])
        if not case:
            continue
        sources = response.get("sources", [])
        original = "\n\n".join(source.get("evidence", "") for source in sources)
        compressed_sources = [
            {**source, "evidence": compress_extractively(response["question"], source.get("evidence", ""), target_ratio)}
            for source in sources
        ]
        compressed = "\n\n".join(source["evidence"] for source in compressed_sources)
        groups = case.get("expected_key_fact_groups", [])
        coverage = _fact_coverage(groups, original, compressed)
        rows.append({
            "case_id": case["id"],
            "response_id": response["response_id"],
            "question_sha256": hashlib.sha256(response["question"].encode()).hexdigest(),
            "source_ids": [source.get("source_id") for source in sources],
            "compressed_source_ids": [source.get("source_id") for source in compressed_sources],
            "source_characters_before": len(original),
            "source_characters_after": len(compressed),
            "compression_ratio": round(len(compressed) / max(1, len(original)), 4),
            "fact_groups_present_before": coverage["before"],
            "fact_groups_present_after": coverage["after"],
            "annotated_fact_group_count": len(groups),
            "annotated_fact_groups_present_before": sum(coverage["before"]),
            "annotated_fact_groups_present_after": sum(coverage["after"]),
            "baseline_fact_coverage_unchanged": coverage["baseline_unchanged"],
            "all_expected_fact_groups_present_before": coverage["all_expected_present_before"],
            "all_expected_fact_groups_present_after": coverage["all_expected_present_after"],
        })
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "query-term extractive sentence selection; no generation or paraphrase",
        "target_ratio": target_ratio,
        "packet_sha256": hashlib.sha256(PACKET.read_bytes()).hexdigest(),
        "qa_cases_sha256": hashlib.sha256(CASES.read_bytes()).hexdigest(),
        "response_count": len(rows),
        "distinct_case_count": len({row["case_id"] for row in rows}),
        "mean_character_ratio": round(sum(row["compression_ratio"] for row in rows) / max(1, len(rows)), 4),
        "baseline_fact_coverage_unchanged_count": sum(row["baseline_fact_coverage_unchanged"] for row in rows),
        "all_expected_fact_groups_present_before_count": sum(row["all_expected_fact_groups_present_before"] for row in rows),
        "all_expected_fact_groups_present_after_count": sum(row["all_expected_fact_groups_present_after"] for row in rows),
        "annotated_fact_groups_present_before_count": sum(row["annotated_fact_groups_present_before"] for row in rows),
        "annotated_fact_groups_present_after_count": sum(row["annotated_fact_groups_present_after"] for row in rows),
        "citation_source_ids_preserved_count": sum(row["source_ids"] == row["compressed_source_ids"] for row in rows),
        "rows": rows,
        "limitations": "Character count is a token-cost proxy, not tokenizer measurement. Repeated blind responses share questions and evidence, labels cover only annotated fact phrases, and no model answers or human ratings were generated. This diagnostic does not establish answer quality or justify production activation.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=PACKET)
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--target-ratio", type=float, default=0.5)
    args = parser.parse_args()
    packet_path = args.packet if args.packet.is_absolute() else ROOT / args.packet
    cases_path = args.cases if args.cases.is_absolute() else ROOT / args.cases
    output = args.output if args.output.is_absolute() else ROOT / args.output
    packet, cases = json.loads(packet_path.read_text()), json.loads(cases_path.read_text())
    report = build_report(packet, cases, args.target_ratio)
    report["packet_sha256"] = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    report["qa_cases_sha256"] = hashlib.sha256(cases_path.read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: report[key] for key in ("response_count", "distinct_case_count", "mean_character_ratio", "baseline_fact_coverage_unchanged_count", "all_expected_fact_groups_present_before_count", "all_expected_fact_groups_present_after_count", "citation_source_ids_preserved_count")}
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
