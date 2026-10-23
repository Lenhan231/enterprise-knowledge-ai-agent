#!/usr/bin/env python3
"""Local candidate embeddings on frozen chunks; no database or inference API access."""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from time import perf_counter

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(Path(__file__).resolve().parent)]
from evaluate_embeddings import MODELS as EXISTING_MODELS, _visible

MODELS = {
    "multilingual-e5-base": {"model_id": "intfloat/multilingual-e5-base", "query_prefix": "query: ",
                             "passage_prefix": "passage: ", "instruction": None},
    "e5-large-v2": {"model_id": "intfloat/e5-large-v2", "query_prefix": "query: ",
                    "passage_prefix": "passage: ", "instruction": None},
    "bge-m3": EXISTING_MODELS["bge-m3"],
    "qwen3-embedding-0.6b": EXISTING_MODELS["qwen3-embedding"],
}


def inputs_for(spec, rows, cases):
    passages = [spec["passage_prefix"] + row["content"] for row in rows]
    queries = [spec["query_prefix"] + case["question"] for case in cases]
    if spec["instruction"]:
        queries = [f"Instruct: {spec['instruction']}\nQuery: {query}" for query in queries]
    return passages, queries


def token_lengths(tokenizer, texts, limit):
    lengths = [len(ids) for ids in tokenizer(texts, add_special_tokens=True,
                                           truncation=False, verbose=False)["input_ids"]]
    over = [(index, count) for index, count in enumerate(lengths) if count > limit]
    if over:
        raise ValueError(f"{len(over)} inputs exceed {limit} tokens after prefixes/special tokens; first: {over[:5]}. Frozen chunks were not changed.")
    return lengths


def unit_vectors(values):
    values = np.asarray(values, dtype=np.float32)
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if not np.isfinite(values).all() or not (norms > 0).all():
        raise ValueError("Embeddings must be finite and nonzero")
    return values / norms


def score_case(rows, passage_vectors, query_vector, case, evidence_context=None):
    eligible = np.array([i for i, row in enumerate(rows)
                         if _visible(row, case["allowed_roles"])
                         and ("target_language" not in case or row.get("language") == case["target_language"])], dtype=int)
    if not len(eligible):
        raise ValueError(f"No eligible chunks for {case['id']}")
    scores = passage_vectors[eligible] @ query_vector
    chosen = eligible[np.argsort(-scores, kind="stable")[:10]]
    expected = set(case["expected_sources"])
    found = sorted({Path(rows[i]["document_name"]).name for i in chosen} & expected)
    result = {"id": case["id"], "question": case["question"], "expected_sources": sorted(expected),
            "found_expected_sources": found, "missing_expected_sources": sorted(expected - set(found)),
            "unavailable_expected_sources": case["unavailable_expected_sources"],
            "source_recall_at_10": len(found) / len(expected) if expected else 0.0,
            "ranked_chunk_ids": [f"{rows[i]['document_id']}::chunk::{rows[i]['chunk_index']}" for i in chosen]}
    if "gold_pages" in case:
        pages = [f"{rows[i]['document_id']}::page::{rows[i]['metadata']['page_number']}" for i in chosen]
        gold = set(case["gold_pages"])
        if not gold:
            raise ValueError("Page-evidence cases require nonempty gold pages")
        result.update(direction=case["direction"], gold_pages=sorted(gold), ranked_pages=pages,
                      evidence_page_recall_at_10=len(gold & set(pages)) / len(gold),
                      evidence_page_reciprocal_rank_at_10=next((1 / rank for rank, page in enumerate(pages, 1) if page in gold), 0.0))
    if evidence_context is not None:
        from core.evaluation.evidence_metrics import score_evidence
        started = perf_counter()
        language = case["target_language"]
        result.update(direction=case["direction"], intent_id=case["intent_id"],
                      query_language=case["query_language"], target_language=language)
        result["evidence"] = score_evidence(
            evidence_context["data"], case["intent_id"], language,
            [{"text": rows[i]["content"], "metadata": rows[i]["metadata"]} for i in chosen],
            evidence_context["sources"][language], k=10)
        result["evidence_scoring_ms"] = (perf_counter() - started) * 1000
    return result


def load_evidence_context(config, cases, rows):
    """Validate frozen labels, questions and all mappings before model loading."""
    if "evidence" not in config:
        return None
    from validate_vietstyle_evidence import validate
    from core.evaluation.evidence_metrics import score_evidence
    raw = (ROOT / config["evidence"]["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != config["evidence"]["sha256"]:
        raise ValueError("Frozen evidence hash mismatch")
    data = json.loads(raw)
    validate(data)
    sources = {}
    for language, info in data["sources"].items():
        source_rows = [json.loads(line) for line in (ROOT / info["path"]).read_text().splitlines()]
        sources[language] = {(r["document_id"], r.get("parser_chunk_index", r.get("chunk_index"))): r["content"]
                             for r in source_rows}
        selected = [r for r in rows if r.get("language") == language]
        if not selected:
            raise ValueError(f"Empty {language} corpus")
        score_evidence(data, data["intents"][0]["id"], language,
                       [{"text": r["content"], "metadata": r["metadata"]} for r in selected],
                       sources[language], k=len(selected))
    intents = {q["id"]: q for q in data["intents"]}
    for case in cases:
        query_language, target_language = case["query_language"], case["target_language"]
        if (query_language not in sources or target_language not in sources
                or case["direction"] != query_language + "->" + target_language
                or case["question"] != intents[case["intent_id"]]["question"][query_language]):
            raise ValueError(f"Evidence case mismatch: {case['id']}")
    return {"data": data, "sources": sources}


def summarize_evidence(results):
    summary = {}
    for direction in sorted({r["direction"] for r in results}):
        selected = [r["evidence"] for r in results if r["direction"] == direction]
        eligible = [r for r in selected if r["full_intent_eligible"]]
        required = sum(r["required_ready"] for r in selected)
        met = sum(r["required_met"] for r in selected)
        full = sum(r["full_evidence_success"] for r in eligible)
        summary[direction] = {
            "cases": len(selected), "required_ready_components": required, "required_met_components": met,
            "required_component_coverage_at_10": met / required if required else None,
            "mean_case_component_coverage_at_10": mean(r["required_coverage"] for r in selected
                                                       if r["required_coverage"] is not None),
            "full_intent_eligible_cases": len(eligible), "full_evidence_cases_at_10": full,
            "full_evidence_success_rate_at_10": full / len(eligible) if eligible else None,
            "excluded_full_intent_ids": [r["intent_id"] for r in selected if not r["full_intent_eligible"]]}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--revision", help="Pin a specific model commit; otherwise resolve and record current commit")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--dtype", choices=("float32", "float16"), default="float32")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.batch_size < 1 or args.max_tokens < 1:
        parser.error("Batch size and token limit must be positive")
    folder = args.output_dir or args.snapshot / "candidates" / args.model
    if (folder / "results.json").exists() or (folder / "vectors.npy").exists():
        parser.error("Outputs already exist; use a different --output-dir to preserve previous runs")
    baseline_config = json.loads((args.snapshot / "benchmark-config.json").read_text())
    corpus_path = args.snapshot / baseline_config["indexed_corpus"]
    corpus_bytes = corpus_path.read_bytes()
    if hashlib.sha256(corpus_bytes).hexdigest() != baseline_config["indexed_corpus_sha256"]:
        raise ValueError("Frozen corpus hash mismatch")
    case_path = args.snapshot / baseline_config["cases"]
    case_bytes = case_path.read_bytes()
    cases = json.loads(case_bytes)["cases"]
    manifest = json.loads((args.snapshot / "manifest.json").read_text())
    if hashlib.sha256(case_bytes).hexdigest() != manifest[baseline_config["cases"] + "_sha256"]:
        raise ValueError("Frozen cases hash mismatch")
    rows = [json.loads(line) for line in corpus_bytes.decode().splitlines() if line.strip()]
    if not rows or not cases or {r["document_id"] for r in rows} != set(baseline_config["document_ids"]):
        raise ValueError("Frozen corpus/cases must be nonempty and match document scope")
    evidence_context = load_evidence_context(baseline_config, cases, rows)
    pinned_revision = baseline_config.get("candidate_revisions", {}).get(args.model)
    if evidence_context is not None and (not pinned_revision or (args.revision and args.revision != pinned_revision)):
        raise ValueError("Evidence benchmark requires the prepared candidate revision")
    spec = MODELS[args.model]
    passages, queries = inputs_for(spec, rows, cases)
    folder.mkdir(parents=True, exist_ok=True)
    config = {"status": "preflight", "candidate": args.model, **spec, "device": args.device,
              "dtype": args.dtype, "batch_size": args.batch_size, "max_sequence_length": args.max_tokens,
              "normalize_embeddings": True, "chunks": len(rows), "questions": len(cases),
              "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(), "cases_sha256": hashlib.sha256(case_bytes).hexdigest(),
              "row_order_sha256": hashlib.sha256(json.dumps([(r["document_id"], r["chunk_index"]) for r in rows]).encode()).hexdigest(),
              "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "created_at": datetime.now(timezone.utc).isoformat()}
    if evidence_context is not None:
        config.update(evidence=baseline_config["evidence"],
                      corpus_scope="Five target-language documents compete; all chunks, admin role. No gold-source filtering.",
                      evidence_scorer_sha256=hashlib.sha256((ROOT / "src/core/evaluation/evidence_metrics.py").read_bytes()).hexdigest())
    def save_config():
        (folder / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    save_config()
    try:
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import AutoTokenizer
        from sentence_transformers import SentenceTransformer
        if args.device == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA requested but unavailable; no automatic CPU fallback")
        metadata = Path(hf_hub_download(spec["model_id"], "config.json", revision=args.revision or pinned_revision))
        revision = metadata.parent.name
        config["revision"] = revision
        tokenizer = AutoTokenizer.from_pretrained(spec["model_id"], revision=revision, use_fast=True)
        passage_lengths = token_lengths(tokenizer, passages, args.max_tokens)
        query_lengths = token_lengths(tokenizer, queries, args.max_tokens)
        config.update(max_passage_tokens=max(passage_lengths), max_query_tokens=max(query_lengths), truncated_inputs=0)
        save_config()
        print(f"Preflight passed: {len(rows)} unchanged chunks, max passage {max(passage_lengths)} tokens; downloading/loading {spec['model_id']}", flush=True)
        started = perf_counter()
        model = SentenceTransformer(spec["model_id"], revision=revision, device=args.device,
                                    model_kwargs={"torch_dtype": getattr(torch, args.dtype)})
        if args.max_tokens > model.max_seq_length:
            raise ValueError(f"Requested {args.max_tokens} exceeds model's packaged limit {model.max_seq_length}")
        model.max_seq_length = args.max_tokens
        config["model_load_seconds"] = perf_counter() - started
        config["gpu_name"] = torch.cuda.get_device_name() if args.device == "cuda" else None
        config["dimensions"] = model.get_sentence_embedding_dimension()
        config["status"] = "encoding"
        save_config()
        if args.device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        started = perf_counter()
        vectors = unit_vectors(model.encode(passages, batch_size=args.batch_size, show_progress_bar=True,
                                            convert_to_numpy=True, normalize_embeddings=True, prompt=""))
        if vectors.shape != (len(rows), config["dimensions"]):
            raise ValueError("Vector matrix shape does not match frozen chunk order")
        config["corpus_embedding_seconds"] = perf_counter() - started
        np.save(folder / "vectors.npy", vectors)
        config["vectors_file_sha256"] = hashlib.sha256((folder / "vectors.npy").read_bytes()).hexdigest()
        results, query_vectors = [], []
        for case, query in zip(cases, queries):
            started = perf_counter()
            vector = unit_vectors(model.encode([query], convert_to_numpy=True, normalize_embeddings=True, prompt=""))[0]
            result = score_case(rows, vectors, vector, case, evidence_context)
            result["local_retrieval_latency_ms"] = (perf_counter() - started) * 1000 - result.get("evidence_scoring_ms", 0)
            results.append(result)
            query_vectors.append(vector)
            print(case["id"], f"source_recall@10={result['source_recall_at_10']:.4f}", flush=True)
        np.save(folder / "query-vectors.npy", np.asarray(query_vectors))
        config["query_vectors_file_sha256"] = hashlib.sha256((folder / "query-vectors.npy").read_bytes()).hexdigest()
        summary = {"mean_source_recall_at_10": mean(r["source_recall_at_10"] for r in results),
                   "full_source_recall_cases": sum(r["source_recall_at_10"] == 1 for r in results),
                   "mean_local_retrieval_latency_ms": mean(r["local_retrieval_latency_ms"] for r in results),
                   "median_local_retrieval_latency_ms": median(r["local_retrieval_latency_ms"] for r in results),
                   "peak_gpu_allocated_mib": torch.cuda.max_memory_allocated() / 1024**2 if args.device == "cuda" else None}
        if all("gold_pages" in case for case in cases):
            directions = sorted({r["direction"] for r in results})
            summary["by_direction"] = {}
            for direction in directions:
                selected = [r for r in results if r["direction"] == direction]
                summary["by_direction"][direction] = {
                    "cases": len(selected),
                    "mean_evidence_page_recall_at_10": mean(r["evidence_page_recall_at_10"] for r in selected),
                    "mrr_at_10": mean(r["evidence_page_reciprocal_rank_at_10"] for r in selected),
                    "full_evidence_page_cases": sum(r["evidence_page_recall_at_10"] == 1 for r in selected)}
        if evidence_context is not None:
            summary["by_direction"] = summarize_evidence(results)
        config["status"] = "completed"
        save_config()
        report = {"configuration": config, "summary": summary, "results": results,
                  "limitations": "Optional gold_pages scores measure evidence-page coverage among top ten chunks (duplicates count once); source-file scores measure file coverage. Neither measures exact-passage relevance or answer accuracy. Same frozen text/questions, with model-required input formatting. Missing README.txt stays in denominator. Local normalized cosine ranking; ties preserve frozen row order. Local timing excludes database/network and cannot be compared directly to the saved DB baseline timing. No database/inference API access. Model downloads may use Hugging Face metadata/weight HTTP endpoints; document text remains local."}
        if evidence_context is not None:
            report["limitations"] += " Evidence metrics use exact frozen source spans, AND requirements / OR complete alternatives; whitespace-only gaps ignored. Component coverage is not answer accuracy. Q14 has unresolved required labels, excluded from full-intent rate; ready components still counted. Source-file metric is historical diagnostic only. Four directions reuse 20 paired intents (80 cases, not 80 independent questions). English files/questions/labels are assistant-curated; alternative evidence may be incomplete. No translation, hybrid, reranker or generation. Latency excludes evidence scorer time."
        (folder / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print("SUMMARY", json.dumps(summary), flush=True)
    except Exception as error:
        config.update(status="failed", error_type=type(error).__name__)
        save_config()
        raise


if __name__ == "__main__":
    main()
