"""Rerun Groq and Gemini invoice extraction on the shared 50-invoice OCR cache."""

from __future__ import annotations

import json
import hashlib
import os
import shlex
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = ROOT / "artifacts/invoice-experiment-download-2026-11-12"
RUN_DIR = EXPERIMENT / "rerun-2026-11-12"
OCR_PATH = RUN_DIR / "inputs/holdout-ocr.json"
RESULTS_DIR = RUN_DIR / "results"
SOURCE_COMMIT = "535932f912949f860ef735df690c3bc60714f8cf"


def load_provider_secrets() -> dict[str, str]:
    env_path = ROOT / ".env"
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.removeprefix("export ").split("=", 1)
        key = key.strip()
        if key in {"GROQ_API_KEY", "GEMINI_API"}:
            parsed = shlex.split(raw_value, comments=False)
            values[key] = parsed[0] if parsed else ""
    missing_groq = not (os.environ.get("GROQ_API_KEY") or values.get("GROQ_API_KEY"))
    if missing_groq:
        raise RuntimeError("Missing GROQ_API_KEY in process environment or repo .env")
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return {key: os.environ[key] for key in ("GROQ_API_KEY", "GEMINI_API") if os.environ.get(key)}


def install_request_pacing() -> None:
    import httpx
    import openai
    import document_processing.invoice_text_processor as invoice_module

    groq_last_request = [0.0]

    def pace_groq(request: httpx.Request) -> None:
        if "api.groq.com" not in str(request.url):
            return
        delay = 2.1 - (time.monotonic() - groq_last_request[0])
        if delay > 0:
            time.sleep(delay)
        groq_last_request[0] = time.monotonic()

    base_openai = openai.OpenAI

    class PacedOpenAI(base_openai):
        def __init__(self, *args, **kwargs):
            kwargs["http_client"] = httpx.Client(event_hooks={"request": [pace_groq]})
            # Keep transient provider 429s from becoming missing samples in this one-off rerun.
            kwargs["max_retries"] = 4
            super().__init__(*args, **kwargs)

    openai.OpenAI = PacedOpenAI

    original_urlopen = invoice_module.urlopen
    gemini_last_request = [0.0]

    def pace_gemini(request, *args, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "generativelanguage.googleapis.com" in url:
            delay = 4.1 - (time.monotonic() - gemini_last_request[0])
            if delay > 0:
                time.sleep(delay)
            gemini_last_request[0] = time.monotonic()
        return original_urlopen(request, *args, **kwargs)

    invoice_module.urlopen = pace_gemini


def save_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    secrets = load_provider_secrets()
    sys.path.insert(0, str(ROOT / "src"))
    from document_processing.invoice_text_processor import InvoiceTextProcessor

    cache_records = json.loads(OCR_PATH.read_text(encoding="utf-8"))
    samples = {record["file"]: record for record in cache_records}
    if len(samples) != 50 or any(sample.get("ocr_status") != "success" for sample in samples.values()):
        raise ValueError(f"Expected 50 successful cached OCR records; found {len(samples)}")

    qwen_rows = json.loads((RESULTS_DIR / "qwen3-0.6b-base-results.json").read_text(encoding="utf-8"))
    qwen_expected = {row["file"]: row["expected"] for row in qwen_rows}
    if set(samples) != set(qwen_expected) or any(samples[name]["expected"] != expected for name, expected in qwen_expected.items()):
        raise ValueError("Local OCR cache does not match the Qwen rerun's held-out files and labels")

    install_request_pacing()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for provider, config, secret_name in (
        ("gemini", {"invoice_provider": "gemini", "gemini_invoice_model": "gemini-3.1-flash-lite"}, "GEMINI_API"),
        ("groq", {"invoice_provider": "groq", "groq_invoice_model": "openai/gpt-oss-120b"}, "GROQ_API_KEY"),
    ):
        if secret_name not in secrets:
            print(f"Skipping {provider.upper()}: {secret_name} is not configured in the local .env or process environment.")
            continue
        path = RESULTS_DIR / f"{provider}-results.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "metadata": {
                "provider": provider,
                "model": config.get("groq_invoice_model") or config.get("gemini_invoice_model"),
                "sample_count": len(samples),
                "shared_ocr_cache": True,
                "ocr_cache_dataset": "ltrngnhn/invoice-50-holdout-ocr-cache",
                "ocr_cache_sha256": hashlib.sha256(OCR_PATH.read_bytes()).hexdigest(),
                "ocr_model": next(iter(samples.values())).get("ocr_model"),
                "ocr_config": next(iter(samples.values())).get("ocr_config"),
                "qwen_rerun_source_commit": SOURCE_COMMIT,
                "ocr_pipeline": next(iter(samples.values())).get("ocr_pipeline"),
                "prompt_source": "InvoiceTextProcessor from main commit " + SOURCE_COMMIT,
            },
            "results": [],
        }
        # Collapse earlier failed attempts so each held-out invoice has one final row.
        data["results"] = list({row["file"]: row for row in data["results"]}.values())
        save_json(path, data)
        completed = {row["file"] for row in data["results"] if row.get("status") == "success"}
        processor = InvoiceTextProcessor(config)
        for index, (filename, sample) in enumerate(samples.items(), 1):
            if filename in completed:
                continue
            row = {
                "file": filename,
                "quality": sample["quality"],
                "expected": sample["expected"],
                "status": "failed",
            }
            started = time.perf_counter()
            try:
                extraction = processor.process(sample.get("elements") or [], sample.get("tables") or [])
                row.update({
                    "status": "success" if extraction.get("status") == "review_required" else extraction.get("status", "failed"),
                    "schema_valid": extraction.get("schema_version") == "invoice.v1" and extraction.get("fields") is not None,
                    "fields": extraction.get("fields") or {},
                    "model": extraction.get("model"),
                    "revision": extraction.get("revision"),
                    "metrics": extraction.get("metrics") or {},
                    "parse_error": extraction.get("parse_error"),
                    "field_conflicts": extraction.get("field_conflicts") or {},
                    "raw_response": extraction.get("raw_response"),
                })
            except Exception as error:
                detail = f"{type(error).__name__}: {error}"
                for secret in secrets.values():
                    detail = detail.replace(secret, "[REDACTED]")
                row["error"] = detail
            row["elapsed_seconds"] = round(time.perf_counter() - started, 2)
            existing = next((i for i, old in enumerate(data["results"]) if old["file"] == filename), None)
            if existing is None:
                data["results"].append(row)
            else:
                data["results"][existing] = row
            save_json(path, data)
            print(f"{provider.upper()} {index}/{len(samples)} {filename} {row['elapsed_seconds']}s {row['status']}", flush=True)


if __name__ == "__main__":
    main()
