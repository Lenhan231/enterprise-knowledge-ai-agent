"""Export the exact 24-question repo artifact to complete, Excel-compatible CSVs."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/benchmark/long_hau_2008.json"
OUT = ROOT / "artifacts/benchmark/exports"
REPO = "https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/QuocAn/"
OUT.mkdir(parents=True, exist_ok=True)
report = json.loads(SOURCE.read_text(encoding="utf-8"))
if len(report["results"]) != 24:
    raise ValueError("Expected 24 cases; refuse to silently mix benchmark versions.")

def emit(name, records):
    if not records: return
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

cases = []
gold = []
answers = []
contexts = []
for item in report["results"]:
    m = item["retrieval_metrics"]
    cases.append({
        "question_id": item["id"], "question": item["question"], "type": item["type"],
        "expected_sources": "; ".join(item["expected_sources"]),
        "expected_chunk_ids": "; ".join(item["expected_chunk_ids"]),
        "recall_at_k": m["recall_at_k"], "precision_at_k": m["precision_at_k"],
        "mrr": m["mrr"], "ndcg_at_k": m["ndcg_at_k"],
        "retrieval_latency_ms": item["retrieval_latency_ms"],
        "benchmark_url": REPO + "artifacts/benchmark/long_hau_2008.json",
    })
    for g in item["gold_evidence"]:
        gold.append({
            "question_id": item["id"], "chunk_id": g["chunk_id"],
            "document_id": g["document_id"], "document_name": g["document_name"],
            "chunk_index": g["chunk_index"], "page_number": g["page_number"],
            "gold_evidence_text": g["content"],
            "retrieved": g["chunk_id"] in {c["chunk_id"] for c in item["retrieved_contexts"]},
            "benchmark_url": REPO + "artifacts/benchmark/long_hau_2008.json",
        })
    for r in item["retrieved_contexts"]:
        contexts.append({
            "question_id": item["id"], "rank": r["rank"], "source_id": r["source_id"],
            "chunk_id": r["chunk_id"], "document_id": r["document_id"],
            "document_name": r["document_name"], "section_title": r.get("section_title", ""),
            "page_number": r["page_number"], "similarity_score": r["similarity_score"],
            "retrieval_method": r.get("retrieval_method", ""),
            "source_metadata_json": json.dumps(r.get("metadata", {}), ensure_ascii=False, sort_keys=True),
            "is_gold": r["chunk_id"] in item["expected_chunk_ids"],
            "retrieved_context_text": r["content"],
        })
    for model in report["model_names"]:
        a = item.get("models", {}).get(model, {})
        answers.append({
            "question_id": item["id"], "model": model,
            "question": item["question"], "answer": a.get("answer", ""),
            "source_ids": "; ".join(a.get("source_ids") or []),
            "prompt_sha256": a.get("prompt_sha256", ""),
            "insufficient_context": a.get("insufficient_context"),
            "error": a.get("error", ""),
            "generation_latency_ms": a.get("generation_latency_ms"),
            "faithfulness": "", "answer_relevancy": "", "context_precision": "",
            "hallucination_rate": "", "review_status": "PENDING",
            "benchmark_url": REPO + "artifacts/benchmark/long_hau_2008.json",
        })
emit("benchmark_24_questions.csv", cases)
emit("benchmark_27_gold_chunks.csv", gold)
emit("benchmark_72_model_answers.csv", answers)
emit("benchmark_retrieved_contexts.csv", contexts)
print(f"Exported {len(cases)} questions, {len(gold)} gold chunks, {len(answers)} model rows, {len(contexts)} retrieved chunks to {OUT}")
