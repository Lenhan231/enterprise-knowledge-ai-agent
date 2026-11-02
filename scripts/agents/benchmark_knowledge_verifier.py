"""Live verifier diagnostic on fixed drafts/sources; never a retrieval benchmark."""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
from core.llm.groq_provider import GroqProvider
from core.rag.claim_verification import verify_answer
from core.prompts.knowledge_verification import CLAIM_VERIFICATION_PROMPT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "data/evaluation/knowledge_claim_verification_cases.json")
    parser.add_argument("--output", type=Path, required=True, help="New JSONL file; flushed after each case")
    parser.add_argument("--limit", type=int, default=0, help="0 runs all diagnostic cases")
    parser.add_argument("--pause", type=float, default=15)
    args = parser.parse_args()
    if args.limit < 0 or not 0 <= args.pause <= 60:
        parser.error("limit must be nonnegative and pause must be 0..60")
    if args.output.exists():
        parser.error("Choose a new output file; previous results are never overwritten")
    load_dotenv(ROOT / ".env")
    dataset = json.loads(args.cases.read_text())
    cases = dataset["cases"][:args.limit or None]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results = []
    llm = GroqProvider()
    try:
        with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
            output.write(json.dumps({"dataset": dataset["dataset_id"], "model": llm.model_name,
                                     "limitations": dataset["limitations"],
                                     "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
                                     "prompt_sha256": hashlib.sha256(CLAIM_VERIFICATION_PROMPT.encode()).hexdigest(),
                                     "verifier_timeout_seconds": 15, "max_output_tokens": 3072}) + "\n")
            output.flush()
            for case in cases:
                ids = set(re.findall(r"\[(S\d+)\]", case["answer"]))
                contexts = [c for c in dataset["contexts"][case["context"]] if c["source_id"] in ids]
                llm.last_usage = None
                started = time.perf_counter()
                outcome = verify_answer(llm, case["question"], case["answer"], contexts)
                row = {"id": case["id"], "expected": case["expected"], **outcome.model_dump(),
                       "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                       "usage": llm.last_usage}
                results.append(row)
                output.write(json.dumps(row) + "\n")
                output.flush()
                print(json.dumps(row), flush=True)
                if outcome.reason in {"RateLimitError", "AuthenticationError", "PermissionDeniedError"}:
                    break
                time.sleep(args.pause)
            summary = {"completed": len(results), "planned": len(cases),
                       "expected_supported": sum(r["expected"] == "supported" for r in results),
                       "expected_rejected": sum(r["expected"] == "rejected" for r in results),
                       "supported_kept": sum(r["expected"] == "supported" and r["status"] == "supported" for r in results),
                       "unsupported_passed": sum(r["expected"] == "rejected" and r["status"] == "supported" for r in results),
                       "unsupported_rejected": sum(r["expected"] == "rejected" and r["status"] == "rejected" for r in results),
                       "unavailable": sum(r["status"] == "unavailable" for r in results)}
            output.write(json.dumps({"summary": summary}) + "\n")
            print(json.dumps({"summary": summary}), flush=True)
    finally:
        llm.close()
    return int(len(results) != len(cases) or any(r["status"] != r["expected"] for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
