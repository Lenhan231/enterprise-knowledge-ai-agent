import json
import sys
from pathlib import Path
from time import perf_counter

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.llm.models import BENCHMARK_MODELS
from core.llm.groq_provider import GroqProvider
from core.rag.rag_service import RAGService
from core.retrieval.retrieval import RetrievalRequest
from core.retrieval.retrieval_service import RetrievalService


DATASET_PATH = REPO_ROOT / "evaluation" / "datasets.json"
OUTPUT_PATH = REPO_ROOT / "artifacts" / "evaluation" / "generation_benchmark_results.json"


def load_cached_contexts(dataset: list[dict], retrieval: RetrievalService) -> dict[str, list[dict]]:
    cached = {}

    for sample in dataset:
        response = retrieval.retrieve(
            RetrievalRequest(query=sample["question"], top_k=5)
        )
        cached[sample["id"]] = [
            {
                "document_name": chunk.source,
                "chunk_index": chunk.location.chunk_index,
                "content": chunk.text,
                "metadata": chunk.metadata,
                "similarity_score": chunk.score,
                "source_id": f"S{index}",
            }
            for index, chunk in enumerate(response.results, start=1)
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


with DATASET_PATH.open("r", encoding="utf-8") as f:
    dataset = json.load(f)

retrieval = RetrievalService()
cached_contexts = load_cached_contexts(dataset, retrieval)
results = []

try:
    for name, model_id in BENCHMARK_MODELS.items():
        llm = GroqProvider(model=model_id)
        rag = RAGService(retrieval_service=retrieval, llm=llm)

        for sample in dataset:
            contexts = cached_contexts[sample["id"]]

            start = perf_counter()

            result = rag.generate_from_contexts(
                question=sample["question"],
                contexts=contexts,
            )

            latency_ms = (perf_counter() - start) * 1000

            save_result(
                results,
                model_name=name,
                sample_id=sample["id"],
                result=result,
                latency_ms=latency_ms,
            )
finally:
    retrieval.close()

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")