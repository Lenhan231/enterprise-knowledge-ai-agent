"""Benchmark the candidate Groq extractor against the same cached Kaggle OCR."""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dotenv import dotenv_values
import httpx
import openai

parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, default=50)
parser.add_argument("--output", type=Path, help="Use a new JSON path for a fresh API run; existing paths resume")
parser.add_argument("--source-commit", default="720b265", help="Pinned deployed source; override to evaluate a different revision")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
folder = Path(__file__).resolve().parent
commit = subprocess.check_output(["git", "rev-parse", args.source_commit], text=True).strip()
source = subprocess.check_output(["git", "show", f"{commit}:src/document_processing/invoice_text_processor.py"])
os.environ["GROQ_API_KEY"] = dotenv_values(root.parent / ".env")["GROQ_API_KEY"]
ocr_bytes = (root / "artifacts/invoice-pilot-50-new-vietocr/ocr_results.json").read_bytes()
ocr_data = json.loads(ocr_bytes)
scoring_path = root / "artifacts/invoice-pilot-50-new-vietocr/run_model_benchmark.py"
spec = importlib.util.spec_from_file_location("scoring", scoring_path)
scoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoring)

last_request = 0.0
remaining_tokens = None
reset_at = 0.0
def pace_request(request):
    global last_request
    delay = 2.1 - (time.monotonic() - last_request)
    estimated = len(request.content) / 3 + 1600
    if remaining_tokens is not None and remaining_tokens < estimated:
        delay = max(delay, reset_at - time.monotonic() + 1)
    if delay > 0:
        time.sleep(delay)
    last_request = time.monotonic()

def record_limits(response):
    global remaining_tokens, reset_at
    header = response.headers.get("x-ratelimit-remaining-tokens")
    if header is not None:
        remaining_tokens = int(header)
        units = {"ms": 0.001, "h": 3600, "m": 60, "s": 1}
        reset = response.headers.get("x-ratelimit-reset-tokens", "")
        seconds = sum(float(n) * units[unit] for n, unit in re.findall(r"([\d.]+)(ms|h|m|s)", reset))
        reset_at = time.monotonic() + seconds
    if response.status_code >= 400:
        print("API HTTP", response.status_code, flush=True)

BaseClient = openai.OpenAI
class PacedClient(BaseClient):
    def __init__(self, **kwargs):
        kwargs["http_client"] = httpx.Client(event_hooks={"request": [pace_request], "response": [record_limits]})
        super().__init__(**kwargs)
openai.OpenAI = PacedClient
path = args.output or folder / "results.json"
path.parent.mkdir(parents=True, exist_ok=True)
data = json.loads(path.read_text()) if path.exists() else {
    "metadata": {
        "source_commit": commit,
        "model_id": "openai/gpt-oss-120b",
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "ocr_sha256": hashlib.sha256(ocr_bytes).hexdigest(),
        "ocr_revision": ocr_data["metadata"]["ocr_revision"],
        "sample_count": 50,
        "runner": "local API calls over cached Kaggle OCR",
        "prompt": "complete_invoice_evidence_v2",
        "reasoning_effort": "medium",
        "response_format": "strict_json_schema",
        "latency_note": "Excludes cached OCR; includes rate-limit pacing and retries.",
    },
    "results": {},
}
assert data["metadata"]["source_sha256"] == hashlib.sha256(source).hexdigest()
with tempfile.TemporaryDirectory(prefix="groq-candidate-") as temp:
    package = Path(temp) / "document_processing"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "invoice_text_processor.py").write_bytes(source)
    sys.path.insert(0, temp)
    from document_processing.invoice_text_processor import InvoiceTextProcessor, InvoiceFields
    processor = InvoiceTextProcessor({"invoice_provider": "groq", "groq_invoice_model": "openai/gpt-oss-120b"})
    for index, (filename, sample) in enumerate(ocr_data["samples"].items(), 1):
        if index > args.limit:
            break
        if filename in data["results"]:
            continue
        row = {"file": filename, "quality": sample["quality"], "expected": sample["expected"], "status": "failed"}
        started = time.perf_counter()
        try:
            result = processor.process(sample.get("elements") or [], sample.get("tables") or [])
            InvoiceFields.model_validate(result["fields"])
            row.update(status="success", schema_valid=True, fields=result["fields"], model=result["model"],
                       metrics=result["metrics"], parse_error=result["parse_error"],
                       field_conflicts=result["field_conflicts"], raw_response=result["raw_response"])
        except Exception as error:
            row.update(error=f"{type(error).__name__}: {error}", schema_valid=False)
        row["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        data["results"][filename] = row
        scores, metrics = scoring.score(list(data["results"].values()))
        data.update(scores=scores, metrics=metrics)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        temporary.replace(path)
        print(f'{index}/50 {filename} {row["status"]} {row["elapsed_seconds"]}s whole_exact={metrics["whole_invoice_exact_rate"]:.1%} error={row.get("error") or row.get("parse_error")}', flush=True)
        if "HTTP 429" in row.get("error", ""):
            raise SystemExit("Groq quota reached; stop here rather than consuming requests for remaining samples")
        if index <= 3 and row["status"] != "success":
            raise SystemExit("Initial API check failed")
print(json.dumps(data["metrics"], ensure_ascii=False), flush=True)
