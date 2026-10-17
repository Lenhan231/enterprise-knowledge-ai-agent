"""Score MinerU preprocessing variants with the existing benchmark metrics."""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from pathlib import Path
from types import SimpleNamespace

from evaluate_document_pipeline_layout import run as score_layout
from evaluate_document_pipeline_ocr import score_text
from evaluate_document_pipeline_pilot import load_page_text
from evaluate_document_pipeline_reading_order import run as score_reading_order
from evaluate_document_pipeline_tables import extract_grid, score_grid


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "artifacts/evaluation/document-pipelines"
LAYOUT_REFERENCE = ROOT / "data/evaluation/layout/vn-enterprise-layout-v2-adjudicated-reference.json"
READING_ORDER_REFERENCE = ROOT / "data/evaluation/layout/vn-enterprise-reading-order-reference.json"
LAYOUT_MANIFEST = DATA / "layout/inputs/manifest.json"
OCR_REFERENCE = DATA / "ocr/reference/reference.csv"
TABLE_REFERENCE = DATA / "tables/reference/reference.jsonl"
SPLITS = ("development", "validation")
BOOTSTRAP_RESAMPLES = 10_000


def load_references() -> tuple[list[dict], list[dict]]:
    with OCR_REFERENCE.open(encoding="utf-8-sig", newline="") as handle:
        ocr = list(csv.DictReader(handle))
    tables = [json.loads(line) for line in TABLE_REFERENCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    return ocr, tables


def summarize_ocr(rows: list[dict]) -> dict:
    scored = [row for row in rows if row["metric"] is not None]
    char_total = sum(row["metric"]["reference_characters"] for row in scored)
    word_total = sum(row["metric"]["reference_words"] for row in scored)
    return {
        "items": len(rows),
        "outputs_found": sum(row["output_found"] for row in rows),
        "micro_cer": sum(row["metric"]["cer"] * row["metric"]["reference_characters"] for row in scored) / char_total if char_total else None,
        "macro_cer": statistics.mean(row["metric"]["cer"] for row in scored) if scored else None,
        "micro_wer": sum(row["metric"]["wer"] * row["metric"]["reference_words"] for row in scored) / word_total if word_total else None,
        "macro_wer": statistics.mean(row["metric"]["wer"] for row in scored) if scored else None,
    }


def score_ocr(raw_root: Path, references: list[dict], split: str) -> dict:
    rows = []
    for reference in references:
        if reference.get("split") != split:
            continue
        sample_id = reference["sample_id"]
        hypothesis, details = load_page_text("mineru-basic", sample_id, raw_root)
        found = details.get("archives", 0) > 0
        metric = score_text(reference["corrected_transcript"], hypothesis) if found else None
        rows.append({"sample_id": sample_id, "issuer": reference.get("issuer"), "output_found": found, "metric": metric, "details": details})
    return {"summary": summarize_ocr(rows), "items": rows}


def summarize_tables(rows: list[dict]) -> dict:
    scored = [row for row in rows if row["metrics"]["cell_accuracy"] is not None]
    positions = sum(row["metrics"]["cell_positions_scored"] for row in scored)
    matches = sum(row["metrics"]["cell_matches"] for row in scored)
    return {
        "items": len(rows),
        "outputs_found": sum(row["output_found"] for row in rows),
        "tables_found": sum(row["metrics"]["predicted_table_found"] for row in scored),
        "micro_cell_accuracy": matches / positions if positions else None,
        "exact_grid_rate": statistics.mean(row["metrics"]["exact_grid"] for row in scored) if scored else None,
        "shape_exact_rate": statistics.mean(row["metrics"]["shape_exact"] for row in scored) if scored else None,
    }


def score_tables(raw_root: Path, references: list[dict], split: str) -> dict:
    archives = list((raw_root / "mineru-output").rglob("*.zip"))
    rows = []
    for reference in references:
        if reference.get("split") != split:
            continue
        prediction, metadata = extract_grid("mineru-basic", reference["reference_id"], raw_root, archives)
        rows.append({
            "reference_id": reference["reference_id"],
            "issuer": reference.get("issuer"),
            "output_found": metadata.get("output_found", False),
            "metrics": score_grid(reference["cell_grid"], prediction),
            "metadata": metadata,
        })
    return {"summary": summarize_tables(rows), "items": rows}


def score_layout_split(raw_root: Path, split: str) -> dict:
    return score_layout(SimpleNamespace(
        manifest=LAYOUT_MANIFEST,
        reference=LAYOUT_REFERENCE,
        engine="mineru",
        kernel_id="mineru-preprocessing-variants",
        raw_root=raw_root,
        output=Path("unused"),
        iou_threshold=0.5,
        scored_classes=None,
        splits=[split],
        positive_regions_only=False,
    ))


def score_order_split(raw_root: Path, split: str) -> dict:
    return score_reading_order(SimpleNamespace(
        engine="mineru",
        raw_root=raw_root,
        manifest=LAYOUT_MANIFEST,
        layout_reference=LAYOUT_REFERENCE,
        reference=READING_ORDER_REFERENCE,
        reviewed_reference=None,
        iou_threshold=0.5,
        splits=[split],
        output=Path("unused"),
    ))


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def paired_issuer_bootstrap(pairs: list[dict], aggregate, seed: int) -> dict:
    """Percentile intervals resample issuers and retain all their paired items."""
    if not pairs:
        return {"paired_items": 0, "issuer_clusters": 0, "resamples": BOOTSTRAP_RESAMPLES, "deltas": {}}
    grouped: dict[str, list[dict]] = {}
    for pair in pairs:
        grouped.setdefault(str(pair["issuer"] or "unknown"), []).append(pair)
    issuers = sorted(grouped)
    point = aggregate(pairs)
    rng = random.Random(seed)
    distributions = {name: [] for name in point}
    for _ in range(BOOTSTRAP_RESAMPLES):
        sampled_issuers = [rng.choice(issuers) for _ in issuers]
        sampled_pairs = [pair for issuer in sampled_issuers for pair in grouped[issuer]]
        for metric, delta in aggregate(sampled_pairs).items():
            if delta is not None:
                distributions[metric].append(delta)
    return {
        "paired_items": len(pairs),
        "issuer_clusters": len(issuers),
        "resamples": BOOTSTRAP_RESAMPLES,
        "deltas": {
            metric: {
                "candidate_minus_V0": value,
                "ci95_percentile": [percentile(distributions[metric], 0.025), percentile(distributions[metric], 0.975)] if distributions[metric] else None,
            }
            for metric, value in point.items()
        },
    }


def pair_rows(base_rows: list[dict], candidate_rows: list[dict], key: str, issuer_by_key: dict[str, str] | None = None) -> list[dict]:
    base_by_id = {str(row[key]): row for row in base_rows}
    candidate_by_id = {str(row[key]): row for row in candidate_rows}
    pairs = []
    for item_id in sorted(base_by_id.keys() & candidate_by_id.keys()):
        base, candidate = base_by_id[item_id], candidate_by_id[item_id]
        issuer = issuer_by_key.get(item_id) if issuer_by_key else (base.get("issuer") or candidate.get("issuer"))
        pairs.append({"issuer": issuer, "baseline": base, "candidate": candidate})
    return pairs


def aggregate_ocr_delta(pairs: list[dict]) -> dict:
    usable = [pair for pair in pairs if pair["baseline"].get("metric") and pair["candidate"].get("metric")]
    def rates(side: str, metric: str, denominator: str) -> tuple[float | None, float | None]:
        rows = [pair[side]["metric"] for pair in usable]
        total = sum(row[denominator] for row in rows)
        micro = sum(row[metric] * row[denominator] for row in rows) / total if total else None
        macro = statistics.mean(row[metric] for row in rows) if rows else None
        return micro, macro
    base_cer, base_macro_cer = rates("baseline", "cer", "reference_characters")
    candidate_cer, candidate_macro_cer = rates("candidate", "cer", "reference_characters")
    base_wer, base_macro_wer = rates("baseline", "wer", "reference_words")
    candidate_wer, candidate_macro_wer = rates("candidate", "wer", "reference_words")
    return {
        "micro_cer": candidate_cer - base_cer if candidate_cer is not None and base_cer is not None else None,
        "macro_cer": candidate_macro_cer - base_macro_cer if candidate_macro_cer is not None and base_macro_cer is not None else None,
        "micro_wer": candidate_wer - base_wer if candidate_wer is not None and base_wer is not None else None,
        "macro_wer": candidate_macro_wer - base_macro_wer if candidate_macro_wer is not None and base_macro_wer is not None else None,
    }


def aggregate_table_delta(pairs: list[dict]) -> dict:
    usable = [pair for pair in pairs if pair["baseline"]["metrics"]["cell_accuracy"] is not None and pair["candidate"]["metrics"]["cell_accuracy"] is not None]
    def cell_accuracy(side: str) -> float | None:
        rows = [pair[side]["metrics"] for pair in usable]
        total = sum(row["cell_positions_scored"] for row in rows)
        return sum(row["cell_matches"] for row in rows) / total if total else None
    base_cell, candidate_cell = cell_accuracy("baseline"), cell_accuracy("candidate")
    deltas = {"micro_cell_accuracy": candidate_cell - base_cell if candidate_cell is not None and base_cell is not None else None}
    for metric in ("exact_grid", "shape_exact"):
        base = statistics.mean(pair["baseline"]["metrics"][metric] for pair in usable) if usable else None
        candidate = statistics.mean(pair["candidate"]["metrics"][metric] for pair in usable) if usable else None
        deltas[f"{metric}_rate"] = candidate - base if candidate is not None and base is not None else None
    return deltas


def aggregate_layout_delta(pairs: list[dict]) -> dict:
    classes = sorted({label for pair in pairs for label in pair["baseline"].get("classes", {})})
    deltas = {}
    counts = {}
    for side in ("baseline", "candidate"):
        total_tp = total_fp = total_fn = 0
        for label in classes:
            total_tp += sum(pair[side]["classes"][label]["true_positive"] for pair in pairs)
            total_fp += sum(pair[side]["classes"][label]["false_positive"] for pair in pairs)
            total_fn += sum(pair[side]["classes"][label]["false_negative"] for pair in pairs)
        precision = total_tp / (total_tp + total_fp) if total_tp + total_fp else 0.0
        recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 0.0
        counts[side] = {"micro_precision": precision, "micro_recall": recall, "micro_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}
    for metric in ("micro_precision", "micro_recall", "micro_f1"):
        deltas[metric] = counts["candidate"][metric] - counts["baseline"][metric]
    for label in classes:
        counts = {}
        for side in ("baseline", "candidate"):
            tp = sum(pair[side]["classes"][label]["true_positive"] for pair in pairs)
            fp = sum(pair[side]["classes"][label]["false_positive"] for pair in pairs)
            fn = sum(pair[side]["classes"][label]["false_negative"] for pair in pairs)
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            counts[side] = {"precision": precision, "recall": recall, "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}
        for metric in ("precision", "recall", "f1"):
            deltas[f"{label}_{metric}"] = counts["candidate"][metric] - counts["baseline"][metric]
    return deltas


def aggregate_reading_order_delta(pairs: list[dict]) -> dict:
    deltas = {}
    for metric, numerator, denominator in (
        ("matched_block_coverage", "matched_blocks", "reference_blocks"),
        ("pairwise_order_accuracy", "pairwise_order_correct", "pairwise_order_total"),
    ):
        rates = {}
        for side in ("baseline", "candidate"):
            total = sum(pair[side][denominator] for pair in pairs)
            rates[side] = sum(pair[side][numerator] for pair in pairs) / total if total else None
        deltas[metric] = rates["candidate"] - rates["baseline"] if rates["candidate"] is not None and rates["baseline"] is not None else None
    return deltas


def apply_paired_deltas(variants: dict, layout_issuer_by_id: dict[str, str]) -> None:
    baseline = variants.get("V0", {}).get("tracks", {})
    for variant_name, variant in variants.items():
        if variant_name == "V0":
            continue
        for track in ("ocr", "tables", "layout"):
            for split in SPLITS:
                base_result = baseline.get(track, {}).get(split, {})
                candidate_result = variant["tracks"].get(track, {}).get(split, {})
                if base_result.get("status") != "scored" or candidate_result.get("status") != "scored":
                    continue
                if track == "ocr":
                    pairs = pair_rows(base_result["items"], candidate_result["items"], "sample_id")
                    pairs = [pair for pair in pairs if pair["baseline"].get("metric") and pair["candidate"].get("metric")]
                    aggregate = aggregate_ocr_delta
                elif track == "tables":
                    pairs = pair_rows(base_result["items"], candidate_result["items"], "reference_id")
                    pairs = [pair for pair in pairs if pair["baseline"]["metrics"]["cell_accuracy"] is not None and pair["candidate"]["metrics"]["cell_accuracy"] is not None]
                    aggregate = aggregate_table_delta
                else:
                    pairs = pair_rows(base_result["pages"], candidate_result["pages"], "input_id", layout_issuer_by_id)
                    aggregate = aggregate_layout_delta
                candidate_result["paired_delta_vs_V0"] = paired_issuer_bootstrap(pairs, aggregate, seed=20261016)
        for split in SPLITS:
            key = f"reading_order_{split}"
            base_order = variants.get("V0", {}).get(key)
            candidate_order = variant.get(key)
            if base_order and candidate_order and base_order.get("page_count") and candidate_order.get("page_count"):
                pairs = pair_rows(base_order["pages"], candidate_order["pages"], "page_id", layout_issuer_by_id)
                variant[key]["paired_delta_vs_V0"] = paired_issuer_bootstrap(
                    pairs, aggregate_reading_order_delta, seed=20261016
                )


def assess_candidate(name: str, candidate: dict, baseline: dict) -> dict:
    tracks = candidate.get("tracks", {})
    baseline_tracks = baseline.get("tracks", {})
    results = {track: tracks.get(track, {}).get("validation", {}) for track in ("ocr", "tables", "layout")}
    base_results = {track: baseline_tracks.get(track, {}).get("validation", {}) for track in ("ocr", "tables", "layout")}
    missing = [track for track, result in results.items() if result.get("status") != "scored"]
    order = candidate.get("reading_order_validation", {})
    base_order = baseline.get("reading_order_validation", {})
    if order.get("page_count", 0) == 0 or base_order.get("page_count", 0) == 0:
        missing.append("reading_order_validation_labels")
    if missing:
        return {"variant": name, "status": "incomplete_validation", "missing": sorted(set(missing)), "checks": {}}

    def delta(track: str, metric: str) -> float | None:
        return results[track].get("paired_delta_vs_V0", {}).get("deltas", {}).get(metric, {}).get("candidate_minus_V0")

    ocr_summary = results["ocr"]["summary"]
    base_ocr = base_results["ocr"]["summary"]
    cer_delta = delta("ocr", "micro_cer")
    cer_ci = results["ocr"].get("paired_delta_vs_V0", {}).get("deltas", {}).get("micro_cer", {}).get("ci95_percentile")
    table_delta = delta("tables", "micro_cell_accuracy")
    candidate_tables = results["tables"]["summary"]
    base_tables = base_results["tables"]["summary"]
    candidate_shape_count = sum(item["metrics"]["shape_exact"] for item in results["tables"]["items"])
    base_shape_count = sum(item["metrics"]["shape_exact"] for item in base_results["tables"]["items"])
    layout_delta = delta("layout", "micro_f1")
    order_deltas = order.get("paired_delta_vs_V0", {}).get("deltas", {})
    checks = {
        "ocr_micro_cer_improved_with_ci": cer_delta is not None and cer_delta < 0 and cer_ci is not None and cer_ci[1] < 0,
        "ocr_micro_cer_guardrail": cer_delta is not None and cer_delta <= 0.01,
        "ocr_micro_wer_guardrail": delta("ocr", "micro_wer") is not None and delta("ocr", "micro_wer") <= 0.02,
        "ocr_validation_coverage": ocr_summary["outputs_found"] == ocr_summary["items"] == 100,
        "table_cell_accuracy_guardrail": table_delta is not None and table_delta >= -0.02,
        "table_found_all_29": candidate_tables["tables_found"] == candidate_tables["items"] == 29,
        "table_exact_shape_loses_at_most_one": candidate_shape_count >= base_shape_count - 1 and len(results["tables"]["items"]) == 29,
        "layout_micro_f1_guardrail": layout_delta is not None and layout_delta >= -0.02,
        "layout_each_class_f1_guardrail": all(
            delta("layout", f"{label}_f1") is not None and delta("layout", f"{label}_f1") >= -0.03
            for label in ("title", "text", "table", "figure")
        ),
        "reading_order_coverage_guardrail": order_deltas.get("matched_block_coverage", {}).get("candidate_minus_V0") is not None and order_deltas["matched_block_coverage"]["candidate_minus_V0"] >= -0.02,
        "reading_order_pairwise_guardrail": order_deltas.get("pairwise_order_accuracy", {}).get("candidate_minus_V0") is not None and order_deltas["pairwise_order_accuracy"]["candidate_minus_V0"] >= -0.02,
    }
    validation_runs = [row for row in candidate.get("resource_runs", []) if row["split"] == "validation"]
    count = sum(row.get("items") or 0 for row in validation_runs)
    end_to_end_seconds_per_page = None
    if count:
        end_to_end_seconds_per_page = sum(
            sum(row.get(field) or 0 for field in ("preprocess_seconds", "batch_inference_seconds", "fallback_seconds"))
            for row in validation_runs
        ) / count
    transforms = sum(
        (row.get("inference_resources") or {}).get("total_transforms_applied", 0)
        for row in candidate.get("resource_runs", [])
        if row["split"] == "validation"
    )
    return {
        "variant": name,
        "status": "eligible" if all(checks.values()) else "rejected_by_predeclared_gates",
        "checks": checks,
        "validation_micro_cer": ocr_summary["micro_cer"],
        "validation_micro_wer": ocr_summary["micro_wer"],
        "validation_end_to_end_seconds_per_page_single_run": end_to_end_seconds_per_page,
        "validation_transforms_applied": transforms,
    }


def select_validation_candidate(variants: dict) -> dict:
    baseline = variants.get("V0")
    if baseline is None:
        return {"status": "waiting_for_V0", "selected_variant": None, "candidates": []}
    names = sorted(name for name in variants if name.startswith("V4-"))
    if len(names) != 6:
        return {"status": "waiting_for_all_six_V4_candidates", "selected_variant": None, "candidates": names}
    assessments = [assess_candidate(name, variants[name], baseline) for name in names]
    if any(result["status"] == "incomplete_validation" for result in assessments):
        return {"status": "waiting_for_validation_metrics_or_reading_order_labels", "selected_variant": None, "candidates": assessments}
    selected = [result for result in assessments if result["status"] == "eligible"]
    selection_type = "adaptive"
    if not selected:
        if not {"V1", "V2", "V3"}.issubset(variants):
            return {"status": "waiting_for_complete_ablation_grid", "selected_variant": None, "candidates": assessments}
        fixed = [name for name in ("V1", "V2", "V3")]
        fixed_assessments = [assess_candidate(name, variants[name], baseline) for name in fixed]
        if any(result["status"] == "incomplete_validation" for result in fixed_assessments):
            return {"status": "waiting_for_complete_ablation_grid", "selected_variant": None, "candidates": assessments + fixed_assessments}
        selected = [result for result in fixed_assessments if result["status"] == "eligible"]
        assessments.extend(fixed_assessments)
        selection_type = "best_fixed_transform"
    if not selected:
        return {"status": "no_variant_passed; retain_V0", "selected_variant": "V0", "selection_type": "control", "candidates": assessments}
    selected.sort(key=lambda row: (
        row["validation_micro_cer"],
        row["validation_micro_wer"],
        row["validation_end_to_end_seconds_per_page_single_run"] if row["validation_end_to_end_seconds_per_page_single_run"] is not None else float("inf"),
        row["validation_transforms_applied"],
    ))
    return {"status": "selected_on_validation", "selected_variant": selected[0]["variant"], "selection_type": selection_type, "candidates": assessments}


def run(run_root: Path, output: Path, include_locked_test: bool = False) -> dict:
    ocr_refs, table_refs = load_references()
    variant_dirs = sorted(path for path in run_root.iterdir() if path.is_dir())
    scored_splits = (*SPLITS, "locked_test") if include_locked_test else SPLITS
    variants = {}
    for variant_dir in variant_dirs:
        variant_result = {"tracks": {}, "resource_runs": []}
        for track in ("ocr", "tables", "layout"):
            track_result = {}
            for split in scored_splits:
                raw_root = variant_dir / track / split
                metadata_path = raw_root / "run-metadata.json"
                if not metadata_path.is_file():
                    track_result[split] = {"status": "missing_run"}
                    continue
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                variant_result["resource_runs"].append({
                    "track": track,
                    "split": split,
                    "status": metadata.get("status"),
                    "items": metadata.get("page_count"),
                    "preprocess_seconds": metadata.get("preprocess_seconds"),
                    "batch_inference_seconds": metadata.get("batch_inference_seconds"),
                    "fallback_seconds": metadata.get("single_input_fallback_seconds"),
                    "inference_resources": metadata.get("inference_resources"),
                    "total_transforms_applied": metadata.get("total_transforms_applied"),
                })
                if metadata.get("status") != "complete":
                    track_result[split] = {"status": "incomplete_run", "metadata": metadata}
                    continue
                if track == "ocr":
                    result = score_ocr(raw_root, ocr_refs, split)
                elif track == "tables":
                    result = score_tables(raw_root, table_refs, split)
                else:
                    result = score_layout_split(raw_root, split)
                track_result[split] = {"status": "scored", **result}
            variant_result["tracks"][track] = track_result

        for split in scored_splits:
            split_layout = variant_dir / "layout" / split
            metadata_path = split_layout / "run-metadata.json"
            if metadata_path.is_file() and json.loads(metadata_path.read_text(encoding="utf-8")).get("status") == "complete":
                result = score_order_split(split_layout, split)
                variant_result[f"reading_order_{split}"] = (
                    result if result["page_count"] else {"status": "missing_reference_labels", "page_count": 0, "splits_scored": [split]}
                )
        variants[variant_dir.name] = variant_result

    report = {
        "status": "scored_available_runs",
        "run_root": str(run_root),
        "scored_splits": list(scored_splits),
        "locked_test_scored": include_locked_test,
        "locked_test_usage": "retrospective comparison only; never a tuning or selection gate" if include_locked_test else None,
        "label_caveat": "Existing assistant-adjudicated labels; not independently human-reviewed.",
        "metrics": {
            "ocr": "Existing normalized CER/WER scoring; absent archive outputs count as missing, not zero CER.",
            "tables": "Existing row/column aligned exact cell accuracy and exact-grid metrics.",
            "layout": "Existing class-aware IoU 0.50 P/R/F1 evaluator.",
            "reading_order": "Existing order reference scored independently by layout split; missing validation annotations are reported as a missing gate, not a score.",
            "resources": "Runner-reported preprocessing and batch inference wall time; one-second sampled process-tree RSS, GPU-process memory, and device memory cover inference and retries. This tuning pass is single-repeat and does not replace the three-repeat 200-page performance benchmark.",
            "paired_comparisons": f"Candidate minus V0; 95% percentile confidence intervals from {BOOTSTRAP_RESAMPLES:,} paired issuer-cluster bootstrap resamples. OCR/table intervals include only paired items with both outputs; missing-output coverage is reported separately.",
        },
        "variants": variants,
    }
    layout_manifest = json.loads(LAYOUT_MANIFEST.read_text(encoding="utf-8"))
    layout_issuer_by_id = {page["id"]: page.get("issuer", "unknown") for page in layout_manifest["pages"]}
    apply_paired_deltas(variants, layout_issuer_by_id)
    report["selection"] = select_validation_candidate(variants)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True, help="MinerU preprocessing output root containing V0/, V1/, etc.")
    parser.add_argument("--output", type=Path, default=DATA / "results/mineru-preprocessing/variant-scores.json")
    parser.add_argument("--include-locked-test", action="store_true", help="Score locked test after selecting the configuration on validation; results are retrospective only.")
    args = parser.parse_args()
    report = run(args.run_root, args.output, include_locked_test=args.include_locked_test)
    print(json.dumps({"status": report["status"], "variants": list(report["variants"]), "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
