#!/usr/bin/env python3
"""Run one arm of vietstyle-heldout-v1 and save raw outputs; scoring is a separate step.

Runs inside the backend-api container (embeddings/reranker are only reachable there), e.g.
  docker compose exec -T backend-api python - --arm B2 --cases /benchmarks/vietstyle-heldout-v1/questions.json \
      --output /benchmarks/vietstyle-heldout-v1/runs/B2.json < scripts/agents/run_vietstyle_arm.py
The reranker is a separate service: arms that expect another reranker abort unless the service reports it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROD = dict(method="translated_hybrid_rerank", verify=True, reranker="mmarco-mMiniLM")
ARMS = {
    "A": dict(kind="retrieval"),  # --method picks dense|bm25|hybrid|translated_hybrid|translated_hybrid_rerank
    "B0": dict(kind="closed_book"),
    "B1": dict(method="dense", verify=False, prompt="old", reranker=None),
    "B2": PROD,
    "B3": {**PROD, "reranker": "bge-reranker-v2-m3"},  # restart the reranker service with RERANKER_MODEL=bge RERANKER_QUANTIZE=int8
    "B4": {**PROD, "verify": False},
    "B5": {**PROD, "prompt": "old"},
    "B6": {**PROD, "model": "openai/gpt-oss-120b"},
    "B7": {**PROD, "model": "openai/gpt-oss-20b"},
    "E2E": dict(kind="http"),  # production /api/chat in auto mode; the only arm that runs multi-turn cases
}
CLOSED_BOOK = ("Trả lời câu hỏi sau về chính sách vận hành doanh nghiệp VietStyle bằng tiếng Việt. "
               "Không có tài liệu nào được cung cấp; nếu không biết thì nói rõ là không biết.\n\nCâu hỏi:\n{question}")


def save(path, report):
    # Atomic replace so an interrupted run keeps the last complete file for --resume.
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    Path(stream.name).replace(path)


def context_row(context, cited):
    meta = context.get("metadata") or {}
    return {"source_id": context.get("source_id"), "cited": context.get("source_id") in cited,
            "document_name": context.get("document_name"), "document_id": meta.get("document_id"),
            "page_number": meta.get("page_number"), "chunk_index": context.get("chunk_index"),
            "score": context.get("similarity_score")}


class InProcess:
    def __init__(self, arm, args):
        from core.llm.groq_provider import GroqProvider
        from core.rag import rag_service
        self.arm, self.args = arm, args
        if arm.get("prompt") == "old":
            rag_service.ENTERPRISE_ASSISTANT_PROMPT = Path(args.old_prompt).read_text(encoding="utf-8")
        self.llm = GroqProvider(model=arm.get("model"))
        self.rag = rag_service.RAGService(llm=self.llm)

    def run(self, case, roles):
        from core.latency import latency_events, snapshot
        events = latency_events.set([])
        try:
            row = self._run(case, roles)
            row["stages_ms"] = {k: round(v) for k, v in snapshot()["stages_ms"].items() if v is not None}
            return row
        finally:
            latency_events.reset(events)

    def _run(self, case, roles):
        from core.agents.runtime import deadline
        kind = self.arm.get("kind")
        token = deadline.set(time.monotonic() + 60)
        try:
            if kind == "closed_book":
                return {"answer": self.llm.generate(CLOSED_BOOK.format(question=case["question"]))}
            if kind == "retrieval":
                contexts = self.rag.retrieve_contexts(case["question"], limit=10, roles=roles,
                                                      retrieval_method=self.args.method)
                return {"contexts": [context_row(c, ()) for c in contexts],
                        "retrieval_details": contexts[0]["retrieval_details"] if contexts else {}}
            result = self.rag.generate_answer(case["question"], roles=roles, retrieval_method=self.arm["method"],
                                              verify_claims=self.arm["verify"])
            details = result.contexts[0]["retrieval_details"] if result.contexts else {}
            expected = self.arm.get("reranker")
            if expected and details.get("reranker_model") and expected not in details["reranker_model"]:
                raise SystemExit(f"Reranker service runs {details['reranker_model']}, arm expects {expected}; stopped")
            return {"answer": result.answer, "insufficient_context": result.insufficient_context,
                    "source_ids": result.source_ids, "prompt_sha256": result.prompt_sha256,
                    "verification": result.verification.model_dump() if result.verification else None,
                    "contexts": [context_row(c, set(result.source_ids)) for c in result.contexts],
                    "retrieval_details": details}
        finally:
            deadline.reset(token)

    def close(self):
        self.rag.close()


class Http:
    def __init__(self, args):
        import httpx
        self.client = httpx.Client(base_url=args.base_url, timeout=180)
        response = self.client.post("/api/auth/login", json={"username": os.environ["DEMO_ADMIN_USERNAME"],
                                                              "password": os.environ["DEMO_ADMIN_PASSWORD"]})
        response.raise_for_status()
        token = response.cookies.get("enterprise_session")
        if not token:
            raise SystemExit("Login did not issue a session; stopped")
        # Secure cookies are not sent over plain HTTP to localhost; reuse the session as Bearer.
        self.client.headers["Authorization"] = "Bearer " + token

    def run(self, case, roles):
        conversation = f"vietstyle-{case['id']}-{uuid.uuid4().hex[:8]}"
        turns = []
        for question in [*case.get("history", []), case["question"]]:
            response = self.client.post("/api/chat", json={"question": question, "agent_mode": "auto",
                                                           "conversation_id": conversation})
            if response.status_code == 429:
                raise SystemExit("HTTP 429 rate limited; stopped")
            response.raise_for_status()
            turns.append(response.json())
        last = turns[-1]
        return {"answer": last.get("answer"), "evidence": last.get("evidence"), "metadata": last.get("metadata"),
                "history_answers": [turn.get("answer") for turn in turns[:-1]]}

    def close(self):
        self.client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arm", required=True, choices=ARMS)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--method", default="translated_hybrid_rerank", help="retrieval method for arm A")
    parser.add_argument("--old-prompt", default=None, help="prompt_pre_875e424.txt for arms using the old prompt")
    parser.add_argument("--rbac-role", default=None, help="document role without VietStyle access; R cases skipped if unset")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--only", default=None, help="comma-separated case ids, for a smoke run")
    parser.add_argument("--resume", action="store_true", help="continue an interrupted output file")
    args = parser.parse_args()
    arm = ARMS[args.arm]
    if arm.get("prompt") == "old" and not args.old_prompt:
        parser.error("--old-prompt is required for this arm")
    if args.output.exists() and not args.resume:
        parser.error("Output exists; choose a new path or pass --resume")
    raw = args.cases.read_bytes()
    dataset = json.loads(raw)
    report = json.loads(args.output.read_text()) if args.resume else {
        "dataset_id": dataset["dataset_id"], "dataset_status": dataset["status"],
        "dataset_sha256": hashlib.sha256(raw).hexdigest(), "arm": args.arm,
        "configuration": {**arm, **({"method": args.method} if args.arm == "A" else {}),
                          "groq_model_env": os.getenv("GROQ_MODEL"), "rbac_role": args.rbac_role,
                          "old_prompt_sha256": hashlib.sha256(Path(args.old_prompt).read_bytes()).hexdigest()
                          if arm.get("prompt") == "old" else None},
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "results": []}
    if report["dataset_sha256"] != hashlib.sha256(raw).hexdigest() or report["arm"] != args.arm:
        parser.error("Resumed output belongs to another dataset or arm")
    done = {row["id"] for row in report["results"]}
    only = set(args.only.split(",")) if args.only else None
    runner = Http(args) if arm.get("kind") == "http" else InProcess(arm, args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for case in dataset["cases"]:
            if case["id"] in done or (only and case["id"] not in only):
                continue
            row = {"id": case["id"], "type": case["type"]}
            if case.get("history") and arm.get("kind") != "http":
                row["skipped"] = "multi_turn_needs_router"
            elif case.get("role") and (arm.get("kind") == "http" or not args.rbac_role):
                row["skipped"] = "rbac_role_not_set" if arm.get("kind") != "http" else "rbac_not_run_as_admin"
            else:
                roles = [args.rbac_role] if case.get("role") else ["admin"]
                started = time.perf_counter()
                try:
                    row.update(runner.run(case, roles))
                except SystemExit:
                    raise
                except Exception as error:  # one failed case must not lose the arm; scored as an error
                    if type(error).__name__ == "RateLimitError":
                        raise SystemExit("Groq rate limit on every key; stopped. Rerun with --resume later.")
                    row.update(error_type=type(error).__name__, error=str(error)[:500])
                row["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
            report["results"].append(row)
            save(args.output, report)
            print(row["id"], row.get("skipped") or row.get("error_type") or f"{row['elapsed_ms']:.0f} ms", flush=True)
    finally:
        runner.close()
    print(f"saved {len(report['results'])} rows to {args.output}")


if __name__ == "__main__":
    sys.exit(main())
