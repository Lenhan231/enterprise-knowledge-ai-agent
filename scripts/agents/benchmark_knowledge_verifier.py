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

from pydantic import ValidationError
from dotenv import load_dotenv
from core.llm.groq_provider import GroqProvider
from core.rag.claim_verification import AnswerReview, validate_review, verify_answer
from core.prompts.knowledge_verification import CLAIM_VERIFICATION_PROMPT


class AuditRecorder(GroqProvider):
    def generate(self, prompt, **kwargs):
        self.audit_raw = None
        raw = super().generate(prompt, **kwargs)
        self.audit_raw = raw
        return raw


def validation_error(raw, answer, contexts):
    if raw is None:
        return None
    try:
        # Replay the existing parser/checks without another LLM call or changing its verdict.
        fenced = re.fullmatch(r"\s*```(?:json)?\s*\n(.*?)\n```\s*", raw, flags=re.DOTALL | re.IGNORECASE)
        review = AnswerReview.model_validate_json(fenced.group(1) if fenced else raw)
        validate_review(answer, contexts, review)
    except ValidationError:
        return "invalid_review_schema"
    except ValueError as error:
        return str(error)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "data/evaluation/knowledge_claim_verification_cases.json")
    parser.add_argument("--output", type=Path, required=True, help="New JSONL file; flushed after each case")
    parser.add_argument("--case-ids", nargs="+", help="Run only these fixed case IDs")
    parser.add_argument("--limit", type=int, default=0, help="0 runs all diagnostic cases")
    parser.add_argument("--pause", type=float, default=15)
    parser.add_argument("--api-key-env", help="Use only this GROQ_API_KEY[_N] variable for this process")
    args = parser.parse_args()
    if args.limit < 0 or not 0 <= args.pause <= 60:
        parser.error("limit must be nonnegative and pause must be 0..60")
    if args.output.exists():
        parser.error("Choose a new output file; previous results are never overwritten")
    load_dotenv(ROOT / ".env")
    if args.api_key_env and (not re.fullmatch(r"GROQ_API_KEY(?:_\d+)?", args.api_key_env)
                             or not os.getenv(args.api_key_env, "").strip()):
        parser.error("Selected Groq key variable is invalid or empty")
    dataset = json.loads(args.cases.read_text())
    if args.case_ids and not set(args.case_ids).issubset(c["id"] for c in dataset["cases"]):
        parser.error("Unknown case ID; no requests were sent")
    selected = [c for c in dataset["cases"] if not args.case_ids or c["id"] in args.case_ids]
    cases = selected[:args.limit or None]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results = []
    llm = AuditRecorder(api_keys=[os.environ[args.api_key_env]]) if args.api_key_env else AuditRecorder()
    try:
        with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
            output.write(json.dumps({"dataset": dataset["dataset_id"], "model": llm.model_name,
                                     "limitations": dataset["limitations"], "api_key_env": args.api_key_env or "pool",
                                     "case_ids": [c["id"] for c in cases],
                                     "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
                                     "prompt_sha256": hashlib.sha256(CLAIM_VERIFICATION_PROMPT.encode()).hexdigest(),
                                     "verifier_timeout_seconds": 15, "max_output_tokens": 3072}) + "\n")
            output.flush()
            for case in cases:
                ids = set(re.findall(r"\[(S\d+)\]", case["answer"]))
                contexts = [c for c in dataset["contexts"][case["context"]] if c["source_id"] in ids]
                llm.last_usage = None
                llm.audit_raw = None
                started = time.perf_counter()
                outcome = verify_answer(llm, case["question"], case["answer"], contexts)
                row = {"id": case["id"], "expected": case["expected"], **outcome.model_dump(),
                       "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                       "usage": llm.last_usage, "audit_raw": llm.audit_raw,
                       "validation_error": validation_error(llm.audit_raw, case["answer"], contexts)}
                if outcome.reason == "RateLimitError":
                    row["rate_limit"] = rate_limit_details(llm)
                results.append(row)
                output.write(json.dumps(row) + "\n")
                output.flush()
                print(json.dumps({k: v for k, v in row.items() if k != "audit_raw"}), flush=True)
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


def rate_limit_details(provider):
    error = provider._last_rate_error
    body = getattr(error, "body", {})
    if isinstance(body, dict):
        body = body.get("error", body)
    message = str(body.get("message", "")) if isinstance(body, dict) else ""
    kind = re.search(r"\b(TPM|TPD|RPM|RPD|ITPM|OTPM)\b", message)
    headers = getattr(getattr(error, "response", None), "headers", {})
    # Only quota fields; never persist raw provider errors, keys or organization IDs.
    values = {name.lower(): value.rstrip(",.") for name, value in
              re.findall(r"\b(Limit|Used|Requested)\s*:?\s*([\d,.]+)", message)}
    return {"kind": kind.group(1) if kind else "unknown",
            "retry_after": headers.get("retry-after"), **values}


if __name__ == "__main__":
    raise SystemExit(main())
