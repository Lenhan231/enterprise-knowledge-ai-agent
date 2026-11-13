"""Compare the production Modal LoRA and Gemini extractors on shared Kaggle OCR."""

from __future__ import annotations

import json
import os
import shlex
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT.parent / ".env"
OCR_RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "artifacts/invoice-pilot-50-new-vietocr/ocr_results.json"
OUTPUT = ROOT / "artifacts/invoice-benchmark-rerun-2026-11-12/api_results.json"


def load_env() -> dict[str, str]:
    values = {}
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        parts = shlex.split(value, comments=False)
        values[key.strip()] = parts[0] if parts else ""
    return values


def norm(value, numeric=False):
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", " ".join(str(value).split())).casefold()
    return "".join(char for char in text if char.isdigit()) if numeric else text


def norm_date(value):
    text = norm(value)
    return text.removeprefix("ngày ").removeprefix("ngay ")


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def word_edit_distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, left_word in enumerate(left, 1):
        current = [i]
        for j, right_word in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (left_word != right_word),
            ))
        previous = current
    return previous[-1]


def score(provider_rows: list[dict]) -> tuple[list[dict], dict]:
    headers = ("invoice_no", "date", "seller", "buyer", "subtotal", "tax_amount", "total_amount")
    item_fields = ("description", "quantity", "unit", "unit_price", "amount")
    numeric = {"subtotal", "tax_amount", "total_amount", "quantity", "unit_price", "amount"}
    rows = []
    for result in provider_rows:
        expected = result["expected"]
        predicted = result.get("fields") or {}
        expected_items = expected.get("items") or []
        predicted_items = predicted.get("items") or []
        row = {
            "file": result["file"],
            "quality": result["quality"],
            "status": result["status"],
            "schema_valid": result.get("schema_valid", False),
            "parse_error": result.get("parse_error"),
            "field_conflict_count": len(result.get("field_conflicts") or {}),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "item_count_exact": len(expected_items) == len(predicted_items),
        }
        for field in headers:
            normalize = norm_date if field == "date" else lambda value: norm(value, field in numeric)
            row[field + "_exact"] = normalize(expected.get(field)) == normalize(predicted.get(field))
        row_exact = 0
        for index, expected_item in enumerate(expected_items):
            predicted_item = predicted_items[index] if index < len(predicted_items) else {}
            row_exact += int(all(
                norm(expected_item.get(field), field in numeric) == norm(predicted_item.get(field), field in numeric)
                for field in item_fields
            ))
        row["item_rows_exact_rate"] = row_exact / len(expected_items) if expected_items else float(not predicted_items)
        for field in item_fields:
            row["item_" + field + "_accuracy"] = (
                sum(
                    norm(item.get(field), field in numeric) == norm((predicted_items[i] if i < len(predicted_items) else {}).get(field), field in numeric)
                    for i, item in enumerate(expected_items)
                ) / len(expected_items) if expected_items else 1.0
            )
        row["whole_invoice_exact"] = (
            row["schema_valid"] and not row["parse_error"] and not row["field_conflict_count"]
            and all(row[field + "_exact"] for field in headers)
            and row["item_count_exact"] and row_exact == len(expected_items)
        )
        rows.append(row)

    def mean(values):
        values = list(values)
        return sum(values) / len(values) if values else 0.0

    successes = [row for row in provider_rows if row["status"] == "success"]
    latency = sorted(row["elapsed_seconds"] for row in successes)
    description_char_errors = description_chars = description_word_errors = description_words = 0
    for result in provider_rows:
        predicted = (result.get("fields") or {}).get("items") or []
        for index, expected_item in enumerate(result["expected"].get("items") or []):
            expected_text = norm(expected_item.get("description"))
            predicted_text = norm((predicted[index] if index < len(predicted) else {}).get("description"))
            description_char_errors += edit_distance(expected_text, predicted_text)
            description_chars += len(expected_text)
            expected_tokens, predicted_tokens = expected_text.split(), predicted_text.split()
            description_word_errors += word_edit_distance(expected_tokens, predicted_tokens)
            description_words += len(expected_tokens)
    header_rates = {field: mean(row[field + "_exact"] for row in rows) for field in headers}
    item_rates = {field: mean(row["item_" + field + "_accuracy"] for row in rows) for field in item_fields}
    model_latency = [row["metrics"].get("inference_seconds", 0) for row in successes]
    summary = {
        "sample_count": len(provider_rows),
        "success_count": len(successes),
        "coverage": len(successes) / len(provider_rows) if provider_rows else 0,
        "schema_valid_rate": mean(row["schema_valid"] for row in rows),
        "parse_error_count": sum(bool(row["parse_error"]) for row in rows),
        "field_conflict_count": sum(row["field_conflict_count"] for row in rows),
        "header_exact_match_rates": header_rates,
        "item_count_exact_rate": mean(row["item_count_exact"] for row in rows),
        "item_row_exact_accuracy": mean(row["item_rows_exact_rate"] for row in rows),
        "item_field_accuracy": item_rates,
        "description_cer": description_char_errors / description_chars if description_chars else None,
        "description_wer": description_word_errors / description_words if description_words else None,
        "whole_invoice_exact_rate": mean(row["whole_invoice_exact"] for row in rows),
        "end_to_end_latency_seconds": {
            "mean": mean(row["elapsed_seconds"] for row in successes),
            "median": (latency[len(latency)//2] if len(latency) % 2 else (latency[len(latency)//2-1] + latency[len(latency)//2]) / 2) if latency else None,
            "p95": latency[min(len(latency)-1, int(0.95 * (len(latency)-1)))] if latency else None,
            "model_inference_seconds_mean": mean(model_latency),
        },
        "usage": {
            "prompt_tokens": sum(int(row["metrics"].get("prompt_tokens") or 0) for row in successes),
            "generated_tokens": sum(int(row["metrics"].get("generated_tokens") or 0) for row in successes),
            "requests": sum(int(row["metrics"].get("request_count") or 0) for row in successes),
        },
        "by_quality": {},
    }
    for quality in sorted({row["quality"] for row in rows}):
        group = [row for row in rows if row["quality"] == quality]
        summary["by_quality"][quality] = {
            "sample_count": len(group),
            "coverage": mean(row["status"] == "success" for row in group),
            "whole_invoice_exact_rate": mean(row["whole_invoice_exact"] for row in group),
            "item_field_accuracy": {field: mean(row["item_" + field + "_accuracy"] for row in group) for field in item_fields},
        }
    return rows, summary


def main() -> None:
    from document_processing.invoice_text_processor import InvoiceTextProcessor
    import document_processing.invoice_text_processor as invoice_module

    env = load_env()
    # Let a run select an alternate Gemini model without changing the shared .env.
    for key in ("DOCUMENT_PROCESSING_GEMINI_INVOICE_MODEL",):
        if os.environ.get(key):
            env[key] = os.environ[key]
    for name in (
        "GEMINI_API", "HF_INVOICE_LLM_TOKEN", "DOCUMENT_PROCESSING_INVOICE_MODAL_URL",
    ):
        if not env.get(name):
            raise SystemExit(f"Missing configured environment key: {name}")
    os.environ.update(env)
    with OCR_RESULTS.open(encoding="utf-8") as stream:
        ocr_data = json.load(stream)
    samples = ocr_data["samples"]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result_data = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {
        "metadata": {
            "sample_count": len(samples),
            "ocr_repo": ocr_data.get("metadata", {}).get("ocr_repo"),
            "ocr_revision": ocr_data.get("metadata", {}).get("ocr_revision"),
            "ocr_device": ocr_data.get("metadata", {}).get("device"),
            "modal_model": env.get("DOCUMENT_PROCESSING_INVOICE_MODEL", "Qwen/Qwen3-0.6B"),
            "modal_adapter": env.get("DOCUMENT_PROCESSING_INVOICE_ADAPTER", "lenhanm1/qwen3-0.6b-invoice-lora-900"),
            "gemini_model": env.get("DOCUMENT_PROCESSING_GEMINI_INVOICE_MODEL", "gemini-3.1-flash-lite"),
            "prompt_source": "current production InvoiceTextProcessor._extraction_jobs",
            "shared_ocr_inputs": True,
            "date_score_normalization": "ignore a leading Vietnamese 'Ngày' label",
        },
        "providers": {"modal": {}, "gemini": {}},
    }

    result_data.setdefault("metadata", {})["gemini_model"] = env.get(
        "DOCUMENT_PROCESSING_GEMINI_INVOICE_MODEL", "gemini-3.1-flash-lite",
    )
    original_urlopen = invoice_module.urlopen
    last_gemini_request = [0.0]

    def quota_paced_urlopen(request, *args, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "generativelanguage.googleapis.com" in url:
            delay = 4.1 - (time.monotonic() - last_gemini_request[0])
            if delay > 0:
                time.sleep(delay)
            last_gemini_request[0] = time.monotonic()
        return original_urlopen(request, *args, **kwargs)

    invoice_module.urlopen = quota_paced_urlopen
    try:
        for provider in ("modal", "gemini"):
            processor = InvoiceTextProcessor({"invoice_provider": provider})
            provider_rows = result_data["providers"][provider]
            for index, (filename, sample) in enumerate(samples.items(), 1):
                if filename in provider_rows and provider_rows[filename].get("status") == "success":
                    continue
                row = {
                    "file": filename,
                    "invoice_no": sample["invoice_no"],
                    "quality": sample["quality"],
                    "expected": sample["expected"],
                    "status": "failed",
                }
                if sample.get("status") != "success":
                    row["error"] = "OCR failed: " + str(sample.get("error") or sample.get("status"))
                    provider_rows[filename] = row
                    continue
                started = time.perf_counter()
                try:
                    extraction = processor.process(sample.get("elements") or [], sample.get("tables") or [])
                    row.update({
                        "status": "success" if extraction.get("status") == "review_required" else extraction.get("status", "failed"),
                        "schema_valid": extraction.get("schema_version") == "invoice.v1" and extraction.get("fields") is not None,
                        "fields": extraction.get("fields") or {},
                        "model": extraction.get("model"),
                        "revision": extraction.get("revision"),
                        "adapter": extraction.get("adapter"),
                        "adapter_revision": extraction.get("adapter_revision"),
                        "metrics": extraction.get("metrics") or {},
                        "parse_error": extraction.get("parse_error"),
                        "field_conflicts": extraction.get("field_conflicts") or {},
                        "raw_response": extraction.get("raw_response"),
                        "elapsed_seconds": round(time.perf_counter() - started, 2),
                    })
                except Exception as error:
                    row.update({"error": f"{type(error).__name__}: {error}", "elapsed_seconds": round(time.perf_counter() - started, 2)})
                provider_rows[filename] = row
                temp = OUTPUT.with_suffix(".tmp")
                temp.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")
                temp.replace(OUTPUT)
                print(f"{provider.upper()} {index}/{len(samples)} {filename} {row['elapsed_seconds']:.1f}s status={row['status']} parse_error={row.get('parse_error')}", flush=True)
            scored_rows, summary = score(list(provider_rows.values()))
            result_data.setdefault("scores", {})[provider] = scored_rows
            result_data.setdefault("metrics", {})[provider] = summary
            temp = OUTPUT.with_suffix(".tmp")
            temp.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(OUTPUT)
            print(f"SUMMARY {provider}: {json.dumps(summary, ensure_ascii=False)}", flush=True)
    finally:
        invoice_module.urlopen = original_urlopen
    print("Saved", OUTPUT)


if __name__ == "__main__":
    main()
