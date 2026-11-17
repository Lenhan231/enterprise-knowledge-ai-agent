"""Run one retrieval method over a v3 set and save each item's ranked passages (no answer generation).

  DATABASE_URL=<local eval db> python evaluation/v3/retrieve.py <dev|test> <method> <top_k> <out.jsonl>

Methods are RetrievalService methods (dense, bm25, hybrid, translated_hybrid, translated_hybrid_rerank). Each item is
searched with its own role, exactly as the question is asked (follow-ups without their history, as Knowledge mode
receives them). Output lines: {"id", "method", "role", "latency_ms", "ranked": [{"document", "chunk_index", "score"}]}.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from core.retrieval.retrieval import RetrievalRequest  # noqa: E402
from core.retrieval import retrieval_service  # noqa: E402
from core.retrieval.retrieval_service import RetrievalService  # noqa: E402


def main(set_name, method, top_k, out_path):
    items = json.load(open(ROOT / f"artifacts/evaluation/vietstyle-v3/{set_name}-v3.json", encoding="utf-8"))["items"]
    if os.getenv("EVAL_DENSE_EXTRA") is not None:
        # Experiment switch: the number of dense passages added to reranking (#54); production uses the module default.
        retrieval_service.RERANK_DENSE_EXTRA = int(os.environ["EVAL_DENSE_EXTRA"])
    # Experiment switches for fusion (experiment 4); unset means the production defaults in RetrievalService.retrieve.
    fusion = {name: cast(os.environ[env]) for name, env, cast in (("dense_weight", "EVAL_DENSE_WEIGHT", float),
              ("bm25_weight", "EVAL_BM25_WEIGHT", float), ("rrf_k", "EVAL_RRF_K", int)) if os.getenv(env)}
    service = RetrievalService()
    done = set()
    if Path(out_path).exists():  # resume after a quota stop without redoing finished items
        done = {json.loads(line)["id"] for line in open(out_path, encoding="utf-8")}
    try:
        with open(out_path, "a", encoding="utf-8") as out:
            for item in items:
                if item["id"] in done:
                    continue
                started = time.perf_counter()
                response = service.retrieve(RetrievalRequest(query=item["question"], top_k=int(top_k)),
                                            roles=[item["role"]], method=method, **fusion)
                out.write(json.dumps({
                    "id": item["id"], "method": method, "role": item["role"],
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    "ranked": [{"document": r.source, "chunk_index": r.location.chunk_index, "score": r.score}
                               for r in response.results],
                }, ensure_ascii=False) + "\n")
                out.flush()
    finally:
        service.close()
    print(f"{set_name} {method}: {sum(1 for _ in open(out_path, encoding='utf-8'))} items in {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
