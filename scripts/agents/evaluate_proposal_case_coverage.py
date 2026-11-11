#!/usr/bin/env python3
"""Validate proposal business-case coverage labels against the live corpus manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "data/evaluation/proposal_business_route_cases.json"
LABELS = ROOT / "data/evaluation/proposal_business_case_corpus_labels.json"
MANIFEST = ROOT / "data/vietnam_enterprises/manifest.json"
DEFAULT_OUTPUT = ROOT / "artifacts/evaluation/proposal-business-case-corpus-coverage.json"
STATUSES = {"supported", "partial", "unsupported"}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_coverage(routes: dict, labels: dict, manifest: dict) -> dict:
    route_cases = {case["id"]: case for case in routes.get("cases", [])}
    label_cases = {case["id"]: case for case in labels.get("cases", [])}
    if len(route_cases) != len(routes.get("cases", [])):
        raise ValueError("Route case IDs must be unique")
    if len(label_cases) != len(labels.get("cases", [])):
        raise ValueError("Coverage case IDs must be unique")
    if route_cases.keys() != label_cases.keys():
        raise ValueError("Coverage labels must match the proposal route case IDs")

    document_ids = {doc["document_id"] for doc in manifest.get("documents", [])}
    result_cases = []
    for case_id, route in route_cases.items():
        label = label_cases[case_id]
        status = label.get("corpus_coverage")
        if status not in STATUSES:
            raise ValueError(f"Invalid corpus_coverage for {case_id}: {status}")
        if label.get("expected_route") != route.get("expected_route"):
            raise ValueError(f"Expected route differs for {case_id}")
        source_ids = label.get("source_document_ids", [])
        missing = sorted(set(source_ids) - document_ids)
        if missing:
            raise ValueError(f"Unknown corpus source IDs for {case_id}: {missing}")
        result_cases.append({**route, **label})

    return {
        "dataset_id": labels["dataset_id"],
        "label_method": labels["label_method"],
        "corpus_id": manifest["corpus_id"],
        "corpus_manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "route_cases_sha256": hashlib.sha256(ROUTES.read_bytes()).hexdigest(),
        "corpus_document_count": len(document_ids),
        "coverage_counts": dict(sorted(Counter(c["corpus_coverage"] for c in result_cases).items())),
        "cases": result_cases,
        "limitations": [
            "Labels assess whether the specific requested evidence exists in this curated public corpus, not whether an agent route is implemented.",
            "Partial and unsupported cases must abstain from unsupported specifics; synthetic RBAC metadata is not evidence of document content.",
            "The inventory is public Vinamilk data and does not represent private HR, contract, invoice, manufacturing or customer-service repositories.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = evaluate_coverage(_read(ROUTES), _read(LABELS), _read(MANIFEST))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "corpus_document_count": result["corpus_document_count"], "coverage_counts": result["coverage_counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
