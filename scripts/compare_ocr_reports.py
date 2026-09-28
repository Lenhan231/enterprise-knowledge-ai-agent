#!/usr/bin/env python3
"""Compare OCR reports only when dataset and rendered inputs match exactly."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _page_identity(row: dict) -> tuple:
    return (row.get("document_id"), row.get("page"), row.get("language"))


def _normalize(text: str) -> str:
    import re
    import unicodedata

    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def _table_cell_text_counts(table_rows: list[dict], hypothesis: str) -> tuple[int, int]:
    expected: dict[str, int] = {}
    for row in table_rows:
        for cell in (row["label"], *row["values"]):
            normalized = _normalize(cell)
            expected[normalized] = expected.get(normalized, 0) + 1
    tokens = _normalize(hypothesis).split()
    matched = 0
    for cell, count in expected.items():
        cell_tokens = cell.split()
        occurrences = sum(
            tokens[index:index + len(cell_tokens)] == cell_tokens
            for index in range(len(tokens) - len(cell_tokens) + 1)
        )
        matched += min(count, occurrences)
    return matched, sum(expected.values())


def compare_reports(reports: list[dict], dataset: dict | None = None) -> dict:
    if len(reports) < 2:
        raise ValueError("Provide at least two OCR reports")
    baseline = reports[0]
    dataset_hash = baseline.get("dataset_sha256")
    dpi = baseline.get("render_dpi")
    if not dataset_hash or not dpi:
        raise ValueError("Each OCR report must include dataset_sha256 and render_dpi")
    if len(baseline.get("engines", {})) != 1:
        raise ValueError("Each input report must contain exactly one OCR engine")
    table_rows_by_page = {}
    if dataset is not None:
        table_rows_by_page = {
            _page_identity(page): page.get("table_rows", [])
            for page in dataset.get("pages", [])
        }

    def input_pages(report: dict) -> dict:
        rows = next(iter(report.get("engines", {}).values())).get("pages", [])
        pages = {}
        for row in rows:
            identity = _page_identity(row)
            if None in identity or not row.get("source_pdf_sha256") or not row.get("rendered_image_sha256"):
                raise ValueError("Every OCR page must identify its document, page, language, PDF and rendered image hashes")
            if identity in pages:
                raise ValueError(f"Duplicate OCR page identity: {identity}")
            pages[identity] = (row["source_pdf_sha256"], row["rendered_image_sha256"])
        return pages

    reference_pages = input_pages(baseline)
    if not reference_pages:
        raise ValueError("OCR reports contain no page records")

    comparisons = []
    names = set()
    for report in reports:
        if report.get("dataset_sha256") != dataset_hash:
            raise ValueError("OCR reports use different dataset contents")
        if report.get("render_dpi") != dpi:
            raise ValueError("OCR reports use different render DPI")
        engines = report.get("engines", {})
        if len(engines) != 1:
            raise ValueError("Each input report must contain exactly one OCR engine")
        name, engine = next(iter(engines.items()))
        if name in names:
            raise ValueError(f"Duplicate OCR engine report: {name}")
        names.add(name)
        if input_pages(report) != reference_pages:
            raise ValueError(f"{name} report does not use the same source pages and rendered images")
        valid = [row for row in engine.get("pages", []) if row.get("cer") is not None and row.get("wer") is not None]
        chars = sum(row.get("reference_characters", 0) for row in valid)
        words = sum(row.get("reference_words", 0) for row in valid)
        char_edits = sum(row.get("character_edit_distance", 0) for row in valid)
        word_edits = sum(row.get("word_edit_distance", 0) for row in valid)
        latency = sum(row.get("latency_seconds", 0) for row in valid)
        comparisons.append({
            "engine": name,
            "engine_version": engine.get("engine_version"),
            "runtime_device": engine.get("runtime_device") or report.get("environment", {}).get("gpu"),
            "valid_pages": len(valid),
            "failed_pages": len(engine.get("pages", [])) - len(valid),
            "micro_cer": round(char_edits / chars, 6) if chars else None,
            "micro_wer": round(word_edits / words, 6) if words else None,
            "mean_latency_seconds": round(latency / len(valid), 3) if valid else None,
            "pages_per_minute": round(len(valid) * 60 / latency, 3) if latency else None,
            "initialization_seconds": engine.get("model_initialization_seconds"),
            "process_peak_rss_mb": report.get("environment", {}).get("process_peak_rss_mb"),
            "child_peak_rss_mb": report.get("environment", {}).get("child_peak_rss_mb"),
            "cuda_memory": engine.get("memory_telemetry", {}),
            "table_rows_expected": engine.get("aggregate", {}).get("table_rows_expected"),
            "table_rows_exact": engine.get("aggregate", {}).get("table_rows_exact"),
            "table_row_recall": engine.get("aggregate", {}).get("table_row_recall"),
        })
        if table_rows_by_page:
            matched_cells = expected_cells = 0
            for page in engine.get("pages", []):
                table_rows = table_rows_by_page.get(_page_identity(page), [])
                if not table_rows or page.get("cer") is None:
                    continue
                matched, expected = _table_cell_text_counts(table_rows, page.get("hypothesis_text", ""))
                matched_cells += matched
                expected_cells += expected
            comparisons[-1].update({
                "table_cells_expected": expected_cells,
                "table_cells_text_matched": matched_cells,
                "table_cell_text_recall": round(matched_cells / expected_cells, 6) if expected_cells else None,
                "table_cell_metric_scope": "cell text presence only; ignores row and column association",
            })

    return {
        "dataset": baseline.get("dataset"),
        "dataset_sha256": dataset_hash,
        "render_dpi": dpi,
        "paired_pages": [
            {"document_id": document, "page": page, "language": language,
             "source_pdf_sha256": reference_pages[(document, page, language)][0],
             "rendered_image_sha256": reference_pages[(document, page, language)][1]}
            for document, page, language in sorted(reference_pages)
        ],
        "engines": comparisons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--dataset", type=Path, help="Ground-truth dataset for complementary table cell-text recall")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
        dataset = json.loads(args.dataset.read_text(encoding="utf-8")) if args.dataset else None
        if dataset is not None:
            dataset_hash = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
            if any(report.get("dataset_sha256") != dataset_hash for report in reports):
                raise ValueError("Ground-truth dataset content does not match the OCR reports")
        result = compare_reports(reports, dataset)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
