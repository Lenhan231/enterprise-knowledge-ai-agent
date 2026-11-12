"""Compare completed Groq results with the shared 50-invoice benchmark."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
base = root / "artifacts/invoice-pilot-50-new-vietocr"
parser = argparse.ArgumentParser()
parser.add_argument("results", type=Path)
args = parser.parse_args()
result = json.loads(args.results.read_text())
ocr_bytes = (base / "ocr_results.json").read_bytes()
assert result["metadata"]["ocr_sha256"] == hashlib.sha256(ocr_bytes).hexdigest(), "OCR inputs differ"
assert set(result["results"]) == set(json.loads(ocr_bytes)["samples"]), "Expected all 50 invoices"
spec = importlib.util.spec_from_file_location("benchmark_scoring", base / "run_model_benchmark.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
scores, metrics = module.score(list(result["results"].values()))
baseline = json.loads((base / "model_results.json").read_text())
comparisons = dict(baseline["metrics"])
comparisons["groq20b"] = metrics
names = {"modal": "Qwen3-0.6B fine-tuned", "qwen17b": "Qwen3-1.7B base",
         "gemini": baseline["metadata"]["gemini_model"], "groq20b": "Groq GPT-OSS 20B"}
lines = [
    "# Groq GPT-OSS 20B on 50 shared VietOCR outputs", "",
    "Production source commit " + result["metadata"]["source_commit"], "",
    "Whole-invoice exact uses the previous benchmark's normalized scoring.",
    "Extraction latency excludes cached OCR and includes quota pacing and retries.",
    "The providers were measured in separate runs.", "",
    "| Model | Completed | Whole-invoice exact | Item row exact | Mean extraction seconds |",
    "|---|---:|---:|---:|---:|",
]
for key, item in comparisons.items():
    lines.append(f"| {names[key]} | {item['success_count']}/50 | "
                 f"{item['whole_invoice_exact_rate']:.1%} | {item['item_row_exact_accuracy']:.1%} | "
                 f"{item['end_to_end_latency_seconds']['mean']:.2f} |")
lines += ["", "## Groq header accuracy", ""]
for key, value in metrics["header_exact_match_rates"].items():
    lines.append(f"- {key}: {value:.1%}")
usage = metrics["usage"]
cost = (usage["prompt_tokens"] * 0.075 + usage["generated_tokens"] * 0.30) / 1_000_000
lines += ["", f"Parse errors: {metrics['parse_error_count']}",
          f"Field conflicts: {metrics['field_conflict_count']}",
          f"Successful-result token usage: {usage}",
          f"Estimated successful-result token cost: USD {cost:.6f}. Failed jobs and retries may add cost.", ""]
out = Path(__file__).resolve().parent
(out / "comparison.md").write_text("\n".join(lines), encoding="utf-8")
(out / "scored_results.json").write_text(
    json.dumps({"metadata":result["metadata"],"metrics":metrics,"scores":scores},ensure_ascii=False,indent=2),
    encoding="utf-8")
print("\n".join(lines))
