#!/usr/bin/env python3
"""Compare raw and ontology-expanded financial queries on labeled live retrieval."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from core.analytics.metric_ontology import METRIC_ONTOLOGY, resolve_metric_names  # noqa: E402
from core.evaluation.retrieval_metrics import ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank  # noqa: E402
from core.retrieval.retrieval import RetrievalRequest  # noqa: E402
from core.retrieval.retrieval_service import RetrievalService  # noqa: E402
from scripts.retrieval.evaluate_retrieval import gpu_metadata, ranked_passage_ids, validate_passage_labels  # noqa: E402

CASES = ROOT / "data/evaluation/archive/retrieval/vinamilk_retrieval_cases.json"
COMPANY = "Công ty Cổ phần Sữa Việt Nam (Vinamilk)"
FINANCIAL_METRICS = {
    "net_revenue", "total_consolidated_revenue", "profit_after_tax",
    "profit_before_tax", "total_assets", "cost_of_goods_sold", "gross_profit",
    "cash_and_equivalents", "state_budget_contribution",
}


def expand_metric_labels(question: str) -> str:
    """Append canonical English KPI names for recognized bilingual aliases."""
    labels = [
        METRIC_ONTOLOGY[name]["label"]
        for name in sorted(resolve_metric_names(question) & FINANCIAL_METRICS)
    ]
    missing = [label for label in labels if label.casefold() not in question.casefold()]
    return question if not missing else f"{question} {'; '.join(missing)}"


def score(result, case: dict) -> dict:
    relevant_docs = set(case["relevant_document_ids"])
    ranked_docs = list(dict.fromkeys(item.document_id for item in result.results))
    relevant_passages = set(case.get("relevant_chunk_ids", []))
    ranked_passages = ranked_passage_ids(result.results)
    return {
        "ranked_document_ids": ranked_docs,
        "ranked_passage_ids": ranked_passages,
        "document": {
            "precision@1": precision_at_k(relevant_docs, ranked_docs, 1),
            "recall@5": recall_at_k(relevant_docs, ranked_docs, 5),
            "mrr": reciprocal_rank(relevant_docs, ranked_docs),
            "ndcg@5": ndcg_at_k(relevant_docs, ranked_docs, 5),
        },
        "passage": {
            "precision@1": precision_at_k(relevant_passages, ranked_passages, 1),
            "recall@5": recall_at_k(relevant_passages, ranked_passages, 5),
            "mrr": reciprocal_rank(relevant_passages, ranked_passages),
            "ndcg@5": ndcg_at_k(relevant_passages, ranked_passages, 5),
        } if relevant_passages else {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.top_k <= 100:
        parser.error("--top-k must be between 1 and 100")
    cases_bytes = args.cases.read_bytes()
    cases = json.loads(cases_bytes)["cases"]
    service = RetrievalService()
    rows = []
    try:
        validate_passage_labels(service, cases, COMPANY)
        service.retrieve(
            RetrievalRequest(query="warm-up, excluded from scoring", top_k=1),
            company=COMPANY, roles=["finance_analyst"], method="hybrid",
        )
        for case in cases:
            rewritten = expand_metric_labels(case["question"])
            variants = {}
            paired_variants = (("raw", case["question"]), ("metric_label_expansion", rewritten))
            if len(rows) % 2:
                paired_variants = tuple(reversed(paired_variants))
            for name, query in paired_variants:
                result = service.retrieve(
                    RetrievalRequest(query=query, top_k=args.top_k),
                    company=COMPANY,
                    roles=case.get("allowed_roles", [case["role"]]),
                    method="hybrid",
                )
                variants[name] = {
                    "query": query,
                    "query_changed": query != case["question"],
                    "latency_ms": round(result.latency_ms, 2),
                    **score(result, case),
                }
            rows.append({"id": case["id"], "role": case["role"], "variants": variants})
            print(f"{case['id']} finished", file=sys.stderr, flush=True)
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
                (COMPANY,),
            )
            pg_version, total_documents, total_chunks, company_documents, company_chunks = cursor.fetchone()
            database_snapshot = {
                "postgres_version": pg_version,
                "all_documents": total_documents,
                "all_chunks": total_chunks,
                "company_ready_documents": company_documents,
                "company_ready_chunks": company_chunks,
            }
    finally:
        service.close()

    aggregates = {}
    for variant in ("raw", "metric_label_expansion"):
        cases_for_variant = [row["variants"][variant] for row in rows]
        aggregates[variant] = {
            group: {
                metric: round(sum(item[group][metric] for item in cases_for_variant) / len(cases_for_variant), 4)
                for metric in cases_for_variant[0][group]
            }
            for group in ("document", "passage")
            if cases_for_variant[0][group]
        }
        aggregates[variant]["mean_latency_ms"] = round(
            sum(item["latency_ms"] for item in cases_for_variant) / len(cases_for_variant), 2
        )

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "bilingual_metric_label_expansion",
        "rewrite_rule": "Append the canonical English metric label for each metric alias recognized by the shared ontology; leave all other queries unchanged.",
        "case_file": args.cases.name,
        "case_file_sha256": hashlib.sha256(cases_bytes).hexdigest(),
        "database_snapshot": database_snapshot,
        "company": COMPANY,
        "top_k": args.top_k,
        "method": {"retrieval": "hybrid", "dense_weight": 1.0, "bm25_weight": 2.0, "rrf_k": 60},
        "model": service.embedding_service.model_name if service.embedding_service else None,
        "environment": {"python": platform.python_version(), "platform": platform.system(), "gpu": gpu_metadata()},
        "query_changed_cases": sum(row["variants"]["metric_label_expansion"]["query_changed"] for row in rows),
        "case_count": len(rows),
        "aggregates": aggregates,
        "results": rows,
        "pairing": "Both variants run for every query with identical role, corpus, candidates, embedding model and hybrid weights; execution order alternates by case to reduce database-cache order bias.",
        "limitations": "Twelve manually labeled cases with selected, non-exhaustive passage judgments. This tests a deterministic ontology-based expansion, not LLM query rewriting or answer quality. It is an offline retrieval experiment and does not enable rewriting in production.",
    }
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "aggregates": aggregates}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
