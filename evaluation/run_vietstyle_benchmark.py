"""Run the full VietStyle QA benchmark with Huy's language-aware hybrid retrieval."""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.database.document_chunks_repository import DocumentChunkRepository
from core.embeddings import EmbeddingService
from core.llm.Cloudflare_provider import CloudflareProvider
from core.llm.groq_provider import GroqProvider
from core.llm.models import BENCHMARK_MODELS
from core.llm.openai_compatible_provider import OpenAICompatibleProvider
from core.rag.rag_service import RAGService
from core.retrieval.query_translator import QueryTranslator
from core.retrieval.retrieval import RetrievalRequest
from core.retrieval.retrieval_service import RetrievalService

CSV = Path(r"C:\Users\Admin\Downloads\VietStyle_RAG_Benchmark_20_Questions.csv")
OUT = ROOT / "artifacts/benchmark/vietstyle_q01-20_translated_hybrid.json"
LANGUAGES = {
    "01_Inventory_Management_Policy_Manual.docx": "vn",
    "02_SOP_Cycle_Count_and_Stock_Adjustment.pdf": "vn",
    "03_Policy_Rules_Registry.csv": "vn",
    "04_Inventory_Control_and_Reorder_Planner.xlsx": "vn",
    "05_Inventory_Policy_Training_Deck.pptx": "vn",
}
TOP_K = 10


def fuse(rankings, weights, k=60):
    scores = {}
    chunks = {}
    for ranking, weight in zip(rankings, weights):
        for rank, chunk in enumerate(ranking, 1):
            chunks[chunk.chunk_id] = chunk
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + weight / (k + rank)
    ordered_ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    return [chunks[chunk_id] for chunk_id in ordered_ids], {
        chunk_id: scores[chunk_id] for chunk_id in ordered_ids
    }


def make_provider(name):
    config = BENCHMARK_MODELS[name]
    if config.get("provider") == "cloudflare":
        return CloudflareProvider(model=config["model"])
    key = next((os.environ.get(env) for env in config["api_key_env"] if os.environ.get(env)), None)
    if not key:
        raise ValueError(f"Missing API key for {name}: {', '.join(config['api_key_env'])}")
    if "groq.com" in config.get("base_url", ""):
        return GroqProvider(model=config["model"], api_key=key)
    return OpenAICompatibleProvider(model=config["model"], base_url=config["base_url"], api_key=key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=CSV)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--models", nargs="+", choices=BENCHMARK_MODELS, default=list(BENCHMARK_MODELS))
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    with args.csv.open(encoding="utf-8-sig", newline="") as file:
        cases = list(csv.DictReader(file))
    if not cases:
        parser.error("The benchmark CSV has no questions")

    repository = DocumentChunkRepository()
    providers = {}
    translation_llm = None
    try:
        repository.conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        repository.conn.execute("SET LOCAL statement_timeout='60s'")
        documents = repository.conn.execute(
            "SELECT d.document_id, d.storage_path, d.processing_status, COUNT(c.id) "
            "FROM documents d LEFT JOIN document_chunks c "
            "ON d.document_id=c.metadata->>'document_id' "
            "WHERE d.company=%s GROUP BY d.document_id,d.storage_path,d.processing_status "
            "ORDER BY d.document_id",
            ("Commerce Demo",),
        ).fetchall()
        if not documents:
            raise ValueError("No Commerce Demo documents are indexed")

        document_ids = []
        languages = {"en": [], "vn": []}
        source_by_id = {}
        invalid = []
        for document_id, storage_path, status, chunk_count in documents:
            filename = str(storage_path or "").replace("\\", "/").rsplit("/", 1)[-1]
            if filename not in LANGUAGES:
                invalid.append(filename or document_id)
            elif status != "ready" or not chunk_count:
                invalid.append(f"{filename} ({status}, {chunk_count} chunks)")
            else:
                document_ids.append(document_id)
                languages[LANGUAGES[filename]].append(document_id)
                source_by_id[document_id] = (filename, LANGUAGES[filename])
        if invalid:
            raise ValueError(f"VietStyle scope is incomplete or contains other documents: {invalid}")
        if not document_ids:
            raise ValueError("No ready VietStyle policy documents with chunks were found")

        embedding_models = {row[0] for row in repository.conn.execute(
            "SELECT DISTINCT metadata->>'embedding_model' FROM document_chunks "
            "WHERE metadata->>'document_id'=ANY(%s::text[])", (document_ids,),
        ).fetchall()}
        if len(embedding_models) != 1 or None in embedding_models:
            raise ValueError(f"Expected one embedding model for VietStyle, found {embedding_models}")
        embedding_model = embedding_models.pop()
        retrieval = RetrievalService(EmbeddingService(model_name=embedding_model), repository)
        rag_by_model = {}
        for name in args.models:
            providers[name] = make_provider(name)
            rag_by_model[name] = RAGService(retrieval_service=retrieval, llm=providers[name])

        translation_llm = GroqProvider()
        translator = QueryTranslator(translation_llm)
        results = []
        for case in cases:
            question = case["Câu hỏi"]
            expected = [item.strip() for item in case["Nguồn mong đợi"].split(";") if item.strip()]
            translation_error = None
            try:
                translated = translator.translate(question, "vn")["en"]
            except Exception as error:
                translated = None
                translation_error = type(error).__name__

            dense = retrieval.retrieve(
                RetrievalRequest(query=question, top_k=TOP_K),
                company="Commerce Demo", roles=["admin"], method="dense", document_ids=document_ids,
            ).results
            lexical_rankings = []
            for language, query in (("en", translated), ("vn", question)):
                if query and languages[language]:
                    lexical_rankings.append(retrieval.retrieve(
                        RetrievalRequest(query=query, top_k=TOP_K),
                        company="Commerce Demo", roles=["admin"], method="bm25",
                        document_ids=languages[language],
                    ).results)
            lexical, _ = fuse(lexical_rankings, [1.0] * len(lexical_rankings))
            ranked, hybrid_scores = fuse([dense, lexical], [1.0, 2.0])
            contexts = [{
                "source_id": f"S{index}",
                "document_id": chunk.document_id,
                "document_language": source_by_id[chunk.document_id][1],
                "document_name": chunk.source,
                "chunk_index": chunk.location.chunk_index,
                "content": chunk.text,
                "retrieval_score": hybrid_scores[chunk.chunk_id],
                "metadata": {**chunk.metadata, "document_language": source_by_id[chunk.document_id][1]},
            } for index, chunk in enumerate(ranked[:TOP_K], 1)]
            retrieved_sources = {Path(context["document_name"]).name for context in contexts}
            generation = {}
            for name, rag in rag_by_model.items():
                try:
                    answer = rag.generate_from_contexts(question, contexts)
                    generation[name] = {
                        "answer": answer.answer,
                        "source_ids": answer.source_ids,
                        "insufficient_context": answer.insufficient_context,
                    }
                except Exception as error:
                    generation[name] = {"error": f"{type(error).__name__}: {error}"}

            results.append({
                "id": case["ID"], "question": question,
                "reference_answer": case["Đáp án chuẩn"],
                "expected_sources": expected,
                "found_expected_sources": sorted(retrieved_sources & set(expected)),
                "source_recall_at_10": round(len(retrieved_sources & set(expected)) / len(expected), 4) if expected else 0,
                "policy_id": case["Policy ID"], "scoring_criteria": case["Tiêu chí chấm"],
                "method": "translated_Hybrid", "translation_error": translation_error,
                "translated_query": translated,
                "scope_document_ids": document_ids,
                "retrieved_contexts": contexts, "generated": generation,
            })
            print(f"{case['ID']}: source_recall={results[-1]['source_recall_at_10']:.2f}", flush=True)

        report = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "benchmark": "VietStyle RAG Benchmark",
            "models": {name: BENCHMARK_MODELS[name]["model"] for name in args.models},
            "retrieval_method": "translated_Hybrid",
            "scope": {"company": "Commerce Demo", "document_ids": document_ids,
                      "document_languages": {doc_id: lang for doc_id, (_, lang) in source_by_id.items()}},
            "embedding_model": embedding_model, "top_k": TOP_K,
            "translation_model": translation_llm.model_name,
            "results": results,
            "summary": {
                "question_count": len(results),
                "mean_source_recall_at_10": round(sum(row["source_recall_at_10"] for row in results) / len(results), 4),
                "generation_completed": {
                    name: sum("answer" in row["generated"][name] for row in results)
                    for name in args.models
                },
            },
            "limitations": "README.txt is not indexed. Results are scoped to the active VietStyle company corpus. Translation is automatic; language metadata is currently an explicit benchmark mapping.",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved {args.output}")
    finally:
        repository.close()
        for provider in [*providers.values(), translation_llm]:
            if provider is not None:
                client = getattr(provider, "client", None)
                if client is not None:
                    client.close()
                elif hasattr(provider, "close"):
                    provider.close()


if __name__ == "__main__":
    main()
