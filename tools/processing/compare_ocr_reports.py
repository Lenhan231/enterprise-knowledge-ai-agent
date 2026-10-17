#!/usr/bin/env python3
"""Compare OCR reports only when dataset and rendered inputs match exactly."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path


def _page_identity(row: dict) -> tuple:
    return (row.get("document_id"), row.get("page"), row.get("language"), row.get("id"))


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


def _table_row_indices(table_rows: list[dict], hypothesis: str) -> list[int]:
    tokens = _normalize(hypothesis).split()
    matched = []
    for index, row in enumerate(table_rows):
        cursor = 0
        for cell in (row["label"], *row["values"]):
            cell_tokens = _normalize(cell).split()
            found = next((
                offset for offset in range(cursor, len(tokens) - len(cell_tokens) + 1)
                if tokens[offset:offset + len(cell_tokens)] == cell_tokens
            ), None)
            if found is None:
                break
            cursor = found + len(cell_tokens)
        else:
            matched.append(index)
    return matched


def _edit_distance(left: Sequence[str], right: Sequence[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left_char != right_char)))
        previous = current
    return previous[-1]


def _score(reference: str, hypothesis: str) -> tuple[int, int, int, int]:
    reference_chars, hypothesis_chars = _normalize(reference), _normalize(hypothesis)
    reference_words, hypothesis_words = reference_chars.split(), hypothesis_chars.split()
    char_edits = _edit_distance(reference_chars, hypothesis_chars)
    word_edits = _edit_distance(reference_words, hypothesis_words)
    return len(reference_chars), len(reference_words), char_edits, word_edits


def compare_reports(
    reports: list[dict], dataset: dict | None = None, *,
    rescore_references: bool = False, dataset_sha256: str | None = None,
) -> dict:
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
    dataset_pages = {}
    if dataset is not None:
        dataset_pages = {_page_identity(page): page for page in dataset.get("pages", [])}
        baseline_rows = baseline["engines"][next(iter(baseline["engines"]))].get("pages", [])
        if not any(page.get("id") for page in baseline_rows):
            dataset_pages = {
                (*_page_identity(page)[:3], None): page
                for page in dataset.get("pages", [])
            }
        table_rows_by_page = {
            identity: page.get("table_rows", [])
            for identity, page in dataset_pages.items()
        }
    if rescore_references and (dataset is None or not dataset_sha256):
        raise ValueError("Reference rescoring requires a ground-truth dataset and its content hash")

    def input_pages(report: dict) -> dict:
        rows = next(iter(report.get("engines", {}).values())).get("pages", [])
        pages = {}
        for row in rows:
            identity = _page_identity(row)
            if None in identity[:3] or not row.get("source_pdf_sha256") or not row.get("rendered_image_sha256"):
                raise ValueError("Every OCR page must identify its document, page, language, PDF and rendered image hashes")
            if identity in pages:
                raise ValueError(f"Duplicate OCR page identity: {identity}")
            pages[identity] = (row["source_pdf_sha256"], row["rendered_image_sha256"])
        return pages

    reference_pages = input_pages(baseline)
    if not reference_pages:
        raise ValueError("OCR reports contain no page records")
    if rescore_references:
        if set(dataset_pages) != set(reference_pages):
            raise ValueError("Updated references must cover exactly the OCR report pages")
        for identity, page in dataset_pages.items():
            report_source, report_image = reference_pages[identity]
            if page.get("source_pdf_sha256") != report_source or page.get("rendered_image_sha256") != report_image:
                raise ValueError(f"Updated reference does not identify the same source/rendered page: {identity}")
            if not page.get("reference_text"):
                raise ValueError(f"Updated reference is missing full text: {identity}")

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
        settings = report.get("ocr_configuration", {})
        psm = settings.get("tesseract_page_segmentation_mode") if name == "tesseract" else None
        comparison_name = f"tesseract_psm{psm}" if psm is not None else name
        if comparison_name in names:
            raise ValueError(f"Duplicate OCR engine/configuration report: {comparison_name}")
        names.add(comparison_name)
        if input_pages(report) != reference_pages:
            raise ValueError(f"{name} report does not use the same source pages and rendered images")
        engine_pages = engine.get("pages", [])
        processed = [row for row in engine_pages if not row.get("error")]
        rescored = {}
        if rescore_references:
            for row in processed:
                identity = _page_identity(row)
                rescored[identity] = _score(
                    dataset_pages[identity]["reference_text"], row.get("hypothesis_text", "")
                )
        valid = [row for row in processed if rescore_references or (row.get("cer") is not None and row.get("wer") is not None)]
        chars = sum(rescored[_page_identity(row)][0] if rescore_references else row.get("reference_characters", 0) for row in valid)
        words = sum(rescored[_page_identity(row)][1] if rescore_references else row.get("reference_words", 0) for row in valid)
        char_edits = sum(rescored[_page_identity(row)][2] if rescore_references else row.get("character_edit_distance", 0) for row in valid)
        word_edits = sum(rescored[_page_identity(row)][3] if rescore_references else row.get("word_edit_distance", 0) for row in valid)
        latency = sum(row.get("latency_seconds", 0) for row in processed)
        by_language = {}
        languages = sorted({row.get("language") for row in engine_pages if row.get("language")})
        for language in languages:
            language_pages = [row for row in engine_pages if row.get("language") == language]
            language_processed = [row for row in language_pages if not row.get("error")]
            language_valid = [
                row for row in language_processed
                if rescore_references or (row.get("cer") is not None and row.get("wer") is not None)
            ]
            language_chars = sum(
                rescored[_page_identity(row)][0] if rescore_references else row.get("reference_characters", 0)
                for row in language_valid
            )
            language_words = sum(
                rescored[_page_identity(row)][1] if rescore_references else row.get("reference_words", 0)
                for row in language_valid
            )
            language_char_edits = sum(
                rescored[_page_identity(row)][2] if rescore_references else row.get("character_edit_distance", 0)
                for row in language_valid
            )
            language_word_edits = sum(
                rescored[_page_identity(row)][3] if rescore_references else row.get("word_edit_distance", 0)
                for row in language_valid
            )
            language_summary = {
                "valid_pages": len(language_valid),
                "ocr_pages": len(language_processed),
                "failed_pages": len(language_pages) - len(language_processed),
                "micro_cer": round(language_char_edits / language_chars, 6) if language_chars else None,
                "micro_wer": round(language_word_edits / language_words, 6) if language_words else None,
            }
            if table_rows_by_page:
                matched_cells = expected_cells = 0
                exact_rows = expected_rows = 0
                for row in language_processed:
                    table_rows = table_rows_by_page.get(_page_identity(row), [])
                    if not table_rows:
                        continue
                    matched, expected = _table_cell_text_counts(table_rows, row.get("hypothesis_text", ""))
                    matched_cells += matched
                    expected_cells += expected
                    exact_rows += len(_table_row_indices(table_rows, row.get("hypothesis_text", "")))
                    expected_rows += len(table_rows)
                language_summary.update({
                    "table_rows_expected": expected_rows,
                    "table_rows_exact": exact_rows,
                    "table_row_recall": round(exact_rows / expected_rows, 6) if expected_rows else None,
                    "table_cells_expected": expected_cells,
                    "table_cells_text_matched": matched_cells,
                    "table_cell_text_recall": round(matched_cells / expected_cells, 6) if expected_cells else None,
                })
            by_language[language] = language_summary
        comparisons.append({
            "engine": comparison_name,
            "base_engine": name,
            "configuration": settings,
            "engine_version": engine.get("engine_version"),
            "runtime_device": engine.get("runtime_device") or report.get("environment", {}).get("gpu"),
            "valid_pages": len(valid),
            "ocr_pages": len(processed),
            "failed_pages": len(engine_pages) - len(processed),
            "micro_cer": round(char_edits / chars, 6) if chars else None,
            "micro_wer": round(word_edits / words, 6) if words else None,
            "mean_latency_seconds": round(latency / len(processed), 3) if processed else None,
            "pages_per_minute": round(len(processed) * 60 / latency, 3) if latency else None,
            "initialization_seconds": engine.get("model_initialization_seconds"),
            "process_peak_rss_mb": report.get("environment", {}).get("process_peak_rss_mb"),
            "child_peak_rss_mb": report.get("environment", {}).get("child_peak_rss_mb"),
            "cuda_memory": engine.get("memory_telemetry", {}),
            "by_language": by_language,
            "table_rows_expected": engine.get("aggregate", {}).get("table_rows_expected"),
            "table_rows_exact": engine.get("aggregate", {}).get("table_rows_exact"),
            "table_row_recall": engine.get("aggregate", {}).get("table_row_recall"),
        })
        if table_rows_by_page:
            matched_cells = expected_cells = 0
            exact_rows = expected_rows = 0
            for page in engine.get("pages", []):
                table_rows = table_rows_by_page.get(_page_identity(page), [])
                if not table_rows or page.get("error"):
                    continue
                hypothesis = page.get("hypothesis_text", "")
                matched, expected = _table_cell_text_counts(table_rows, hypothesis)
                matched_cells += matched
                expected_cells += expected
                exact_rows += len(_table_row_indices(table_rows, hypothesis))
                expected_rows += len(table_rows)
            comparisons[-1].update({
                "table_cells_expected": expected_cells,
                "table_cells_text_matched": matched_cells,
                "table_cell_text_recall": round(matched_cells / expected_cells, 6) if expected_cells else None,
                "table_cell_metric_scope": "cell text presence only; ignores row and column association",
                "table_rows_expected_from_dataset": expected_rows,
                "table_rows_exact_from_dataset": exact_rows,
                "table_row_recall_from_dataset": round(exact_rows / expected_rows, 6) if expected_rows else None,
            })

    return {
        "dataset": dataset.get("dataset_id", baseline.get("dataset")) if rescore_references else baseline.get("dataset"),
        "dataset_sha256": dataset_sha256 if rescore_references else dataset_hash,
        "source_ocr_dataset_sha256": dataset_hash if rescore_references else None,
        "reference_rescored": rescore_references,
        "render_dpi": dpi,
        "paired_pages": [
            {"id": page_id, "document_id": document, "page": page, "language": language,
             "source_pdf_sha256": reference_pages[(document, page, language, page_id)][0],
             "rendered_image_sha256": reference_pages[(document, page, language, page_id)][1]}
            for document, page, language, page_id in sorted(
                reference_pages,
                key=lambda item: (item[0], item[1], item[2], item[3] or ""),
            )
        ],
        "engines": comparisons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--dataset", type=Path, help="Ground-truth dataset for complementary table cell-text recall")
    parser.add_argument("--rescore-references", action="store_true", help="Rescore cached OCR text against updated references for the same source/rendered pages")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
        dataset = json.loads(args.dataset.read_text(encoding="utf-8")) if args.dataset else None
        dataset_hash = hashlib.sha256(args.dataset.read_bytes()).hexdigest() if dataset is not None else None
        if dataset is not None and not args.rescore_references:
            if any(report.get("dataset_sha256") != dataset_hash for report in reports):
                raise ValueError("Ground-truth dataset content does not match the OCR reports")
        result = compare_reports(reports, dataset, rescore_references=args.rescore_references, dataset_sha256=dataset_hash)
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
