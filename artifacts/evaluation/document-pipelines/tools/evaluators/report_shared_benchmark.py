"""Render and write shared benchmark Markdown reports."""

from __future__ import annotations

from pathlib import Path


def render_report(result: dict) -> str:
    def pct(value): return "n/a" if value is None else f"{value:.2%}"
    runtime = result["runtime"]
    if runtime["inference_wall_seconds"] is None:
        runtime_line = "**Runtime:** inference timing unavailable"
    elif result.get("selected_reference_ids") and runtime["source_run_inference_wall_seconds"] is not None:
        runtime_line = (
            f"**Runtime:** {runtime['inference_wall_seconds']}s summed selected-page inference on {runtime['device']} "
            f"(source full-run total: {runtime['source_run_inference_wall_seconds']}s; excludes initialization)"
        )
    elif result.get("selected_reference_ids"):
        runtime_line = f"**Runtime:** {runtime['inference_wall_seconds']}s summed selected-page inference on {runtime['device']}"
    else:
        runtime_line = f"**Runtime:** {runtime['inference_wall_seconds']}s on {runtime['device']}"
    lines = [f"# {result['engine']} benchmark: {result['dataset']}", "",
             f"**Run:** `{result['run_id']}` · **Predictions:** {result['coverage']['prediction_pages']} pages · **Inference success:** {result['coverage']['inference_successful_pages']}",
             runtime_line +
             (f" · peak process RSS {runtime['peak_process_rss_mib']} MiB" if runtime['peak_process_rss_mib'] is not None else " · peak inference RSS unavailable"), ""]
    if result.get("selected_reference_ids"):
        lines.append("**Scored pilot pages:** " + ", ".join(f"`{page_id}`" for page_id in result["selected_reference_ids"]))
        lines.append("")
    lines.extend([
             "## Independent layer scores", "",
             "| Layer | Cohort | Metrics |", "|---|---:|---|",
             f"| OCR | {result['layer_scores']['ocr']['pages']} pages | full-page CER {pct(result['layer_scores']['ocr']['micro_cer'])}; full-page WER (PyVi) {pct(result['layer_scores']['ocr']['micro_wer_pyvi'])} |",
             f"| Reading order | {result['layer_scores']['reading_order']['pages']} pages | pairwise accuracy {pct(result['layer_scores']['reading_order']['micro_pairwise_accuracy'])}; matched-region recall {pct(result['layer_scores']['reading_order']['matched_region_recall'])} |",
             f"| Layout | {result['layer_scores']['layout']['pages']} pages | micro P/R/F1 {pct(result['layer_scores']['layout']['micro']['precision'])} / {pct(result['layer_scores']['layout']['micro']['recall'])} / {pct(result['layer_scores']['layout']['micro']['f1'])} |",
             f"| Table | {result['layer_scores']['table']['reference_tables']} tables on {result['layer_scores']['table']['pages_with_reviewed_tables']} pages | detection P/R/F1 {pct(result['layer_scores']['table']['detection_precision'])} / {pct(result['layer_scores']['table']['detection_recall'])} / {pct(result['layer_scores']['table']['detection_f1'])}; cell CER {pct(result['layer_scores']['table']['micro_cell_cer'])}; cell WER (whitespace) {pct(result['layer_scores']['table']['micro_cell_wer_whitespace'])}; exact grids {pct(result['layer_scores']['table']['exact_grid_rate'])} |", "",
             "### Layout per-class scores", "",
             "| Class | Precision | Recall | F1 | Reference regions | Predicted regions |", "|---|---:|---:|---:|---:|---:|"])
    for label, scores in result["layer_scores"]["layout"]["per_class"].items():
        lines.append(
            f"| {label} | {pct(scores['precision'])} | {pct(scores['recall'])} | {pct(scores['f1'])} | "
            f"{scores['reference_regions']} | {scores['predicted_regions']} |"
        )
    lines.extend([
             "",
             "## End-to-end cohort", "",
             f"{result['end_to_end_scores']['pages']} pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.", "",
             "| Layer | Metrics |", "|---|---|",
             f"| OCR | full-page CER {pct(result['end_to_end_scores']['ocr']['micro_cer'])}; full-page WER (PyVi) {pct(result['end_to_end_scores']['ocr']['micro_wer_pyvi'])} |",
             f"| Reading order | pairwise accuracy {pct(result['end_to_end_scores']['reading_order']['micro_pairwise_accuracy'])}; matched-region recall {pct(result['end_to_end_scores']['reading_order']['matched_region_recall'])} |",
             f"| Layout | micro P/R/F1 {pct(result['end_to_end_scores']['layout']['micro']['precision'])} / {pct(result['end_to_end_scores']['layout']['micro']['recall'])} / {pct(result['end_to_end_scores']['layout']['micro']['f1'])} |",
             f"| Table | detection P/R {pct(result['end_to_end_scores']['table']['detection_precision'])} / {pct(result['end_to_end_scores']['table']['detection_recall'])}; cell CER {pct(result['end_to_end_scores']['table']['micro_cell_cer'])}; cell WER (whitespace) {pct(result['end_to_end_scores']['table']['micro_cell_wer_whitespace'])} |", "",
             "## Notes", ""])
    lines.extend(f"- {note}" for note in result["caveats"])
    lines.append("")
    return "\n".join(lines)



def write_report(result: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.md"
    report_path.write_text(render_report(result), encoding="utf-8")
    return report_path
