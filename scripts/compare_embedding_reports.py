#!/usr/bin/env python3
"""Verify and summarize paired proposal embedding benchmark reports."""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path


EXPECTED_MODELS = {
    "bge-m3": "BAAI/bge-m3",
    "qwen3-embedding": "Qwen/Qwen3-Embedding-0.6B",
    "e5-large-v2": "intfloat/e5-large-v2",
}
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = REPO_ROOT / "data/evaluation/vinamilk_public_embedding_corpus.jsonl"
DEFAULT_CASES = REPO_ROOT / "data/evaluation/vinamilk_retrieval_cases.json"
PAIR_FIELDS = (
    "case_file_sha256",
    "corpus_file_sha256",
    "sampled_corpus_sha256",
    "case_count",
    "corpus_chunks",
    "full_company_corpus_chunks",
    "sampled_chunks_per_document",
    "evaluation_level",
)


def comparable_configuration(report: dict) -> dict:
    configuration = dict(report.get("configuration") or {})
    configuration.pop("sample_strategy", None)
    return configuration


def load_report(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return report


def _verify_local_inputs(reports: list[dict], corpus_path: Path, cases_path: Path) -> dict:
    corpus_bytes = corpus_path.read_bytes()
    corpus_sha256 = hashlib.sha256(corpus_bytes).hexdigest()
    corpus = [json.loads(line) for line in corpus_bytes.decode("utf-8").splitlines() if line.strip()]
    cases_bytes = cases_path.read_bytes()
    cases_sha256 = hashlib.sha256(cases_bytes).hexdigest()
    cases_payload = json.loads(cases_bytes)
    cases = cases_payload.get("cases", [])

    grouped: dict[str, list[dict]] = {}
    for row in corpus:
        document_id = row.get("document_id")
        if not document_id or not isinstance(row.get("content"), str):
            raise ValueError("Local embedding corpus contains a row without document_id/content")
        grouped.setdefault(document_id, []).append(row)

    limits = {report.get("sampled_chunks_per_document") for report in reports}
    if len(limits) != 1 or not isinstance(next(iter(limits)), int) or next(iter(limits)) < 1:
        raise ValueError("Paired reports must have one positive per-document sample cap")
    limit = next(iter(limits))
    sampled = []
    for document_id in sorted(grouped):
        rows = grouped[document_id]
        if len(rows) <= limit:
            sampled.extend(rows)
        elif limit == 1:
            sampled.append(rows[len(rows) // 2])
        else:
            positions = [round(index * (len(rows) - 1) / (limit - 1)) for index in range(limit)]
            sampled.extend(rows[position] for position in positions)
    sampled_sha256 = hashlib.sha256(
        "\n".join(f"{row['document_id']}\0{row['content']}" for row in sampled).encode("utf-8")
    ).hexdigest()
    expected_strategy = (
        "all eligible passages per document (corpus fits per-document cap)"
        if len(sampled) == len(corpus) else "evenly spaced passages per document"
    )

    report_hashes_match = all(
        report.get("corpus_file_sha256") == corpus_sha256
        and report.get("sampled_corpus_sha256") == sampled_sha256
        and report.get("corpus_chunks") == len(sampled)
        and report.get("full_company_corpus_chunks") == len(corpus)
        and report.get("case_file_sha256") == cases_sha256
        and report.get("case_count") == len(cases)
        for report in reports
    )
    return {
        "corpus_path": str(corpus_path.resolve().relative_to(REPO_ROOT))
        if corpus_path.resolve().is_relative_to(REPO_ROOT) else str(corpus_path),
        "corpus_file_sha256": corpus_sha256,
        "case_path": str(cases_path),
        "case_file_sha256": cases_sha256,
        "case_count": len(cases),
        "full_corpus_chunks": len(corpus),
        "selected_chunks_after_per_document_cap": len(sampled),
        "sampled_corpus_sha256": sampled_sha256,
        "sampled_chunks_per_document_cap": limit,
        "observed_sample_strategy": expected_strategy,
        "all_report_counts_and_hashes_match": report_hashes_match,
        "verified": report_hashes_match,
    }


def compare_reports(
    paths: list[Path], corpus_path: Path | None = None, cases_path: Path | None = None,
) -> dict:
    reports = [load_report(path) for path in paths]
    by_model = {report.get("model_key"): (path, report) for path, report in zip(paths, reports)}
    if len(by_model) != len(reports) or set(by_model) != set(EXPECTED_MODELS):
        raise ValueError(f"Expected exactly these model keys: {sorted(EXPECTED_MODELS)}")

    first = by_model["bge-m3"][1]
    for model_key, (path, report) in by_model.items():
        if report.get("model_id") != EXPECTED_MODELS[model_key]:
            raise ValueError(f"Unexpected checkpoint for {model_key}: {report.get('model_id')}")
        if not report.get("model_revision"):
            raise ValueError(f"Missing model revision for {model_key}")
        if report.get("environment", {}).get("gpu_available") is not True:
            raise ValueError(f"GPU evaluation was not recorded for {model_key}")
        rows = report.get("results", [])
        if len(rows) != report.get("case_count") or not rows:
            raise ValueError(f"Expected one result per labeled case for {model_key}")
        for field in PAIR_FIELDS:
            if report.get(field) != first.get(field):
                raise ValueError(f"Paired reports differ in {field}: {path}")
        if comparable_configuration(report) != comparable_configuration(first):
            raise ValueError(f"Paired reports differ in configuration: {path}")

    baseline_rows = by_model["bge-m3"][1].get("results", [])
    baseline_ids = [row.get("id") for row in baseline_rows]
    if len(baseline_ids) != first.get("case_count") or len(set(baseline_ids)) != len(baseline_ids):
        raise ValueError("Each report must contain one result for every labeled case")

    cases = []
    for index, baseline in enumerate(baseline_rows):
        case_id = baseline["id"]
        model_results = {}
        for model_key, (_, report) in by_model.items():
            rows = report.get("results", [])
            if len(rows) != len(baseline_rows):
                raise ValueError(f"Case count differs for {model_key}")
            row = rows[index]
            for field in ("id", "role", "eligible_chunks", "relevant_document_ids"):
                if row.get(field) != baseline.get(field):
                    raise ValueError(f"Paired case differs in {field}: {model_key} / {case_id}")
            model_results[model_key] = {
                "ranked_document_ids": row.get("ranked_document_ids", []),
                "metrics": row.get("metrics", {}),
                "latency_ms": row.get("latency_ms"),
            }
        cases.append({
            "id": case_id,
            "role": baseline.get("role"),
            "eligible_chunks": baseline.get("eligible_chunks"),
            "relevant_document_ids": baseline.get("relevant_document_ids", []),
            "models": model_results,
        })

    local_verification = None
    if corpus_path is not None and cases_path is not None:
        local_verification = _verify_local_inputs(
            [report for _, report in by_model.values()], corpus_path, cases_path,
        )

    models = []
    source_reports = {}
    for model_key in EXPECTED_MODELS:
        path, report = by_model[model_key]
        claimed_full = report.get("corpus_chunks") == report.get("full_company_corpus_chunks")
        sample_strategy = report.get("configuration", {}).get("sample_strategy")
        stale_full_corpus_claim = claimed_full and sample_strategy != "all eligible passages per document (corpus fits per-document cap)"
        hash_verified = bool(local_verification and local_verification["verified"])
        source_reports[model_key] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "limitations_note": report.get("limitations"),
            "full_corpus_count_claim": claimed_full,
            "sample_strategy_claim": sample_strategy,
            "sample_strategy_metadata_mismatch": stale_full_corpus_claim,
            "sample_provenance_verified_by_hash": hash_verified,
            "provenance_conflict": stale_full_corpus_claim,
        }
        models.append({
            "model_key": model_key,
            "model_id": report["model_id"],
            "model_revision": report["model_revision"],
            "aggregate": report["aggregate"],
            "timing_seconds": report["timing_seconds"],
            "environment": report["environment"],
        })

    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark": "paired proposal embedding models on the manifest-allowlisted Vinamilk corpus",
        "paired_protocol": {
            **{field: first[field] for field in PAIR_FIELDS},
            "configuration_without_conflicting_sample_strategy": comparable_configuration(first),
        },
        "all_corpus_chunks_claimed": first["corpus_chunks"] == first["full_company_corpus_chunks"],
        "provenance_consistent": not any(item["provenance_conflict"] for item in source_reports.values()),
        "local_source_verification": local_verification,
        "corpus_coverage_verified_by_hash": bool(
            local_verification
            and local_verification["verified"]
            and local_verification["selected_chunks_after_per_document_cap"] == local_verification["full_corpus_chunks"]
            and first["corpus_chunks"] == first["full_company_corpus_chunks"]
        ),
        "source_reports": source_reports,
        "models": models,
        "cases": cases,
        "limitations": (
            "One run on 12 sparse document-level labels. Results do not measure passage-level retrieval, semantic answer quality, or human preference and are not a production model selection."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    args = parser.parse_args()
    try:
        comparison = compare_reports(args.reports, args.corpus, args.cases)
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "models": len(comparison["models"]), "cases": len(comparison["cases"]), "all_corpus_chunks_claimed": comparison["all_corpus_chunks_claimed"], "provenance_consistent": comparison["provenance_consistent"], "corpus_coverage_verified_by_hash": comparison["corpus_coverage_verified_by_hash"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
