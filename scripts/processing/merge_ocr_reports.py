#!/usr/bin/env python3
"""Combine hash-paired OCR reports over disjoint subsets of one label set."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from scripts.processing.evaluate_ocr import (  # noqa: E402
    edit_distance,
    matched_table_row_indices,
    normalize,
    summarize_pages,
    table_cell_text_counts,
)


def page_identity(row: dict) -> tuple[str, int, str]:
    return row.get("document_id"), row.get("page"), row.get("language")


def merge_reports(dataset: dict, dataset_sha256: str, report_paths: list[Path]) -> dict[str, dict]:
    expected = {}
    labels_by_page = {}
    for page in dataset["pages"]:
        identity = (page["document_id"], page["page"], page["language"])
        if identity in expected:
            raise ValueError(f"Duplicate page in merged dataset: {identity}")
        if not page.get("source_pdf_sha256") or not page.get("rendered_image_sha256"):
            raise ValueError(f"Dataset page is missing source/render hashes: {identity}")
        expected[identity] = (page["source_pdf_sha256"], page["rendered_image_sha256"])
        labels_by_page[identity] = page

    groups: dict[str, list[tuple[Path, dict, dict]]] = defaultdict(list)
    for path in report_paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        engines = report.get("engines", {})
        if len(engines) != 1:
            raise ValueError(f"Each input must contain exactly one engine: {path}")
        name, engine = next(iter(engines.items()))
        if report.get("render_dpi") != dataset.get("render_dpi"):
            raise ValueError(f"Render DPI does not match merged dataset: {path}")
        groups[name].append((path, report, engine))

    merged = {}
    dataset_order = list(expected)
    for name, inputs in groups.items():
        _, baseline_report, baseline_engine = inputs[0]
        settings = baseline_report.get("ocr_configuration")
        version = baseline_engine.get("engine_version")
        device = baseline_engine.get("runtime_device")
        baseline_environment = baseline_report.get("environment", {})
        environment_signature = tuple(
            baseline_environment.get(key)
            for key in ("python", "platform", "gpu", "cuda_available")
        )
        seen = {}
        for path, report, engine in inputs:
            if report.get("render_dpi") != baseline_report.get("render_dpi"):
                raise ValueError(f"Mixed render DPI for {name}: {path}")
            if report.get("ocr_configuration") != settings:
                raise ValueError(f"Mixed OCR settings for {name}: {path}")
            if engine.get("engine_version") != version or engine.get("runtime_device") != device:
                raise ValueError(f"Mixed model version or runtime device for {name}: {path}")
            current_environment = report.get("environment", {})
            if tuple(current_environment.get(key) for key in ("python", "platform", "gpu", "cuda_available")) != environment_signature:
                raise ValueError(f"Mixed runtime environment for {name}: {path}")
            for row in engine.get("pages", []):
                identity = page_identity(row)
                if identity not in expected:
                    raise ValueError(f"Unexpected page in {path}: {identity}")
                hashes = (row.get("source_pdf_sha256"), row.get("rendered_image_sha256"))
                if hashes != expected[identity]:
                    raise ValueError(f"Source/render hash mismatch for {identity} in {path}")
                if identity in seen:
                    raise ValueError(f"Duplicate page for {name}: {identity}")
                seen[identity] = row
        missing = set(expected) - set(seen)
        if missing:
            raise ValueError(f"{name} reports do not cover the merged dataset: {sorted(missing)}")

        for identity, row in seen.items():
            label = labels_by_page[identity]
            reference = normalize(label.get("reference_text", ""))
            hypothesis = normalize(row.get("hypothesis_text", ""))
            row["reference_source"] = label.get("reference_annotation_method", "reviewed_reference")
            row["reference_characters"] = len(reference)
            row["reference_words"] = len(reference.split())
            row["hypothesis_characters"] = len(hypothesis)
            if row.get("error") or not reference:
                row["character_edit_distance"] = None
                row["word_edit_distance"] = None
                row["cer"] = None
                row["wer"] = None
            else:
                char_edits = edit_distance(reference, hypothesis)
                word_edits = edit_distance(reference.split(), hypothesis.split())
                row["character_edit_distance"] = char_edits
                row["word_edit_distance"] = word_edits
                row["cer"] = round(char_edits / len(reference), 6)
                row["wer"] = round(word_edits / len(reference.split()), 6)
            table_rows = label.get("table_rows", [])
            if table_rows:
                if row.get("error"):
                    exact_indices = None
                    cells_matched = None
                    cells_expected = None
                else:
                    exact_indices = matched_table_row_indices(table_rows, row.get("hypothesis_text", ""))
                    cells_matched, cells_expected = table_cell_text_counts(
                        table_rows, row.get("hypothesis_text", ""),
                    )
                row["table_rows_expected"] = len(table_rows)
                row["table_rows_exact"] = len(exact_indices) if exact_indices is not None else None
                row["table_row_recall"] = (
                    round(len(exact_indices) / len(table_rows), 6) if exact_indices is not None else None
                )
                row["exact_table_row_indices"] = exact_indices
                row["table_cells_expected"] = cells_expected
                row["table_cells_text_matched"] = cells_matched
                row["table_cell_text_recall"] = (
                    round(cells_matched / cells_expected, 6) if cells_expected else None
                )

        engine = copy.deepcopy(baseline_engine)
        engine["pages"] = [seen[identity] for identity in dataset_order]
        engine["aggregate"] = summarize_pages(engine["pages"])
        engine["by_language"] = {
            language: summarize_pages([row for row in engine["pages"] if row.get("language") == language])
            for language in sorted({page["language"] for page in dataset["pages"]})
        }
        initializations = [item[2].get("model_initialization_seconds") for item in inputs]
        engine["source_run_initialization_seconds"] = initializations
        if all(value is not None for value in initializations):
            engine["model_initialization_seconds"] = round(sum(initializations), 3)
        engine["memory_telemetry"] = {
            key: max(
                (item[2].get("memory_telemetry", {}).get(key) for item in inputs
                 if item[2].get("memory_telemetry", {}).get(key) is not None),
                default=None,
            )
            for key in (
                "torch_cuda_peak_allocated_mb", "torch_cuda_peak_reserved_mb",
            )
        }
        engine["memory_telemetry"]["measurement_scope"] = "maximum across source reports; runs were separate"
        engine["source_report_sha256"] = [
            hashlib.sha256(path.read_bytes()).hexdigest() for path, _, _ in inputs
        ]
        environment = copy.deepcopy(baseline_report.get("environment", {}))
        environment["source_run_environments"] = [
            {"path": str(path.relative_to(REPO_ROOT)), **report.get("environment", {})}
            for path, report, _ in inputs
        ]
        for key in ("process_peak_rss_mb", "child_peak_rss_mb"):
            values = [report.get("environment", {}).get(key) for _, report, _ in inputs]
            values = [value for value in values if value is not None]
            environment[key] = max(values) if values else None
        merged[name] = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "dataset": dataset["dataset_id"],
            "dataset_sha256": dataset_sha256,
            "source_dataset_sha256s": sorted({report["dataset_sha256"] for _, report, _ in inputs}),
            "source_reports": [
                {"path": str(path.relative_to(REPO_ROOT)),
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                 "dataset": report.get("dataset"),
                 "dataset_sha256": report.get("dataset_sha256")}
                for path, report, _ in inputs
            ],
            "reference_method": dataset["reference_method"],
            "reference_quality": dataset["reference_quality"],
            "limitations": dataset["limitations"],
            "render_dpi": baseline_report["render_dpi"],
            "environment": environment,
            "ocr_configuration": settings,
            "engines": {name: engine},
        }
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()
    dataset_path = args.dataset if args.dataset.is_absolute() else REPO_ROOT / args.dataset
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    dataset_bytes = dataset_path.read_bytes()
    dataset = json.loads(dataset_bytes)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        parser.error(f"output directory must be empty: {output_dir}")
    reports = [path if path.is_absolute() else REPO_ROOT / path for path in args.reports]
    merged = merge_reports(dataset, hashlib.sha256(dataset_bytes).hexdigest(), reports)
    written = []
    for name, report in merged.items():
        engine = report["engines"][name]
        psm = report.get("ocr_configuration", {}).get("tesseract_page_segmentation_mode")
        filename = f"{name}_psm{psm}.json" if name == "tesseract" and psm else f"{name}.json"
        path = output_dir / filename
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(str(path))
    print(json.dumps({"dataset": dataset["dataset_id"], "outputs": written}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
