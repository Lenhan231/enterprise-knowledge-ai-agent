import json
import os
import sys
import argparse
from pathlib import Path
from time import perf_counter

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.llm.models import BENCHMARK_MODELS
from core.llm.openai_compatible_provider import OpenAICompatibleProvider
from core.rag.rag_service import RAGService
from core.retrieval.retrieval import RetrievalRequest
from core.retrieval.retrieval_service import RetrievalService


DATASET_PATH = REPO_ROOT / "evaluation" / "datasets.json"
OUTPUT_PATH = REPO_ROOT / "artifacts" / "evaluation" / "revenue_model_comparison.json"
TOP_K = 10


def load_cached_contexts(dataset: list[dict], retrieval: RetrievalService) -> dict[str, list[dict]]:
    cached = {}

    for sample in dataset:
        response = retrieval.retrieve(
            RetrievalRequest(query=sample["question"], top_k=TOP_K)
        )
        expected_document_id = sample["expected_document_id"]
        relevant = [
            chunk for chunk in response.results
            if chunk.document_id == expected_document_id
        ]
        if not relevant:
            raise RuntimeError(
                f"Expected document {expected_document_id} was not retrieved "
                f"for {sample['id']} in top {TOP_K} results"
            )
        ordered = relevant + [
            chunk for chunk in response.results
            if chunk.document_id != expected_document_id
        ]
        cached[sample["id"]] = [
            {
                "document_name": chunk.source,
                "chunk_index": chunk.location.chunk_index,
                "content": chunk.text,
                "metadata": chunk.metadata,
                "similarity_score": chunk.score,
                "source_id": f"S{index}",
            }
            for index, chunk in enumerate(ordered, start=1)
        ]

    return cached


def save_result(results: list[dict], model_name: str, sample_id: str, result, latency_ms: float) -> None:
    results.append({
        "model_name": model_name,
        "sample_id": sample_id,
        "answer": result.answer,
        "source_ids": result.source_ids,
        "insufficient_context": result.insufficient_context,
        "latency_ms": latency_ms,
    })
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


parser = argparse.ArgumentParser()
parser.add_argument("--model", choices=BENCHMARK_MODELS, nargs="+")
parser.add_argument("--question-id", default="q01")
parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
args = parser.parse_args()

with DATASET_PATH.open("r", encoding="utf-8") as f:
    dataset = json.load(f)

sample = next(
    (item for item in dataset if item["id"] == args.question_id),
    None,
)
if sample is None:
    parser.error(f"Question ID not found: {args.question_id}")

retrieval = RetrievalService()
try:
    cached_contexts = load_cached_contexts([sample], retrieval)[sample["id"]]
    model_results = {}
    for name in args.model or BENCHMARK_MODELS:
        model_config = BENCHMARK_MODELS[name]
        api_key = next(
            (os.environ[key] for key in model_config["api_key_env"] if os.environ.get(key)),
            None,
        )
        if api_key is None:
            model_results[name] = {
                "error": f"Set one of {', '.join(model_config['api_key_env'])} to use {name}"
            }
            continue

        try:
            llm = OpenAICompatibleProvider(
                model=model_config["model"],
                base_url=model_config["base_url"],
                api_key=api_key,
            )
            rag = RAGService(retrieval_service=retrieval, llm=llm)
            start = perf_counter()
            result = rag.generate_from_contexts(
                question=sample["question"],
                contexts=cached_contexts,
            )
            model_results[name] = {
                "model": model_config["model"],
                "answer": result.answer,
                "source_ids": result.source_ids,
                "cited_document_ids": list(dict.fromkeys(
                    context["metadata"].get("document_id")
                    for context in cached_contexts
                    if context["source_id"] in result.source_ids
                    and context["metadata"].get("document_id")
                )),
                "insufficient_context": result.insufficient_context,
                "latency_ms": (perf_counter() - start) * 1000,
            }
        except Exception as error:
            model_results[name] = {
                "model": model_config["model"],
                "error": f"{type(error).__name__}: {error}",
            }

    output = {
        "question_id": sample["id"],
        "question": sample["question"],
        "expected_document_id": sample["expected_document_id"],
        "retrieved_document_ids": list(dict.fromkeys(
            context["metadata"].get("document_id")
            for context in cached_contexts
            if context["metadata"].get("document_id")
        )),
        "models": model_results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
finally:
    retrieval.close()