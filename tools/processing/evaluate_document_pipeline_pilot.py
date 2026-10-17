"""Score the shared OCR and table-anchor references for pilot pipeline outputs."""

from __future__ import annotations

import argparse
import html
import json
import re
import statistics
import unicodedata
import zipfile
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "artifacts/evaluation/document-pipelines/pilot-v1"
RESULTS = ROOT / "artifacts/evaluation/document-pipelines/results"
OCR_REFERENCE = ROOT / "artifacts/evaluation/ocr/layout-pipeline-kaggle/dataset/ocr_ground_truth.json"
TABLE_REFERENCE = ROOT / "artifacts/evaluation/ocr/layout-pipeline-kaggle/dataset/table_ground_truth.json"
TABLE_GRID_REFERENCE = PILOT / "table-reference-draft.json"
ENGINE_DIRS = {
    "docling": RESULTS / "docling/document-pipeline-pilot",
    "pp-structurev3": RESULTS / "pp-structurev3/document-pipeline-pilot",
    "mineru": RESULTS / "mineru-basic/document-pipeline-pilot",
}
ENGINE_CONFIG_FALLBACKS = {
    "docling": {"device": "CUDA", "ocr": "RapidOCR ONNX Runtime, vi", "table_structure": True},
}
OCR_PAGE_IDS = {
    "hpt-longhau-page1-cover-vi": "longhau-cover-p001",
    "hpt-longhau-page3-board-report-vi": "longhau-board-p003",
}
TABLE_PAGE_ID = "longhau-financials-p006"


def normalize_text(value: str) -> str:
    value = html.unescape(str(value or ""))
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.S)
    value = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", value)
    value = re.sub(r"(?m)^\s*\|?[\s:-]+\|[\s|:-]*$", " ", value)
    value = re.sub(r"\*\*(.*?)\*\*|__(.*?)__", lambda m: m.group(1) or m.group(2), value)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = unicodedata.normalize("NFC", value).casefold()
    return re.sub(r"\s+", " ", value).strip()


def edit_distance(left: list[str] | str, right: list[str] | str) -> int:
    previous = list(range(len(right) + 1))
    for i, left_item in enumerate(left, start=1):
        current = [i]
        for j, right_item in enumerate(right, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left_item != right_item)))
        previous = current
    return previous[-1]


def score_text(reference: str, hypothesis: str) -> dict:
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    ref_words, hyp_words = ref.split(), hyp.split()
    return {
        "reference_characters": len(ref),
        "reference_words": len(ref_words),
        "cer": edit_distance(ref, hyp) / len(ref) if ref else None,
        "wer": edit_distance(ref_words, hyp_words) / len(ref_words) if ref_words else None,
    }


def pp_text(page_id: str, root: Path) -> tuple[str, dict]:
    candidates = list((root / "raw_pages").glob(f"{page_id}-page-*.json"))
    markdown_path = root / "raw_pages" / f"{page_id}-page-001-markdown.json"
    if markdown_path.exists():
        markdown = json.loads(markdown_path.read_text(encoding="utf-8")).get("markdown_texts", "")
        if re.sub(r"<[^>]+>", "", str(markdown)).strip():
            return str(markdown), {"raw_files": len(candidates), "markdown_output": True}
    texts, counts = [], {}
    for path in candidates:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload = payload.get("res", payload) if isinstance(payload, dict) else payload
        blocks = payload.get("parsing_res_list", []) if isinstance(payload, dict) else []
        counts[path.name] = len(blocks)
        for block in blocks:
            content = block.get("block_content", "")
            if content:
                texts.append(str(content))
    return "\n".join(texts), {"raw_files": len(candidates), "markdown_output": False, "blocks_by_file": counts}


def mineru_text(page_id: str, root: Path) -> tuple[str, dict]:
    archives = [path for path in root.rglob("*.zip") if page_id in str(path)]
    if not archives:
        return "", {"error": f"MinerU output ZIP not found for {page_id}"}
    texts, markdown_files = [], []
    for archive in archives:
        with zipfile.ZipFile(archive) as bundle:
            name = next((name for name in bundle.namelist() if Path(name).name == "markdown.md"), None)
            if name:
                texts.append(bundle.read(name).decode("utf-8", errors="replace"))
                markdown_files.append(f"{archive.name}:{name}")
    return "\n".join(texts), {"archives": len(archives), "markdown_files": markdown_files}


def load_page_text(engine: str, page_id: str, root: Path) -> tuple[str, dict]:
    if engine == "docling":
        path = root / "raw_pages" / f"{page_id}.md"
        return (path.read_text(encoding="utf-8"), {"raw_markdown": path.exists()}) if path.exists() else ("", {"error": "Markdown file missing"})
    if engine == "pp-structurev3":
        return pp_text(page_id, root)
    return mineru_text(page_id, root)


def table_anchor_score(hypothesis: str, rows: list[dict]) -> dict:
    words = normalize_text(hypothesis).split()
    matched = 0
    for row in rows:
        cells = [row["label"], *row["values"]]
        cursor = 0
        for cell in cells:
            tokens = normalize_text(cell).split()
            found = next(
                (i for i in range(cursor, len(words) - len(tokens) + 1) if words[i : i + len(tokens)] == tokens),
                None,
            )
            if found is None:
                break
            cursor = found + len(tokens)
        else:
            matched += 1
    return {"exact_rows": matched, "expected_rows": len(rows), "row_recall": matched / len(rows) if rows else None}


class _TableGridParser(HTMLParser):
    """Read table rows and spans from HTML/Markdown table output."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[tuple[str, int, int]]] = []
        self.row: list[tuple[str, int, int]] | None = None
        self.cell: list[object] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs)
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = ["", int(attrs.get("rowspan") or 1), int(attrs.get("colspan") or 1)]

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell[0] = str(self.cell[0]) + data

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row.append((str(self.cell[0]).strip(), int(self.cell[1]), int(self.cell[2])))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def _expand_table_html(source: str) -> list[list[str]]:
    parser = _TableGridParser()
    parser.feed(source)
    matrix: list[list[str]] = []
    spans: dict[int, tuple[str, int]] = {}
    for cells in parser.rows:
        row: list[str] = []
        column = 0

        def fill_spans() -> None:
            nonlocal column
            while column in spans:
                value, remaining = spans.pop(column)
                row.append(value)
                if remaining > 1:
                    spans[column] = (value, remaining - 1)
                column += 1

        fill_spans()
        for value, row_span, col_span in cells:
            fill_spans()
            row.append(value)
            for _ in range(col_span - 1):
                row.append("")
            if row_span > 1:
                for offset in range(col_span):
                    spans[column + offset] = (value if offset == 0 else "", row_span - 1)
            column += col_span
        fill_spans()
        matrix.append(row)
    width = max((len(row) for row in matrix), default=0)
    return [row + [""] * (width - len(row)) for row in matrix]


def load_table_grid(engine: str, root: Path) -> list[list[str]]:
    if engine == "docling":
        path = root / "raw_pages" / f"{TABLE_PAGE_ID}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        cells = payload.get("tables", [{}])[0].get("data", {}).get("table_cells", [])
        row_count = max((cell["end_row_offset_idx"] for cell in cells), default=0)
        col_count = max((cell["end_col_offset_idx"] for cell in cells), default=0)
        matrix = [[""] * col_count for _ in range(row_count)]
        for cell in cells:
            matrix[cell["start_row_offset_idx"]][cell["start_col_offset_idx"]] = cell["text"]
        return matrix
    if engine == "pp-structurev3":
        path = root / "raw_pages" / f"{TABLE_PAGE_ID}-page-001.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        tables = [
            block.get("block_content", "")
            for block in payload.get("res", {}).get("parsing_res_list", [])
            if block.get("block_label") == "table" and block.get("block_content")
        ]
        return _expand_table_html(max(tables, key=len)) if tables else []
    archives = [path for path in root.rglob("*.zip") if TABLE_PAGE_ID in str(path)]
    if not archives:
        return []
    with zipfile.ZipFile(archives[0]) as archive:
        markdown = next((name for name in archive.namelist() if Path(name).name == "markdown.md"), None)
        if not markdown:
            return []
        return _expand_table_html(archive.read(markdown).decode("utf-8", errors="replace"))


def table_grid_score(predicted: list[list[str]], reference: dict) -> dict:
    expected_rows = reference["rows"]
    expected_codes = [row["cells"][0] for row in expected_rows]
    by_code = {
        row[0].strip(): row
        for row in predicted
        if row and row[0].strip() in set(expected_codes)
    }
    exact_cells = 0
    exact_numeric_cells = 0
    for expected in expected_rows:
        cells = expected["cells"]
        actual = by_code.get(cells[0], [])
        exact_cells += sum(
            normalize_text(actual[index] if index < len(actual) else "") == normalize_text(value)
            for index, value in enumerate(cells)
        )
        exact_numeric_cells += sum(
            normalize_text(actual[index] if index < len(actual) else "") == normalize_text(cells[index])
            for index in (3, 4)
        )
    row_matches = len(by_code)
    expected_cells = len(expected_rows) * len(reference["columns"])
    expected_numeric_cells = len(expected_rows) * 2
    return {
        "detected": bool(predicted),
        "predicted_grid_rows": len(predicted),
        "predicted_grid_columns": max((len(row) for row in predicted), default=0),
        "exact_row_key_matches": row_matches,
        "expected_row_keys": len(expected_rows),
        "row_key_recall": row_matches / len(expected_rows) if expected_rows else None,
        "row_key_aligned_exact_cells": exact_cells,
        "expected_cells": expected_cells,
        "row_key_aligned_cell_accuracy": exact_cells / expected_cells if expected_cells else None,
        "row_key_aligned_exact_numeric_cells": exact_numeric_cells,
        "expected_numeric_cells": expected_numeric_cells,
        "row_key_aligned_numeric_cell_accuracy": exact_numeric_cells / expected_numeric_cells if expected_numeric_cells else None,
        "alignment": "exact first-column row key; a missing row counts as all cells incorrect",
    }


def run(output: Path, ocr_reference: Path = OCR_REFERENCE, table_reference: Path = TABLE_REFERENCE) -> dict:
    pilot = json.loads((PILOT / "manifest.json").read_text(encoding="utf-8"))
    ocr_reference_data = json.loads(ocr_reference.read_text(encoding="utf-8"))
    full_refs = ocr_reference_data["pages"]
    table_reference_data = json.loads(table_reference.read_text(encoding="utf-8"))
    table_ref = table_reference_data["pages"][0]
    table_grid_ref = json.loads(TABLE_GRID_REFERENCE.read_text(encoding="utf-8"))["table"]
    engines = {}
    for engine, root in ENGINE_DIRS.items():
        meta_path = root / "run-metadata.json"
        if not meta_path.is_file():
            engines[engine] = {"status": "not_available", "output_directory": str(root.relative_to(ROOT))}
            continue
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        page_metrics = {}
        for ref in full_refs:
            page_id = OCR_PAGE_IDS.get(ref["id"])
            if not page_id:
                continue
            hypothesis, details = load_page_text(engine, page_id, root)
            page_metrics[page_id] = {
                **score_text(ref["reference_text"], hypothesis),
                "hypothesis_characters": len(normalize_text(hypothesis)),
                "extract_details": details,
            }
        page, _ = load_page_text(engine, TABLE_PAGE_ID, root)
        table = table_anchor_score(page, table_ref["table_rows"])
        table_grid = table_grid_score(load_table_grid(engine, root), table_grid_ref)
        run_pages = metadata.get("inference", {}).get("pages", [])
        times = sorted(
            row["seconds"] for row in run_pages if row.get("seconds") is not None and row.get("status") != "error"
        )
        p95 = statistics.quantiles(times, n=100, method="inclusive")[94] if len(times) > 1 else (times[0] if times else None)
        parent_rss = metadata.get("system", {}).get("peak_rss_mb")
        engines[engine] = {
            "status": "pilot_output_available",
            "package_versions": metadata.get("packages", {}),
            "engine_config": metadata.get("engine_config") or ENGINE_CONFIG_FALLBACKS.get(engine, {}),
            "page_count": metadata.get("page_count"),
            "successful_page_count": sum(row.get("status", "").endswith("SUCCESS") or row.get("status") == "ok" for row in run_pages),
            "failed_page_count": sum(row.get("status") == "error" for row in run_pages),
            "ocr_full_page_references": page_metrics,
            "table_anchor_reference": table,
            "table_grid_reference": table_grid,
            "median_page_seconds": statistics.median(times) if times else None,
            "p95_page_seconds": p95,
            "batch_seconds": metadata.get("inference", {}).get("batch_seconds_including_process_startup"),
            "peak_rss_mb": None if engine == "mineru" else parent_rss,
            "parent_process_peak_rss_mb": parent_rss if engine == "mineru" else None,
            "raw_output_directory": str(root.relative_to(ROOT)),
        }
    result = {
        "dataset_id": pilot["dataset_id"],
        "status": "pilot_only_not_for_model_selection",
        "reference_version": ocr_reference_data.get("reference_version", "existing-exploratory-reference"),
        "reference_provenance": ocr_reference_data.get("adjudication", "existing candidate references"),
        "normalization": "NFC, casefold, collapse whitespace; strip Markdown/HTML presentation syntax; retain punctuation and Vietnamese diacritics",
        "references": {"full_page_ocr": 2, "table_page": 1, "table_anchor_rows": len(table_ref["table_rows"]), "complete_table_grids": 1, "table_grid_reference_version": "assistant-adjudicated-pilot-v1", "table_grid_reference_status": "assistant_adjudicated_user_authorized", "layout_labels_reviewed": 0, "reading_order_pages_labeled": 0},
        "engines": engines,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS / "comparison.json")
    parser.add_argument("--ocr-reference", type=Path, default=OCR_REFERENCE)
    parser.add_argument("--table-reference", type=Path, default=TABLE_REFERENCE)
    args = parser.parse_args()
    result = run(args.output, args.ocr_reference, args.table_reference)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
