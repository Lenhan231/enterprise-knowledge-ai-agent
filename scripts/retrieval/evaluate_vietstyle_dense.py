#!/usr/bin/env python3
"""Read-only dense retrieval baseline against a verified frozen VietStyle index."""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads((args.snapshot / "benchmark-config.json").read_text())
    case_path = args.snapshot / config["cases"]
    cases = json.loads(case_path.read_text())["cases"]
    ids = config["document_ids"]
    for key in ("indexed_corpus", "vectors_file"):
        if hashlib.sha256((args.snapshot / config[key]).read_bytes()).hexdigest() != config[key + "_sha256"]:
            raise ValueError("Frozen " + key + " hash mismatch")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                      EMBEDDING_MAX_SEQUENCE_LENGTH=str(config["embedding_max_sequence_length"]))
    import numpy as np
    from core.database.document_chunks_repository import DocumentChunkRepository
    from core.embeddings.embedding_service import EmbeddingService
    from core.retrieval.retrieval import RetrievalRequest
    from core.retrieval.retrieval_service import RetrievalService
    repo = DocumentChunkRepository()
    service = None
    try:
        repo.conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        repo.conn.execute("SET LOCAL statement_timeout='30s'")
        rows = repo.conn.execute(
            "SELECT ch.document_name,ch.chunk_index,ch.content,ch.metadata,ch.embedding::text,d.allowed_roles "
            "FROM document_chunks ch JOIN documents d ON d.document_id=ch.metadata->>'document_id' "
            "WHERE d.document_id=ANY(%s::text[]) AND d.processing_status='ready' "
            "AND d.knowledge_base_active IS TRUE ORDER BY d.document_id,ch.chunk_index", (ids,)).fetchall()
        indexed = [{"document_id": r[3]["document_id"], "chunk_index": r[1], "document_name": r[0],
                    "content": r[2], "metadata": r[3], "allowed_roles": r[5]} for r in rows]
        raw = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in indexed).encode()
        if hashlib.sha256(raw).hexdigest() != config["indexed_corpus_sha256"]:
            raise ValueError("Live corpus differs from the frozen baseline; do not compare changed datasets")
        live_vectors = np.stack([np.fromstring(r[4].strip("[]"), sep=",", dtype=np.float32) for r in rows])
        if not np.array_equal(live_vectors, np.load(args.snapshot / config["vectors_file"])):
            raise ValueError("Live embeddings differ from frozen baseline")
        print(f"Verified {len(rows)} frozen chunks across {len(ids)} documents", flush=True)
        started = perf_counter()
        embedder = EmbeddingService(model_name=config["embedding_model"], backend_name="local")
        encoder = embedder._backend._client
        revision = getattr(encoder[0].auto_model.config, "_commit_hash", None)
        if revision != config["embedding_model_revision"] or encoder.max_seq_length != config["embedding_max_sequence_length"]:
            raise ValueError("Query encoder revision/limit differs from indexed baseline")
        load_seconds = perf_counter() - started
        service = RetrievalService(embedder, repo)
        results = []
        for case in cases:
            response = service.retrieve(RetrievalRequest(query=case["question"], top_k=10),
                                        method="dense", company="Commerce Demo", roles=["admin"], document_ids=ids)
            if any(chunk.document_id not in ids for chunk in response.results):
                raise ValueError("Retrieval escaped document scope")
            expected = set(case["expected_sources"])
            found = sorted({Path(chunk.source).name for chunk in response.results} & expected)
            results.append({"id": case["id"], "question": case["question"], "expected_sources": sorted(expected),
                            "found_expected_sources": found, "missing_expected_sources": sorted(expected - set(found)),
                            "unavailable_expected_sources": case["unavailable_expected_sources"],
                            "source_recall_at_10": len(found) / len(expected) if expected else 0.0,
                            "retrieval_latency_ms": response.latency_ms,
                            "retrieved_contexts": [chunk.model_dump() for chunk in response.results]})
            print(case["id"], f"source_recall@10={results[-1]['source_recall_at_10']:.4f}", flush=True)
        unavailable_ceiling = mean((len(set(c["expected_sources"])) - len(set(c["unavailable_expected_sources"])))
                                   / len(set(c["expected_sources"])) for c in cases)
        summary = {"question_count": len(results), "mean_source_recall_at_10": mean(r["source_recall_at_10"] for r in results),
                   "full_source_recall_cases": sum(r["source_recall_at_10"] == 1 for r in results),
                   "mean_retrieval_latency_ms": mean(r["retrieval_latency_ms"] for r in results),
                   "median_retrieval_latency_ms": median(r["retrieval_latency_ms"] for r in results),
                   "max_mean_source_recall_with_available_files": unavailable_ceiling}
        report = {"created_at": datetime.now(timezone.utc).isoformat(), "method": "dense", "top_k": 10,
                  "scope_document_ids": ids, "chunks": len(rows), "roles": ["admin"], "company": "Commerce Demo",
                  "embedding_model": embedder.model_name, "embedding_revision": revision,
                  "encoder_max_sequence_length": encoder.max_seq_length, "device": str(encoder.device),
                  "model_load_seconds": load_seconds, "corpus_sha256": config["indexed_corpus_sha256"],
                  "vectors_file_sha256": config["vectors_file_sha256"], "cases_sha256": hashlib.sha256(case_path.read_bytes()).hexdigest(),
                  "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "limitations": "Source-file coverage in top 10 chunks, not chunk relevance or answer accuracy. Missing README.txt stays in the denominator. No generation or translation. Latency includes query embedding/search/mapping, excludes model load; single run, not a controlled speed comparison. Different corpus/chunking/model from historical An runs.",
                  "summary": summary, "results": results}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print("SUMMARY", json.dumps(summary), flush=True)
    finally:
        repo.conn.rollback()
        if service is not None:
            service.close()
        else:
            repo.close()


if __name__ == "__main__":
    main()
