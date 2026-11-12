"""Build one compact comparison from the per-invoice benchmark result files."""

from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parent
ROOT = RUN_DIR.parents[2]
RESULTS = RUN_DIR / "results"
EXPERIMENT = ROOT / "artifacts/invoice-experiment-download-2026-11-12"
QWEN_METRICS = json.loads((RESULTS / "qwen-metrics.json").read_text(encoding="utf-8"))

scorer_path = EXPERIMENT / "reports/score_saved_results.py"
spec = importlib.util.spec_from_file_location("invoice_result_scorer", scorer_path)
scorer = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(scorer)

models = {
    name: QWEN_METRICS[name]
    for name in ("qwen3-0.6b-base", "qwen3-0.6b-lora", "qwen3-1.7b-base")
}
provider_status = {}
for provider in ("groq", "gemini"):
    path = RESULTS / f"{provider}-results.json"
    if not path.exists():
        provider_status[provider] = "not_run"
        continue
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows, summary = scorer.score(raw["results"])
    (RESULTS / f"{provider}-scored-rows.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    models[provider] = summary
    provider_status[provider] = "complete" if summary["success_count"] == summary["sample_count"] else "partial"

metrics = {
    "experiment": {
        **QWEN_METRICS["experiment"],
        "sample_count": 50,
        "ocr_cache_dataset": "ltrngnhn/invoice-50-holdout-ocr-cache",
        "ocr_cache_sha256": hashlib.sha256((RUN_DIR / "inputs/holdout-ocr.json").read_bytes()).hexdigest(),
        "qwen_source_commit": QWEN_METRICS["experiment"]["source_commit"],
        "provider_model_ids": {
            "groq": "openai/gpt-oss-120b",
            "gemini": "gemini-3.1-flash-lite",
        },
        "api_prompt_source": "InvoiceTextProcessor from main commit " + QWEN_METRICS["experiment"]["source_commit"],
        "api_run_host": "local for Groq and Gemini after Kaggle secret access failed before provider requests",
    },
    "provider_status": provider_status,
    "models": models,
}
(RESULTS / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

def pct(value):
    return "—" if value is None else f"{value * 100:.1f}%"

def row(name, result):
    if "whole_invoice_exact_rate" in result:
        successes = result.get("success_count", result.get("inference_success_count", 0))
        samples = 50 if name in ("groq", "gemini") else result["sample_count"]
        complete = name not in provider_status or provider_status[name] == "complete"
        whole = result["whole_invoice_exact_rate"] if complete else None
        items = result.get("item_row_exact_accuracy", result.get("item_row_exact_accuracy_macro_invoice")) if complete else None
        latency = result.get("end_to_end_latency_seconds", {}).get("mean", result.get("mean_inference_seconds")) if complete else None
    else:
        samples, successes, whole, items, latency = 50, 0, None, None, None
    latency_text = "—" if latency is None else f"{latency:.2f}s"
    return f"| {name} | {successes}/{samples} | {pct(whole)} | {pct(items)} | {latency_text} |"

lines = [
    "# Invoice extraction rerun — 2026-11-12",
    "",
    "## Scope",
    "",
    "All models use the same 50 held-out invoices, labels, and the exact `holdout-ocr.json` downloaded from Kaggle dataset `ltrngnhn/invoice-50-holdout-ocr-cache` (SHA-256 in `results/metrics.json`). OCR was produced by Docling 2.129.0 with fine-tuned VietOCR. The Qwen LoRA adapter was reused; training was not repeated. Qwen used Kaggle GPU inference; Groq and Gemini used local `.env` keys after Kaggle secret access failed before provider requests.",
    "",
    "## Results",
    "",
    "| Model | Successful | Whole invoice exact | Item row exact (macro) | Mean latency / invoice |",
    "|---|---:|---:|---:|---:|",
]
for model_name in ("qwen3-0.6b-base", "qwen3-0.6b-lora", "qwen3-1.7b-base", "groq", "gemini"):
    lines.append(row(model_name, models.get(model_name, {})))
lines.extend([
    "",
    "Whole-invoice exact requires matching all normalized header fields, totals, item count and every item row. The scoring function treats digits-only fields numerically and ignores a leading Vietnamese `Ngày` label for dates.",
    "",
    "## Interpretation",
    "",
    "The base Qwen3-0.6B did not recover line items. Fine-tuning raised item-row exact accuracy substantially, with slower inference. Qwen3-1.7B base was faster than the fine-tuned 0.6B and retained strong item-row accuracy. Neither Qwen model achieved a fully exact invoice under the strict all-fields metric. Gemini completed 50/50. Groq is incomplete: 6/50 succeeded, 39 requests were rejected with HTTP 429, and 5 invoices were not reached. The provider reported its 200,000-token daily limit was at 199,731. Accuracy metrics are withheld for Groq because coverage is partial.",
    "",
    "## Reproduction and artifacts",
    "",
    "- Kaggle notebook: [Invoice Qwen 50 Rerun 2026 11 12](https://www.kaggle.com/code/ltrngnhn/invoice-qwen-50-rerun-2026-11-12). Qwen was version 1; API-only code was Quick Saved as version 2 and attempted as version 3, which stopped before requests because Kaggle secret access raised `ConnectionError`.",
    "- Rerun source commit: `" + QWEN_METRICS["experiment"]["source_commit"] + "`.",
    "- Per-invoice predictions, scored rows, metrics and execution log are in [`results/`](results/).",
    "- Exact OCR input used by all five models: [`inputs/holdout-ocr.json`](inputs/holdout-ocr.json). The initial local API outputs from an older OCR serialization were discarded and rerun against this verified Kaggle cache.",
    "- API runner: [`run_api_benchmark.py`](run_api_benchmark.py). It reads provider keys from the local `.env` without writing them to outputs.",
])
(RUN_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
