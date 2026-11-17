"""Local Postgres + pgvector copy of the production knowledge index, for eval-v3 experiments (never production).

  python evaluation/v3/local_db.py up                         # start the container (127.0.0.1:55432)
  python evaluation/v3/local_db.py load <db> <chunks.jsonl>   # create <db> with the exported production vectors
  python evaluation/v3/local_db.py url <db>                   # print the DATABASE_URL for <db>

The password lives in artifacts/local/eval-v3/pg.env (gitignored). One database per embedding model keeps the
application code unchanged: only DATABASE_URL differs between experiments.
"""
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import psycopg

IMAGE = "pgvector/pgvector:0.8.0-pg16"
CONTAINER, PORT = "ekai-eval-pg", 55432
ENV = Path(os.environ.get("EVAL_V3_DIR", "artifacts/local/eval-v3")) / "pg.env"

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE documents (
    document_id text PRIMARY KEY, domain text, title text, year_or_version text, format text, verification text,
    document_type text, source_type text, allowed_roles text[] NOT NULL DEFAULT '{{}}', storage_path text,
    processing_status text NOT NULL, uploaded_by text, uploaded_at timestamptz, knowledge_base_active boolean NOT NULL
);
CREATE TABLE document_chunks (
    id bigint PRIMARY KEY, document_name text NOT NULL, chunk_index integer NOT NULL, content text NOT NULL,
    metadata jsonb NOT NULL, embedding vector({dim}) NOT NULL, created_at timestamptz DEFAULT now(),
    status text, expired_at timestamptz
);
CREATE INDEX ON document_chunks ((metadata->>'document_id'));
"""


def password():
    if not ENV.exists():
        ENV.parent.mkdir(parents=True, exist_ok=True)
        ENV.write_text(f"EVAL_PG_PASSWORD={secrets.token_urlsafe(24)}\n")
        ENV.chmod(0o600)
    return ENV.read_text().split("=", 1)[1].strip()


def url(db="postgres"):
    return f"postgresql://postgres:{password()}@127.0.0.1:{PORT}/{db}"


def up():
    running = subprocess.run(["docker", "ps", "-q", "-f", f"name=^{CONTAINER}$"], capture_output=True, text=True).stdout.strip()
    if running:
        print("already running")
        return
    subprocess.run(["docker", "run", "-d", "--name", CONTAINER, "-p", f"127.0.0.1:{PORT}:5432",
                    "-e", f"POSTGRES_PASSWORD={password()}", "-v", "ekai-eval-pg:/var/lib/postgresql/data", IMAGE], check=True)
    print("started", CONTAINER)


def load(db, chunks_path, vectors_path=None):
    """Load the exported chunks; with vectors_path (.npy, one row per chunk in file order) use those vectors instead."""
    rows = [json.loads(line) for line in open(chunks_path, encoding="utf-8")]
    if vectors_path:
        import numpy as np
        vectors = np.load(vectors_path)
        assert len(vectors) == len(rows), (len(vectors), len(rows))
        for row, vector in zip(rows, vectors):
            row["embedding"] = "[" + ",".join(f"{v:.7g}" for v in vector) + "]"
    dim = len(json.loads(rows[0]["embedding"]))
    with psycopg.connect(url(), autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{db}"')
        admin.execute(f'CREATE DATABASE "{db}"')
    with psycopg.connect(url(db)) as conn:
        conn.execute(SCHEMA.format(dim=dim))
        documents = {}
        for row in rows:
            doc = row["document"] or {}
            documents.setdefault(row["metadata"]["document_id"], (row["metadata"]["document_id"], doc.get("domain"), doc.get("title"),
                                 doc.get("format"), doc.get("type"), doc.get("allowed_roles") or [],
                                 doc.get("processing_status") or "ready", bool(doc.get("active"))))
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO documents (document_id, domain, title, format, document_type, allowed_roles, "
                            "processing_status, knowledge_base_active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", list(documents.values()))
            cur.executemany("INSERT INTO document_chunks (id, document_name, chunk_index, content, metadata, embedding, status, expired_at) "
                            "VALUES (%s,%s,%s,%s,%s,%s::vector,%s,%s)",
                            [(r["id"], r["document_name"], r["chunk_index"], r["content"], json.dumps(r["metadata"], ensure_ascii=False),
                              r["embedding"], r["status"], r["expired_at"]) for r in rows])
        count = conn.execute("SELECT count(*) FROM document_chunks").fetchone()[0]
    print(f"{db}: {count} chunks, {len(documents)} documents, vector({dim})")


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    {"up": up, "load": load, "url": lambda db: print(url(db))}[command](*args)
