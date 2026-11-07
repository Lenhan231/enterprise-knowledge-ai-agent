#!/usr/bin/env python3
"""Measure cached-local E5/SQL/BGE stages; translation is frozen replay, not timed API.

Creates session-local temporary replicas of the 1063 frozen chunks and 10 documents
on the configured PostgreSQL server. Persistent production tables are never written.
Uses existing production SQL and BGE functions, with target-language five-doc scope.
"""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import evaluate_fresh_retrieval_metrics as metrics
from fresh_translated_candidates import SavedTranslator
from core.retrieval.retrieval import RetrievalRequest, RetrievedChunk, make_chunk_id
from core.retrieval.retrieval_service import RetrievalService
from core.database.document_chunks_repository import DocumentChunkRepository
from core.embeddings import EmbeddingService
from core.retrieval.reranker import BGEReranker


class FixedQuery:
    model_name = "intfloat/multilingual-e5-base"
    def __init__(self):
        self.vector = None
    def embed_query(self, query):
        return self.vector


def prepare_tables(conn, data):
    from psycopg.types.json import Jsonb
    conn.execute("CREATE TEMP TABLE documents (document_id text PRIMARY KEY, document_type text, title text, source_url text, fiscal_year text, company text, allowed_roles text[], processing_status text, knowledge_base_active boolean) ON COMMIT DROP")
    conn.execute("CREATE TEMP TABLE document_chunks (id bigint PRIMARY KEY, document_name text, chunk_index integer, content text, metadata jsonb, embedding vector(768)) ON COMMIT DROP")
    documents = {}
    for row in data["rows"]:
        meta = row["metadata"]
        documents[row["document_id"]] = (row["document_id"], meta.get("document_type"), row["document_name"],
            meta.get("source_url"), meta.get("fiscal_year"), meta.get("company"), row["allowed_roles"], "ready", True)
    with conn.cursor() as cursor:
        cursor.executemany("INSERT INTO documents VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", list(documents.values()))
        cursor.executemany("INSERT INTO document_chunks VALUES (%s,%s,%s,%s,%s,%s)",
            [(i+1, row["document_name"], row["chunk_index"], row["content"], Jsonb(row["metadata"]), data["vectors"][i])
             for i, row in enumerate(data["rows"])])
    conn.execute("ANALYZE documents")
    conn.execute("ANALYZE document_chunks")
    temporary = conn.execute("SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid='document_chunks'::regclass").fetchone()[0]
    if not temporary.startswith("pg_temp_"):
        raise ValueError("Benchmark table is not temporary")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=48, help="Smoke subset or complete 48-case latency run")
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("Preserve previous outputs; choose a new output directory")
    if not 1 <= args.limit <= 48:
        raise ValueError("limit must be 1..48")
    data, _ = metrics.load_verified()
    import torch
    import psycopg
    from pgvector.psycopg import register_vector
    if not torch.cuda.is_available():
        raise RuntimeError("GPU unavailable; no implicit CPU fallback")
    os.environ["RERANKER_DEVICE"] = "cuda"
    os.environ["RERANKER_ALLOW_DOWNLOAD"] = "0"
    torch.set_num_threads(4)
    torch.manual_seed(0)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    args.output_dir.mkdir(parents=True)
    report = {"configuration": {"status": "loading", "device": torch.cuda.get_device_name(0), "dtype": "float32",
        "candidate_k": 30, "final_k": 10, "batch_size": 4, "passes": 1, "cases_requested": args.limit,
        "translation": "frozen replay; no API calls, API latency excluded", "persistent_database_writes": False,
        "database": "session-local frozen-corpus replica on configured PostgreSQL server",
        "scope": "5 target-language documents; 1063 passages in 10 documents total",
        "timing": "CUDA synchronized; warm model; fresh SQL and reranker inference per arm; query encoding timed once per case and shared across arms",
        "seed": 20261022, "cold_model_load_ms": None, "max_pair_tokens": 0,
        "limits": "Not full production/API/LLM latency; temporary SQL table size/IDs differ from production; one observation per case and method, not multi-seed inference stability."}, "results": []}
    output = args.output_dir / "results.json"
    def save():
        output.write_text(json.dumps(report, indent=2) + "\n")
    save()
    conn = None
    try:
        started = perf_counter()
        embedder = EmbeddingService(model_name="intfloat/multilingual-e5-base", backend_name="local")
        reranker = BGEReranker()
        warm = data["cases"][0]
        embedder.embed_query(warm["question"])
        warm_chunk = RetrievedChunk(document_name=data["rows"][0]["document_name"], chunk_index=0,
            content=data["rows"][0]["content"], metadata=data["rows"][0]["metadata"], retrieval_score=0)
        reranker.rerank(warm["question"], [warm_chunk], 1)
        torch.cuda.synchronize()
        report["configuration"]["cold_model_load_ms"] = (perf_counter() - started) * 1000
        conn = psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=15)
        register_vector(conn)
        conn.execute("SET LOCAL lock_timeout='10s'")
        conn.execute("SET LOCAL statement_timeout='30s'")
        prepare_tables(conn, data)
        fixed = FixedQuery()
        translations = metrics.replay.base.frozen.read(metrics.replay.INPUT / "translations.json")
        translator = SavedTranslator({r["question"]: r for r in translations["records"]}, translations["model"])
        repo = DocumentChunkRepository.__new__(DocumentChunkRepository)
        repo.conn = conn
        service = RetrievalService(fixed, repo, translator, reranker)
        language_map = {r["document_id"]: "vn" if r["language"] == "vi" else "en" for r in data["rows"]}
        by_id = {metrics.replay.base.previous.chunk_id(row): i for i, row in enumerate(data["rows"])}
        rng = np.random.default_rng(20261022)
        report["configuration"]["status"] = "running"
        for case in data["cases"][:args.limit]:
            torch.cuda.synchronize(); start = perf_counter()
            fixed.vector = embedder.embed_query(case["question"])
            torch.cuda.synchronize(); embedding_ms = (perf_counter() - start) * 1000
            scope = sorted({r["document_id"] for r in data["rows"] if r["language"] == case["target_language"]})
            options = {"roles": case["allowed_roles"], "document_ids": scope,
                       "document_languages": {doc: language_map[doc] for doc in scope}}
            row = {"id": case["id"], "direction": case["direction"], "embedding_ms": embedding_ms, "methods": {}}
            for arm in rng.permutation(["dense", "dense_bge", "translated_hybrid_bge"]):
                method = "translated_hybrid" if arm == "translated_hybrid_bge" else "dense"
                torch.cuda.synchronize(); start = perf_counter()
                retrieved = service.retrieve(RetrievalRequest(query=case["question"], top_k=30), method=method, **options)
                candidate_ms = (perf_counter() - start) * 1000
                chunks = [RetrievedChunk(document_name=r.source, chunk_index=r.location.chunk_index,
                    content=r.text, metadata=r.metadata, retrieval_score=r.score) for r in retrieved.results]
                rerank_ms = 0.0
                if arm != "dense":
                    lengths = reranker.model.tokenizer([case["question"]] * len(chunks), [c.content for c in chunks], truncation=False)["input_ids"]
                    max_length = max(map(len, lengths), default=0)
                    report["configuration"]["max_pair_tokens"] = max(report["configuration"]["max_pair_tokens"], max_length)
                    if max_length > 1024:
                        raise ValueError("Pair would truncate; preserve benchmark inputs")
                    torch.cuda.synchronize(); start = perf_counter()
                    chunks, _ = reranker.rerank(case["question"], chunks, 10)
                    torch.cuda.synchronize(); rerank_ms = (perf_counter() - start) * 1000
                else:
                    chunks = chunks[:10]
                ranking = [make_chunk_id(c.document_id, c.chunk_index) for c in chunks]
                score = metrics.evidence(data, case, [metrics.chunk(data, by_id[c]) for c in ranking])
                row["methods"][str(arm)] = {"candidate_ms": candidate_ms, "rerank_ms": rerank_ms,
                    "warm_stages_ms": embedding_ms + candidate_ms + rerank_ms,
                    "ranking": ranking, "full_evidence": score["full_evidence_success"],
                    "component_coverage": score["required_coverage"]}
            # Check the actual integrated selector against the stage-isolated pipeline.
            if not report["results"]:
                integrated = service.retrieve(RetrievalRequest(query=case["question"], top_k=10), method="translated_hybrid_rerank", **options)
                if [r.chunk_id for r in integrated.results] != row["methods"]["translated_hybrid_bge"]["ranking"]:
                    raise ValueError("Integrated method differs from stage-isolated pipeline")
                report["configuration"]["integrated_selector_smoke"] = "passed"
            report["results"].append(row)
            report["configuration"]["cases_completed"] = len(report["results"])
            save()
            print(f"{len(report['results'])}/{args.limit} {case['id']} " + " ".join(f"{a}={v['warm_stages_ms']:.0f}ms" for a, v in row['methods'].items()), flush=True)
        summary = {}
        for arm in ("dense", "dense_bge", "translated_hybrid_bge"):
            values = [r["methods"][arm] for r in report["results"]]
            summary[arm] = {field: {"median": float(np.median([v[field] for v in values])),
                "p95": float(np.quantile([v[field] for v in values], .95)), "mean": float(np.mean([v[field] for v in values]))}
                for field in ("candidate_ms", "rerank_ms", "warm_stages_ms")}
            summary[arm]["complete_evidence_cases"] = sum(v["full_evidence"] for v in values)
        report["summary"] = summary
        report["configuration"].update(status="completed", cuda_peak_allocated_bytes=torch.cuda.max_memory_allocated())
        save(); print(json.dumps(summary, indent=2))
    except Exception as error:
        report["configuration"].update(status="failed", error_type=type(error).__name__, error=str(error))
        save(); raise
    finally:
        if conn is not None:
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    main()
