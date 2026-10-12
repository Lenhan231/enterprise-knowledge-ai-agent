"""Benchmark PVFCCo and Long Hau questions with saved retrieval evidence."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from time import perf_counter

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.database.document_chunks_repository import DocumentChunkRepository
from core.embeddings.embedding_service import EmbeddingService
from core.llm.models import BENCHMARK_MODELS
from core.llm.groq_provider import GroqProvider
from core.llm.openai_compatible_provider import OpenAICompatibleProvider
from core.rag.rag_service import RAGService
from core.retrieval.retrieval import RetrievalRequest, make_chunk_id
from core.retrieval.retrieval_service import RetrievalService

DATASET_PATH = REPO_ROOT / "evaluation" / "long_hau_2008_cases.json"
OUTPUT_PATH = REPO_ROOT / "artifacts" / "benchmark" / "long_hau_2008.json"
ANNUAL_REPORT_ID = "UPLOAD-11e62199551047c0a1ddcd5e6684a1c1"
LONG_HAU_FS_ID = "UPLOAD-5149fb823530440da1a2f09704c695d6"


def model_keys(names: list[str]) -> dict[str, str]:
    keys = {}
    for name in names:
        choices = BENCHMARK_MODELS[name]["api_key_env"]
        key = next((os.environ[value] for value in choices if os.environ.get(value)), None)
        if key is None:
            raise ValueError(f"Missing API key for {name}: {', '.join(choices)}")
        keys[name] = key
    if {"gpt_oss_20b", "qwen3"}.issubset(keys) and keys["gpt_oss_20b"] == keys["qwen3"]:
        raise ValueError("The two Groq models require distinct API keys")
    return keys


def serialize_contexts(chunks: list) -> list[dict]:
    return [
        {
            "source_id": f"S{index}", "rank": chunk.rank, "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id, "document_name": chunk.source,
            "chunk_index": chunk.location.chunk_index,
            "page_number": chunk.location.page_number,
            "section_title": chunk.location.section_title,
            "similarity_score": chunk.score, "content": chunk.text,
        }
        for index, chunk in enumerate(chunks, start=1)
    ]


def retrieval_metrics(contexts: list[dict], expected_ids: set[str]) -> dict:
    if not expected_ids:
        raise ValueError("Gold chunk IDs are required to score retrieval")
    found = {row["chunk_id"] for row in contexts} & expected_ids
    relevant = [row for row in contexts if row["chunk_id"] in expected_ids]
    first_rank = next((row["rank"] for row in relevant), None)
    seen = set()
    dcg = 0.0
    for row in contexts:
        chunk_id = row["chunk_id"]
        if chunk_id in expected_ids and chunk_id not in seen:
            dcg += 1 / math.log2(row["rank"] + 1)
            seen.add(chunk_id)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, len(expected_ids) + 1))
    return {
        "recall_at_k": round(len(found) / len(expected_ids), 4),
        "precision_at_k": round(len(relevant) / len(contexts), 4) if contexts else 0.0,
        "mrr": round(1 / first_rank, 4) if first_rank else 0.0,
        "ndcg_at_k": round(dcg / ideal, 4),
    }


def _plain(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", value.casefold()) if not unicodedata.combining(char))


def required_sources(cases: list[dict], source_ids: dict[str, str | None]) -> dict[str, str]:
    labels = {label for case in cases for label in case["expected_sources"]}
    missing = labels - {label for label in labels if source_ids.get(label)}
    if missing:
        raise ValueError(f"Missing document ID for: {', '.join(sorted(missing))}")
    return {label: source_ids[label] for label in labels}


def verify_sources(repository: DocumentChunkRepository, source_ids: dict[str, str]) -> None:
    if len(set(source_ids.values())) != len(source_ids):
        raise ValueError("Expected sources must use different documents")
    for label, document_id in source_ids.items():
        with repository.conn.cursor() as cursor:
            cursor.execute("SELECT title FROM documents WHERE document_id = %s", (document_id,))
            document = cursor.fetchone()
            cursor.execute("SELECT content FROM document_chunks WHERE metadata->>'document_id' = %s", (document_id,))
            chunks = cursor.fetchall()
        if not document or not chunks:
            raise ValueError(f"{label}: document or indexed chunks not found for {document_id}")
        content = _plain(" ".join(row[0] for row in chunks))
        marker = "petrovietnam fertilizer" if label == "annual_report" else "long hau"
        if marker not in content:
            raise ValueError(f"{label}: indexed document {document_id} does not mention {('PVFCCo' if label == 'annual_report' else 'LONG HAU')}")
        purpose = ("annual report", "bao cao thuong nien") if label == "annual_report" else ("bao cao tai chinh rieng",)
        if not any(term in content for term in purpose):
            raise ValueError(f"{label}: indexed document {document_id} does not look like {label.replace('_', ' ')}")


def load_gold_evidence(repository: DocumentChunkRepository, case: dict, source_ids: dict[str, str]) -> list[dict]:
    evidence = case["evidence"]
    if {item["source"] for item in evidence} != set(case["expected_sources"]):
        raise ValueError(f"{case['id']}: evidence sources do not match expected sources")
    gold = []
    for item in evidence:
        document_id = source_ids[item["source"]]
        with repository.conn.cursor() as cursor:
            cursor.execute(
                "SELECT document_name, content, metadata->>'page_number' "
                "FROM document_chunks WHERE metadata->>'document_id' = %s AND chunk_index = %s",
                (document_id, item["chunk_index"]),
            )
            row = cursor.fetchone()
        if not row or int(row[2]) != item["page_number"]:
            raise ValueError(f"{case['id']}: gold chunk {item['source']}:{item['chunk_index']} missing or page mismatch")
        gold.append({
            "chunk_id": make_chunk_id(document_id, item["chunk_index"]),
            "document_id": document_id, "document_name": row[0],
            "chunk_index": item["chunk_index"], "page_number": item["page_number"],
            "content": row[1],
        })
    return gold


def indexed_embedding_model(repository: DocumentChunkRepository) -> str:
    with repository.conn.cursor() as cursor:
        cursor.execute("SELECT DISTINCT metadata->>'embedding_model' FROM document_chunks")
        models = {row[0] for row in cursor.fetchall()}
    if len(models) != 1 or None in models:
        raise ValueError(f"Expected one labeled embedding model in document_chunks; found {models}")
    return models.pop()


def render_retrieval_markdown(report: dict) -> str:
    lines = ["# Benchmark retrieval evidence", ""]
    for row in report["results"]:
        lines.extend((f"## {row['id']} — {row['question']}", "", "### Gold evidence", ""))
        retrieved_ids = {item["chunk_id"] for item in row["retrieved_contexts"]}
        for gold in row["gold_evidence"]:
            lines.extend((
                f"{gold['document_name']} · chunk {gold['chunk_index']} · page {gold['page_number']}",
                f"Retrieved: {gold['chunk_id'] in retrieved_ids}", "",
                *(f"    {line}" for line in gold["content"].splitlines()), "",
            ))
        lines.extend(("### Retrieved top K", ""))
        for context in row["retrieved_contexts"]:
            lines.extend((
                f"#### [{context['source_id']}] rank {context['rank']} · {context['document_name']} · page {context['page_number']} · score {context['similarity_score']:.4f}",
                f"Document ID: `{context['document_id']}`", "",
                *(f"    {line}" for line in context["content"].splitlines()), "",
            ))
    return "\n".join(lines)


def score_human_reviews(report: dict) -> dict:
    from scripts.agents.score_qa_artifact import summarize_human_reviews

    return {
        name: summarize_human_reviews([
            row["models"].get(name, {}) for row in report["results"]
        ])
        for name in report["model_names"]
    }


def summarize_run(report: dict, elapsed_seconds: float) -> dict:
    rows = report["results"]
    completed = [
        (row["retrieval_latency_ms"], model["generation_latency_ms"])
        for row in rows for model in row["models"].values()
        if "generation_latency_ms" in model
    ]
    retrieval_scores = [row["retrieval_metrics"] for row in rows]
    return {
        "question_count": len(rows),
        "generation_completed": len(completed),
        "average_retrieval_latency_ms": round(mean(row["retrieval_latency_ms"] for row in rows), 2) if rows else None,
        "average_response_time_ms": round(mean(retrieval_ms + generation_ms for retrieval_ms, generation_ms in completed), 2) if completed else None,
        "observed_throughput_requests_per_second": round(len(completed) / elapsed_seconds, 4) if completed and elapsed_seconds > 0 else None,
        "retrieval_metrics_mean": {
            key: round(mean(score[key] for score in retrieval_scores), 4)
            for key in retrieval_scores[0]
        } if retrieval_scores and all(retrieval_scores) else None,
        "gpu_utilization": None,
        "scalability": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--annual-report-id", default=ANNUAL_REPORT_ID)
    parser.add_argument("--long-hau-fs-id", default=LONG_HAU_FS_ID)
    parser.add_argument("--inspect-only", action="store_true", help="Export retrieval without generation calls")
    parser.add_argument("--score-only", type=Path, help="Score manually reviewed benchmark JSON without API calls")
    parser.add_argument("--model", choices=BENCHMARK_MODELS, nargs="+")
    parser.add_argument("--question-id", nargs="+")
    parser.add_argument("--top-k", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.score_only:
        report = json.loads(args.score_only.read_text(encoding="utf-8"))
        report["human_score_summary"] = score_human_reviews(report)
        output = args.output if args.output != OUTPUT_PATH else args.score_only.with_name(args.score_only.stem + "_scored.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Human review scores: {output}")
        return 0
    if not 1 <= args.top_k <= 100:
        raise ValueError("--top-k must be between 1 and 100")
    load_dotenv(REPO_ROOT / ".env")
    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    if args.question_id:
        selected_ids = set(args.question_id)
        cases = [case for case in cases if case["id"] in selected_ids]
        if len(cases) != len(selected_ids):
            raise ValueError(f"Unknown question IDs: {sorted(selected_ids - {case['id'] for case in cases})}")
    source_ids = {"annual_report": args.annual_report_id, "long_hau_fs": args.long_hau_fs_id}
    selected_sources = required_sources(cases, source_ids)
    names = args.model or list(BENCHMARK_MODELS)
    keys = {} if args.inspect_only else model_keys(names)
    repository = DocumentChunkRepository()
    try:
        verify_sources(repository, selected_sources)
        embedding_model = indexed_embedding_model(repository)
        retrieval = RetrievalService(EmbeddingService(model_name=embedding_model), repository)
        providers = {
            name: (
                GroqProvider(model=BENCHMARK_MODELS[name]["model"], api_key=keys[name])
                if "groq.com" in BENCHMARK_MODELS[name]["base_url"] else
                OpenAICompatibleProvider(
                    model=BENCHMARK_MODELS[name]["model"],
                    base_url=BENCHMARK_MODELS[name]["base_url"],
                    api_key=keys[name],
                )
            )
            for name in names if not args.inspect_only
        }
        try:
            report = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "dataset": str(args.dataset), "embedding_model": embedding_model,
                "top_k": args.top_k, "source_document_ids": source_ids,
                "model_names": names if not args.inspect_only else [],
                "metric_notes": {
                    "recall_at_k": "fraction of gold chunk IDs present in top K chunks",
                    "precision_at_k": "fraction of retrieved top K chunks matching gold chunk IDs",
                    "mrr": "reciprocal rank of first gold chunk",
                    "ndcg_at_k": "binary gold-chunk relevance in original retrieval order",
                    "generation": "Faithfulness, answer relevancy, context precision and hallucination rate require human review against retrieved content",
                    "observed_throughput_requests_per_second": "sequential completed model calls divided by elapsed benchmark time; not a load-test throughput",
                },
                "results": [],
            }
            run_started = perf_counter()
            for case in cases:
                gold = load_gold_evidence(repository, case, source_ids)
                gold_ids = {item["chunk_id"] for item in gold}
                response = retrieval.retrieve(RetrievalRequest(query=case["question"], top_k=args.top_k))
                contexts = serialize_contexts(response.results)
                expected = [source_ids[label] for label in case["expected_sources"]]
                row = {
                    **case, "expected_document_ids": expected,
                    "expected_chunk_ids": sorted(gold_ids), "gold_evidence": gold,
                    "retrieval_latency_ms": round(response.latency_ms, 2),
                    "retrieval_metrics": retrieval_metrics(contexts, gold_ids),
                    "retrieved_contexts": contexts, "models": {},
                }
                for name, provider in providers.items():
                    started = perf_counter()
                    try:
                        result = RAGService(retrieval_service=retrieval, llm=provider).generate_from_contexts(
                            case["question"], [
                                {
                                    "source_id": context["source_id"],
                                    "document_name": context["document_name"],
                                    "chunk_index": context["chunk_index"],
                                    "content": context["content"],
                                    "similarity_score": context["similarity_score"],
                                    "metadata": {
                                        "document_id": context["document_id"],
                                        "page_number": context["page_number"],
                                        "section_title": context["section_title"],
                                    },
                                }
                                for context in contexts
                            ],
                        )
                        row["models"][name] = {
                            "answer": result.answer, "source_ids": result.source_ids,
                            "insufficient_context": result.insufficient_context,
                            "prompt_sha256": result.prompt_sha256,
                            "generation_latency_ms": round((perf_counter() - started) * 1000, 2),
                            "human_reviews": [],
                        }
                    except Exception as error:
                        row["models"][name] = {"error": type(error).__name__}
                report["results"].append(row)
                report["summary"] = summarize_run(report, perf_counter() - run_started)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                args.output.with_suffix(".md").write_text(render_retrieval_markdown(report), encoding="utf-8")
                print(f"{case['id']}: {len(contexts)} chunks")
        finally:
            for provider in providers.values():
                provider.client.close()
    finally:
        repository.close()
    print(f"Retrieval content and results: {args.output} / {args.output.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
