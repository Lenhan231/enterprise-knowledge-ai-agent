#!/usr/bin/env python3
"""Replace the active embedding index with E5 from hash-verified, exactly matching cached vectors.

Dry-run by default. Uses a transaction and a local recovery backup. Source chunks and identities stay
unchanged. Requires the exact original MiniLM corpus; refuses other source indexes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "artifacts/evaluation/embedding-comparison-20261018"
VECTOR_SHA = "7609b2446a50153b0a2fb0ab79cb72e6285aea4440228976283ecb2a769f3a91"
MODEL = "intfloat/multilingual-e5-base"
REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--backup", type=Path, default=ROOT / ".venv/e5-migration-recovery/minilm-index.json")
    args = parser.parse_args()
    import numpy as np
    import psycopg
    from psycopg.types.json import Jsonb
    from pgvector.psycopg import register_vector
    from dotenv import load_dotenv
    from transformers import AutoTokenizer
    load_dotenv(ROOT / ".env")
    folder = SOURCE / "candidates/multilingual-e5-base"
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    if (config["model_id"], config["revision"], config["query_prefix"], config["passage_prefix"],
        config["normalize_embeddings"], config["max_sequence_length"]) != (
            MODEL, REVISION, "query: ", "passage: ", True, 512):
        raise ValueError("Cached vector settings do not match the production E5 profile")
    vectors_path = folder / "vectors.npy"
    if hashlib.sha256(vectors_path.read_bytes()).hexdigest() != VECTOR_SHA:
        raise ValueError("Cached vector hash mismatch")
    vectors = np.load(vectors_path, allow_pickle=False)
    rows = [json.loads(line) for line in (SOURCE / "indexed-corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    expected = {(row["document_id"], row["chunk_index"]): (row, vector)
                for row, vector in zip(rows, vectors, strict=True)}
    if (len(expected) != len(rows) or vectors.shape != (len(rows), 768)
            or not np.isfinite(vectors).all()
            or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)):
        raise ValueError("Invalid vector identities/dimensions/normalization")
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, local_files_only=True)
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=15) as conn:
        register_vector(conn)
        conn.execute("SET LOCAL lock_timeout = '10s'")
        conn.execute("SET LOCAL statement_timeout = '120s'")
        conn.execute("LOCK TABLE public.document_chunks IN ACCESS EXCLUSIVE MODE")
        original = conn.execute("SELECT id, document_name, chunk_index, content, metadata, embedding::text, created_at::text, status, expired_at::text FROM public.document_chunks ORDER BY id").fetchall()
        digest = lambda values: hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        before = digest(original)
        if len(original) != len(rows):
            raise ValueError("Live corpus count changed; regenerate E5 vectors")
        payload = []
        for _, name, index, content, metadata, _, created, status, expired in original:
            source, vector = expected.get((metadata["document_id"], index), (None, None))
            if source is None or source["content"] != content or source["document_name"] != name:
                raise ValueError("Live corpus identity/content changed; regenerate E5 vectors")
            if len(tokenizer.encode("passage: " + content)) > 512:
                raise ValueError("A passage exceeds the pinned E5 token limit")
            if metadata.get("embedding_model") != "sentence-transformers/all-MiniLM-L6-v2":
                raise ValueError("Expected the original MiniLM source index")
            updated = dict(metadata, embedding_model=MODEL, embedding_revision=REVISION,
                           embedding_dimensions=768, embedding_normalized=True,
                           embedding_query_prefix="query: ", embedding_passage_prefix="passage: ",
                           embedding_max_sequence_length=512,
                           token_count=len(tokenizer.encode(content, add_special_tokens=False)))
            payload.append((name, index, content, Jsonb(updated), vector, created, status, expired))
        report = {"mode": "apply" if args.apply else "dry_run", "model": MODEL,
                  "revision": REVISION, "chunks": len(rows), "dimensions": 768,
                  "vectors_sha256": VECTOR_SHA, "legacy_table_sha256": before,
                  "source_content_preserved": True, "target": "public.document_chunks"}
        if args.apply:
            args.backup.parent.mkdir(parents=True, exist_ok=True)
            if args.backup.exists():
                if digest(json.loads(args.backup.read_text(encoding="utf-8"))) != before:
                    raise ValueError("Recovery backup differs from the current source index")
            else:
                args.backup.write_text(json.dumps(original, ensure_ascii=False) + "\n", encoding="utf-8")
            args.backup.chmod(0o600)
            # No partial state becomes visible: DDL and all vectors commit together.
            conn.execute("DROP INDEX IF EXISTS public.document_chunks_embedding_hnsw_idx")
            conn.execute("ALTER TABLE public.document_chunks ALTER COLUMN embedding DROP NOT NULL")
            conn.execute("ALTER TABLE public.document_chunks ALTER COLUMN embedding TYPE vector(768) USING NULL::vector(768)")
            with conn.cursor() as cursor:
                cursor.executemany(
                    "UPDATE public.document_chunks SET embedding=%s,metadata=%s WHERE metadata->>'document_id'=%s AND chunk_index=%s",
                    [(vector, metadata, metadata.obj["document_id"], index)
                     for _, index, _, metadata, vector, _, _, _ in payload])
            conn.execute("ALTER TABLE public.document_chunks ALTER COLUMN embedding SET NOT NULL")
            conn.execute("CREATE INDEX document_chunks_embedding_hnsw_idx ON public.document_chunks USING hnsw (embedding vector_cosine_ops)")
            actual = conn.execute("SELECT metadata->>'document_id',chunk_index,content,embedding FROM public.document_chunks").fetchall()
            if len(actual) != len(rows):
                raise ValueError("E5 index count mismatch")
            for doc, index, content, vector in actual:
                source, saved = expected[(doc, index)]
                if source["content"] != content or not np.allclose(vector.to_numpy() if hasattr(vector, "to_numpy") else vector, saved, atol=1e-7):
                    raise ValueError("E5 index verification failed")
            # IDs, names, text, status and timestamps must remain identical.
            preserved = conn.execute("SELECT id,document_name,chunk_index,content,created_at::text,status,expired_at::text FROM public.document_chunks ORDER BY id").fetchall()
            if preserved != [(r[0],r[1],r[2],r[3],r[6],r[7],r[8]) for r in original]:
                raise ValueError("Source identity or content changed")
            report["recovery_backup"] = str(args.backup.relative_to(ROOT))
            report["vectors_verified"] = len(actual)
        else:
            conn.rollback()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
