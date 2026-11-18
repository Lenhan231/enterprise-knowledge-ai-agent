"""Generate Knowledge answers for a v3 set the way production does, paced to protect the shared Groq quota.

  DATABASE_URL=<local eval db> python evaluation/v3/answer.py <dev|test> <out.jsonl> [item ids...]

Knowledge settings come from the production .env (whitelisted, non-secret names) unless already set in the
environment, so an experiment overrides one setting and inherits the rest. Calls RAGService.generate_answer with the
same arguments KnowledgeAgent.run passes, and keeps the retrieved contexts for RAGAS context precision.
EVAL_PACE_SECONDS (default 8) waits between items; a rate limit pauses 10 minutes and retries the item (max 3).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SETTINGS = ("GROQ_MODEL", "KNOWLEDGE_MULTIQUERY_ENABLED", "KNOWLEDGE_CLAIM_VERIFICATION_ENABLED", "KNOWLEDGE_TOP_K",
            "KNOWLEDGE_CONTEXT_RADIUS", "QUERY_NORMALIZATION_ENABLED", "KNOWLEDGE_COMPLETENESS_RULE",
            "KNOWLEDGE_CONTEXT_MAX_CHARS", "KNOWLEDGE_STRICT_CITATION_RULE", "KNOWLEDGE_AUDIT_MAX_OUTPUT_TOKENS",
            "KNOWLEDGE_MULTIQUERY_MAX", "EMBEDDING_MODEL", "KNOWLEDGE_LLM_PROVIDER", "KNOWLEDGE_CLOUDFLARE_MODEL",
            "KNOWLEDGE_GROQ_MODEL", "RERANKER_MODEL", "RERANKER_QUANTIZE", "RERANKER_DEVICE")
PROD_ENV = Path(os.getenv("EVAL_PROD_ENV", Path.home() / "projects/ekai-prod/.env"))


def load_settings():
    for line in PROD_ENV.read_text().splitlines():
        name, _, value = line.partition("=")
        if name in SETTINGS and name not in os.environ:
            os.environ[name] = value.strip()
        elif name.startswith(("GROQ_API_KEY", "CLOUDFLARE_")) and name not in os.environ:  # used, never printed
            os.environ[name] = value.strip()


class ClaimCheckRateLimited(Exception):
    pass


def rate_limited(row):
    """The claim check swallows Groq rate limits and reports status 'unavailable', reason 'RateLimitError'."""
    # Cloudflare reports HTTP 429 and timeouts as RuntimeError.
    return "error" in row or str((row.get("verification") or {}).get("reason")) in ("RateLimitError", "RuntimeError")


def wait_for_active_hours():
    """EVAL_ACTIVE_HOURS=23-7 runs only between 23:00 and 07:00, to stay off quota the live site uses by day."""
    window = os.getenv("EVAL_ACTIVE_HOURS")
    if not window:
        return
    start, end = map(int, window.split("-"))
    while not (time.localtime().tm_hour >= start or time.localtime().tm_hour < end if start > end
               else start <= time.localtime().tm_hour < end):
        time.sleep(300)


def main(set_name, out_path, *only):
    load_settings()
    from openai import RateLimitError
    from core.rag.rag_service import RAGService
    items = json.load(open(ROOT / f"artifacts/evaluation/vietstyle-v3/{set_name}-v3.json", encoding="utf-8"))["items"]
    if Path(out_path).exists():  # a claim check cut short by a rate limit is not a result: drop it so it is redone
        rows = [l for l in open(out_path, encoding="utf-8") if l.strip() and not rate_limited(json.loads(l))]
        Path(out_path).write_text("".join(rows), encoding="utf-8")
    done = {json.loads(l)["id"] for l in open(out_path, encoding="utf-8")} if Path(out_path).exists() else set()
    rag = RAGService()
    config = {name: os.environ.get(name) for name in SETTINGS}
    config["commit"] = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                                      text=True).stdout.strip()
    try:
        with open(out_path, "a", encoding="utf-8") as out:
            for item in items:
                if item["id"] in done or (only and item["id"] not in only):
                    continue
                for attempt in range(3):
                    wait_for_active_hours()
                    started = time.perf_counter()
                    try:
                        # Same arguments as KnowledgeAgent.run (src/core/agents/knowledge/agent.py).
                        result = rag.generate_answer(
                            item["question"], decompose=os.environ.get("KNOWLEDGE_MULTIQUERY_ENABLED") == "1",
                            verify_claims=os.environ.get("KNOWLEDGE_CLAIM_VERIFICATION_ENABLED") == "1",
                            roles=[item["role"]], retrieval_method="translated_hybrid_rerank")
                        if not rate_limited({"verification": result.verification.model_dump() if result.verification else None}):
                            break
                        raise ClaimCheckRateLimited()
                    except (RateLimitError, ClaimCheckRateLimited, RuntimeError) as error:
                        if isinstance(error, RuntimeError) and "HTTP 429" not in str(error) and "timed out" not in str(error):
                            raise
                        print(item["id"], "rate limited; pausing 10 minutes", flush=True)
                        time.sleep(600)
                else:
                    out.write(json.dumps({"id": item["id"], "error": "rate_limited"}) + "\n")
                    continue
                verification = result.verification.model_dump() if result.verification else None
                out.write(json.dumps({
                    "id": item["id"], "answer": result.answer, "insufficient_context": result.insufficient_context,
                    "verification": verification, "withheld_draft": result.withheld_draft,
                    "cited": [{"source_id": c["source_id"], "document": c["document_name"], "chunk_index": c["chunk_index"]}
                              for c in result.contexts if c["source_id"] in set(result.source_ids)],
                    "contexts": [{"source_id": c["source_id"], "document": c["document_name"], "chunk_index": c["chunk_index"],
                                  "content": c["content"]} for c in result.contexts],
                    "latency_ms": round((time.perf_counter() - started) * 1000), "config": config,
                    "answered_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                }, ensure_ascii=False) + "\n")
                out.flush()
                status = (verification or {}).get("status") or ("not_covered" if result.insufficient_context else "no_check")
                print(item["id"], status, f"{(time.perf_counter() - started):.1f}s", flush=True)
                time.sleep(float(os.getenv("EVAL_PACE_SECONDS", "8")))
    finally:
        rag.close()


if __name__ == "__main__":
    main(*sys.argv[1:])
