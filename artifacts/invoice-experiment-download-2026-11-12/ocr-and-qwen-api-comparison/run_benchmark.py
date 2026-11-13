"""Run the 50-invoice holdout through the deployed VietOCR and both extractors."""

from __future__ import annotations

import json
import os
import csv
import time
from pathlib import Path

from document_processing.document_processor import DocumentProcessor
from document_processing.invoice_text_processor import InvoiceTextProcessor


DATA = Path("/tmp/invoice-pilot-50/data")
GROUND_TRUTH = Path("/tmp/invoice-pilot-50/ground_truth.json")
MANIFEST = Path("/tmp/invoice-pilot-50/manifest.csv")
OUTPUT = Path("/tmp/invoice-pilot-50-new-vietocr.json")
PROVIDERS = ("modal", "gemini")


def save(payload: dict) -> None:
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    temporary.replace(OUTPUT)


def main() -> None:
    ground_truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    with MANIFEST.open(encoding="utf-8", newline="") as stream:
        manifest = list(csv.DictReader(stream))
    if len(ground_truth) != 50 or len(manifest) != 50:
        raise RuntimeError(f"Expected 50 labeled invoices; found {len(ground_truth)} labels and {len(manifest)} manifest rows")
    labels_by_invoice_no = {row["invoice_no"]: row for row in ground_truth}
    reference_by_file = {
        row["file"]: {**labels_by_invoice_no[row["invoice_no"]], "quality": row["quality"]}
        for row in manifest
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        results = json.loads(OUTPUT.read_text(encoding="utf-8"))
    else:
        results = {
            "metadata": {
                "sample_count": len(manifest),
                "ocr_repo": os.getenv("DOCUMENT_PROCESSING_VIETOCR_REPO_ID", ""),
                "ocr_revision": os.getenv("DOCUMENT_PROCESSING_VIETOCR_REVISION", ""),
                "ocr_config": os.getenv("DOCUMENT_PROCESSING_VIETOCR_CONFIG", "vgg_seq2seq"),
                "providers": list(PROVIDERS),
            },
            "samples": {},
        }

    parser = DocumentProcessor({
        "intent": "document",
        "parser_engine": "docling",
        "docling_device": "cpu",
        "docling_ocr": True,
        "docling_ocr_engine": "vietocr",
        "docling_ocr_language": "vie+eng",
        "docling_table_structure": True,
        "docling_num_threads": 4,
    })
    extractors = {provider: InvoiceTextProcessor({"invoice_provider": provider}) for provider in PROVIDERS}

    sample_limit = int(os.getenv("INVOICE_BENCHMARK_LIMIT", "50"))
    selected = list(reference_by_file.items())[:sample_limit]
    for index, (filename, reference) in enumerate(selected, start=1):
        sample = results["samples"].setdefault(filename, {
            "file": filename,
            "expected": reference,
            "ocr": None,
            "providers": {},
        })
        if sample["ocr"] is None:
            started = time.perf_counter()
            try:
                parsed = parser.process(filename, (DATA / filename).read_bytes(), {"source_type": "benchmark"})
                sample["ocr"] = {
                    "elements": parsed.get("elements", []),
                    "tables": parsed.get("tables", []),
                    "pipeline_id": (parsed.get("metadata") or {}).get("pipeline_id"),
                    "elapsed_seconds": round(time.perf_counter() - started, 2),
                    "error": None,
                }
            except Exception as error:
                sample["ocr"] = {
                    "elements": [], "tables": [],
                    "elapsed_seconds": round(time.perf_counter() - started, 2),
                    "error": f"{type(error).__name__}: {error}",
                }
            save(results)
            print(
                f"OCR {index}/50 {filename}: "
                f"{sample['ocr']['elapsed_seconds']:.1f}s, "
                f"{len(sample['ocr']['elements'])} elements, "
                f"{len(sample['ocr']['tables'])} tables, "
                f"error={bool(sample['ocr']['error'])}",
                flush=True,
            )

        if sample["ocr"]["error"]:
            continue
        for provider in PROVIDERS:
            if provider in sample["providers"] and sample["providers"][provider].get("status") == "success":
                continue
            started = time.perf_counter()
            try:
                extraction = extractors[provider].process(sample["ocr"]["elements"], sample["ocr"]["tables"])
                sample["providers"][provider] = {
                    "status": "success",
                    "model": extraction.get("model"),
                    "revision": extraction.get("revision"),
                    "adapter": extraction.get("adapter"),
                    "adapter_revision": extraction.get("adapter_revision"),
                    "fields": extraction.get("fields"),
                    "metrics": extraction.get("metrics", {}),
                    "parse_error": extraction.get("parse_error"),
                    "field_conflicts": extraction.get("field_conflicts", {}),
                    "raw_response": extraction.get("raw_response", ""),
                    "elapsed_seconds": round(time.perf_counter() - started, 2),
                }
            except Exception as error:
                sample["providers"][provider] = {
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                    "elapsed_seconds": round(time.perf_counter() - started, 2),
                }
            save(results)
            outcome = sample["providers"][provider]
            print(
                f"{provider.upper()} {index}/50 {filename}: "
                f"{outcome['elapsed_seconds']:.1f}s, status={outcome['status']}, "
                f"error={outcome.get('error') or outcome.get('parse_error')}",
                flush=True,
            )

    successes = {
        provider: sum(
            sample.get("providers", {}).get(provider, {}).get("status") == "success"
            for sample in results["samples"].values()
        )
        for provider in PROVIDERS
    }
    results["metadata"]["completed_count"] = len(results["samples"])
    results["metadata"]["provider_success_counts"] = successes
    save(results)
    print("BENCHMARK_COMPLETE", json.dumps(results["metadata"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
