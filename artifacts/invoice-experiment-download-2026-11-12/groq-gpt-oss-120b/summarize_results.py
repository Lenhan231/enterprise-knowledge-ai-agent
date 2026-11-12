"""Summarize the complete-evidence Groq candidate and baseline results."""
import hashlib
import json
from pathlib import Path

folder = Path(__file__).resolve().parent
root = folder.parents[1]
data = json.loads((folder / "results.json").read_text())
old = json.loads((root / "artifacts/kaggle-invoice-50-groq20b/output/groq20b-invoice-50/groq20b_results.json").read_text())
baseline = json.loads((root / "artifacts/invoice-pilot-50-new-vietocr/model_results.json").read_text())
ocr_bytes = (root / "artifacts/invoice-pilot-50-new-vietocr/ocr_results.json").read_bytes()
assert data["metadata"]["ocr_sha256"] == hashlib.sha256(ocr_bytes).hexdigest()
assert set(data["results"]) == set(old["results"])
assert len(data["results"]) == 50
metrics = data["metrics"]
models = [
    ("Qwen3-0.6B fine-tuned baseline", baseline["metrics"]["modal"]),
    ("Qwen3-1.7B base baseline", baseline["metrics"]["qwen17b"]),
    (baseline["metadata"]["gemini_model"] + " baseline", baseline["metrics"]["gemini"]),
    ("Groq GPT-OSS 20B original prompt", old["metrics"]),
    ("Groq GPT-OSS 120B complete-evidence prompt v2", metrics),
]
lines = [
    "# Groq invoice extraction — model and prompt update", "",
    "Candidate source commit " + data["metadata"]["source_commit"],
    "Same 50 cached Kaggle VietOCR outputs and the previous normalized exact-match scoring.",
    "The new API benchmark ran locally over cached OCR; earlier baselines ran separately.",
    "Because both model and prompt changed, the comparison measures their combined effect.", "",
    "| Model | Completed | Whole-invoice exact | Item-row exact | Mean extraction seconds |",
    "|---|---:|---:|---:|---:|",
]
for name, m in models:
    lines.append(f"| {name} | {m['success_count']}/50 | {m['whole_invoice_exact_rate']:.1%} "
                 f"| {m['item_row_exact_accuracy']:.1%} | {m['end_to_end_latency_seconds']['mean']:.2f} |")
lines += ["", "Extraction times exclude cached OCR and include quota pacing/retries.", "",
          "## Field accuracy", "", "| Field | 20B original | 120B + prompt v2 |", "|---|---:|---:|"]
for key, value in metrics["header_exact_match_rates"].items():
    lines.append(f"| {key} | {old['metrics']['header_exact_match_rates'][key]:.1%} | {value:.1%} |")
usage = metrics["usage"]
cost = (usage["prompt_tokens"] * 0.15 + usage["generated_tokens"] * 0.60) / 1_000_000
lines += ["", f"Candidate usage {usage}", f"Estimated token cost USD {cost:.6f}.",
          "Rates used are USD 0.15 input and USD 0.60 output per million tokens.",
          "Failed attempts and retries may add cost not represented by successful-result usage.",
          f"Schema-valid rate {metrics['schema_valid_rate']:.1%}; parse errors {metrics['parse_error_count']}.", ""]
(folder / "comparison.md").write_text("\n".join(lines))
print("\n".join(lines))
