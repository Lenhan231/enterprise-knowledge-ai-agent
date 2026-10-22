#!/usr/bin/env python3
"""Additional ranking metrics and context-loss diagnostics on frozen review cases.

No relabelling, downloads, model inference, external API calls or database writes.
Qrels include every frozen chunk with any mapped non-whitespace overlap with a
required evidence span, including alternatives and partially split spans. These
are support-chunk metrics; full evidence remains the AND/OR-aware primary check.
"""
import argparse
import contextlib
import csv
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import evaluate_translated_fresh_reranker as replay
from fresh_translated_candidates import FrozenRepository, SavedTranslator
from core.evaluation.retrieval_metrics import precision_at_k, recall_at_k, reciprocal_rank, ndcg_at_k
from core.evaluation.evidence_metrics import score_evidence
from core.retrieval.methods import translated_hybrid
from core.retrieval.retrieval import RetrievalRequest, make_chunk_id
from core.rag.rag_service import RAGService, MAX_CONTEXT_CHARS

ROOT = replay.ROOT
RESULTS = replay.INPUT / "colab-results"
METHODS = ("bm25_original", "dense", "hybrid_original", "translated_hybrid", "dense_bge", "translated_hybrid_bge")
METRICS = ("precision_at_10", "recall_at_10", "mrr_at_10", "ndcg_at_10", "full_evidence_at_10", "component_coverage_at_10")


def chunk(data, index):
    row = data["rows"][index]
    return {"text": row["content"], "metadata": row["metadata"]}


def evidence(data, case, chunks):
    return score_evidence(data["labels"], case["intent_id"], case["target_language"],
                          chunks, data["sources"][case["target_language"]], k=max(1, len(chunks)))


def support_relevance(scored):
    """Any exact mapped evidence overlap, not a claim a single chunk answers fully."""
    return any(value["covered_characters"] > 0 for value in scored["span_coverage"].values())


def ranking_metrics(qrels, ranking, k=10):
    if len(ranking) != len(set(ranking)):
        raise ValueError("Duplicate chunk IDs in ranking")
    if not qrels:
        raise ValueError("No annotated support chunks in corpus")
    return {"precision_at_10": precision_at_k(qrels, ranking, k),
            "recall_at_10": recall_at_k(qrels, ranking, k),
            "mrr_at_10": reciprocal_rank(qrels, ranking[:k]),
            "ndcg_at_10": ndcg_at_k(qrels, ranking, k)}


def clipped_chunk(row, content):
    """Clip source coordinates to the exact prefix actually delivered to generation."""
    if not row["content"].startswith(content):
        raise ValueError("Packed context is not an original chunk prefix")
    spans = []
    for original in row["metadata"]["source_spans"]:
        start, end = original["chunk_start"], min(original["chunk_end"], len(content))
        if start < end:
            spans.append({**original, "chunk_end": end,
                          "source_end": original["source_start"] + end - start})
    return {"text": content, "metadata": {**row["metadata"], "source_spans": spans}}


def context_probe(data, case, indices):
    contexts = [{"document_name": data["rows"][i]["document_name"],
                 "chunk_index": data["rows"][i]["chunk_index"],
                 "chunk_id": replay.base.previous.chunk_id(data["rows"][i]),
                 "content": data["rows"][i]["content"], "metadata": data["rows"][i]["metadata"],
                 "source_id": f"S{rank}", "retrieval_score": 0.0, "retrieval_method": "hybrid"}
                for rank, i in enumerate(indices, 1)]
    rag = RAGService(retrieval_service=SimpleNamespace(), llm=SimpleNamespace(model_name="offline-context-probe"))
    with patch("core.rag.rag_service.generate_with_provider_fallback", return_value=("Answer [S1]", "mock")), \
         patch("core.rag.rag_service.accumulate_token_usage", return_value=None), \
         patch("core.rag.rag_service._get_cached_response", return_value=None), \
         patch("core.rag.rag_service._cache_response"):
        result = rag.generate_answer(case["question"], roles=case["allowed_roles"], retrieved_contexts=contexts)
    if result.prompt_sha256 is None:
        return {"packing_applied": False, "reason": "pre-generation record-type/no-context guard"}
    by_id = {replay.base.previous.chunk_id(data["rows"][i]): i for i in indices}
    delivered = [clipped_chunk(data["rows"][by_id[c["chunk_id"]]], c["content"]) for c in result.contexts]
    score = evidence(data, case, delivered)
    return {"packing_applied": True, "delivered_chunks": len(delivered),
            "truncated_chunks": sum(len(c["text"]) < len(data["rows"][by_id[r["chunk_id"]]]["content"])
                                    for c, r in zip(delivered, result.contexts)),
            "delivered_content_characters": sum(len(c["text"]) for c in delivered),
            "full_evidence": score["full_evidence_success"], "component_coverage": score["required_coverage"],
            "missing_components": [r["id"] for r in score["requirements"] if r["required"] and not r["complete"]]}


def cluster_bootstrap(records, left, right, field, samples=10000):
    ids = sorted({r["intent_id"] for r in records})
    differences = np.asarray([np.mean([r["methods"][right][field] - r["methods"][left][field]
                                       for r in records if r["intent_id"] == intent]) for intent in ids])
    rng = np.random.default_rng(20261022)
    draws = differences[rng.integers(0, len(ids), size=(samples, len(ids)))].mean(axis=1)
    return {"delta": float(differences.mean()), "percentile_ci95": list(map(float, np.quantile(draws, [.025, .975]))),
            "intent_clusters": len(ids), "samples": samples, "seed": 20261022}


def load_verified():
    # Existing verifiers write an audit file; suppress that write to preserve all frozen artifacts.
    with contextlib.redirect_stdout(io.StringIO()), patch.object(replay.base, "save"):
        data = replay.load()
        replay.verify(data, RESULTS)
    report = replay.base.frozen.read(RESULTS / "results.json")
    return data, report


def additional_rankings(data):
    lexical = replay.base.frozen.read(replay.INPUT / "lexical-inputs.json")
    repository = FrozenRepository(data["rows"], data["vectors"], lexical["document_terms"], lexical["query_terms"])
    vectors = np.load(replay.BASELINE / "query-vectors.npy", allow_pickle=False)
    language_map = {r["document_id"]: "vn" if r["language"] == "vi" else "en" for r in data["rows"]}
    answer = []
    for case, vector in zip(data["cases"], vectors):
        scope = sorted({r["document_id"] for r in data["rows"] if r["language"] == case["target_language"]})
        kwargs = {"roles": case["allowed_roles"], "document_ids": scope}
        bm25 = repository.similarity_search(None, 30, query=case["question"], method="bm25", **kwargs)
        identity = SavedTranslator({case["question"]: {"error": None, "queries": {"en": case["question"], "vn": case["question"]}}}, "identity-no-translation")
        hybrid, _ = translated_hybrid.search(repository, vector, RetrievalRequest(query=case["question"], top_k=30),
            lambda: identity, document_languages={doc: language_map[doc] for doc in scope}, **kwargs)
        answer.append({"bm25_original": [make_chunk_id(c.document_id, c.chunk_index) for c in bm25],
                       "hybrid_original": [make_chunk_id(c.document_id, c.chunk_index) for c in hybrid]})
    return answer


def evaluate(data, saved):
    by_id = {replay.base.previous.chunk_id(row): i for i, row in enumerate(data["rows"])}
    controls = additional_rankings(data)
    qrels_cache = {}; records = []
    for n, (case, old) in enumerate(zip(data["cases"], saved["results"], strict=True)):
        if case["id"] != old["id"]:
            raise ValueError("Case order mismatch")
        key = (case["intent_id"], case["target_language"])
        if key not in qrels_cache:
            relevant = []
            for i, row in enumerate(data["rows"]):
                if row["language"] == case["target_language"] and support_relevance(evidence(data, case, [chunk(data, i)])):
                    relevant.append(replay.base.previous.chunk_id(row))
            qrels_cache[key] = relevant
        qrels = set(qrels_cache[key])
        rankings = {**controls[n], "dense": old["dense_candidates"], "dense_bge": old["dense_ranking"],
                    "translated_hybrid": old["translated_hybrid_candidates"],
                    "translated_hybrid_bge": old["translated_hybrid_ranking"]}
        methods = {}
        for method in METHODS:
            ranking = rankings[method]
            indices = [by_id[c] for c in ranking[:10]]
            score = evidence(data, case, [chunk(data, i) for i in indices])
            values = ranking_metrics(qrels, ranking)
            values.update(full_evidence_at_10=float(score["full_evidence_success"]),
                          component_coverage_at_10=score["required_coverage"],
                          required_met=score["required_met"], required_total=score["required_ready"],
                          missing_components=[r["id"] for r in score["requirements"] if r["required"] and not r["complete"]],
                          ranking=ranking[:10], annotated_relevant_chunks=len(qrels),
                          pool30_full_evidence=evidence(data, case, [chunk(data, by_id[c]) for c in ranking[:30]])["full_evidence_success"])
            if method in {"dense", "dense_bge", "translated_hybrid_bge"}:
                values["prompt_context_probe"] = context_probe(data, case, indices)
            methods[method] = values
        records.append({**case, "methods": methods})
        print(f"{n+1}/48 {case['id']}", flush=True)
    summary = {}
    for method in METHODS:
        summary[method] = {}
        for direction in ["all"] + sorted({r["direction"] for r in records}):
            selected = [r["methods"][method] for r in records if direction == "all" or r["direction"] == direction]
            summary[method][direction] = {"cases": len(selected), **{f: float(np.mean([r[f] for r in selected])) for f in METRICS},
                "complete_cases": sum(r["full_evidence_at_10"] for r in selected),
                "components_met": sum(r["required_met"] for r in selected), "components_total": sum(r["required_total"] for r in selected)}
    comparisons = {}
    for left, right in [("dense", "dense_bge"), ("dense_bge", "translated_hybrid_bge"),
                        ("hybrid_original", "translated_hybrid"), ("translated_hybrid", "translated_hybrid_bge")]:
        comparisons[left + "_to_" + right] = {
            "bootstrap": {field: cluster_bootstrap(records, left, right, field) for field in METRICS},
            "metric_regressions": {field: [r["id"] for r in records if r["methods"][right][field] < r["methods"][left][field] - 1e-12] for field in METRICS}}
    return records, summary, comparisons, [{"intent_id": i, "target_language": lang, "relevant_chunks": values} for (i, lang), values in qrels_cache.items()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("Choose a new output directory; preserve prior outputs")
    data, saved = load_verified()
    protected = [replay.base.frozen.OUT / "manifest.json", replay.base.frozen.OUT / "cases.json", replay.base.frozen.OUT / "evidence.json", RESULTS / "results.json", replay.BASELINE / "results.json"]
    hashes = {str(p.relative_to(ROOT)): replay.base.file_sha(p) for p in protected}
    records, summary, comparisons, qrels = evaluate(data, saved)
    if hashes != {str(p.relative_to(ROOT)): replay.base.file_sha(p) for p in protected}:
        raise ValueError("Frozen inputs changed")
    output = {"configuration": {"k": 10, "qrels": "union of all mapped non-whitespace overlaps with required evidence, including alternatives/partial spans",
        "mrr_cutoff": 10, "aggregation": "macro per case; intent-cluster bootstrap", "annotated_relevance_only": True,
        "unjudged_policy": "unannotated chunks count nonrelevant for these metrics; labels are not exhaustive",
        "hybrid_original_control": "production translated-hybrid fusion with identity queries, verified language scope; not a new LLM translation",
        "inference_run": False, "external_api_calls": False, "context_cap_chars": MAX_CONTEXT_CHARS,
        "source_hashes": hashes, "script_sha256": replay.base.file_sha(Path(__file__))},
        "summary": summary, "comparisons": comparisons, "qrels": qrels, "results": records}
    args.output_dir.mkdir(parents=True)
    replay.base.save(args.output_dir / "results.json", output)
    replay.base.save(args.output_dir / "qrels.json", qrels)
    with (args.output_dir / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["method", "direction", "cases", *METRICS])
        writer.writeheader()
        for method, directions in summary.items():
            for direction, values in directions.items():
                writer.writerow({"method": method, "direction": direction, **{f: values[f] for f in ["cases", *METRICS]}})
    print(json.dumps({m: values["all"] for m, values in summary.items()}, indent=2))


if __name__ == "__main__":
    main()
