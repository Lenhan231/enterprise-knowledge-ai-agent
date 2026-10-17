"""Score pipeline table grids against the assistant-adjudicated crop set."""

from __future__ import annotations

import argparse
import html
import json
import re
import statistics
import zipfile
from pathlib import Path

from evaluate_document_pipeline_pilot import _expand_table_html, normalize_text

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "artifacts/evaluation/document-pipelines/tables/reference"
RESULTS = ROOT / "artifacts/evaluation/document-pipelines/results/table-150-v1"


def markdown_tables(source: str) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in source.splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            if current:
                tables.append(current)
                current = []
            continue
        cells = [html.unescape(cell.strip()).replace("<br>", " ") for cell in line[1:-1].split("|")]
        if cells and all(re.fullmatch(r":?-{2,}:?", cell.replace(" ", "")) for cell in cells):
            continue
        current.append(cells)
    if current:
        tables.append(current)
    return tables


def docling_grid(payload: dict) -> list[list[str]]:
    grids = []
    for table in payload.get("tables", []):
        data = table.get("data", {})
        rows, columns = int(data.get("num_rows", 0)), int(data.get("num_cols", 0))
        grid = [[""] * columns for _ in range(rows)]
        for cell in data.get("table_cells", []):
            row = int(cell.get("start_row_offset_idx", 0))
            column = int(cell.get("start_col_offset_idx", 0))
            if row < rows and column < columns:
                grid[row][column] = str(cell.get("text", "")).strip()
        if any(any(value for value in row) for row in grid):
            grids.append(grid)
    return max(grids, key=lambda grid: sum(bool(cell) for row in grid for cell in row), default=[])


def extract_grid(engine: str, sample_id: str, root: Path, archives: list[Path]) -> tuple[list[list[str]], dict]:
    if engine == "pp-structurev3":
        path = root / "raw_pages" / f"{sample_id}-page-001.json"
        if not path.exists():
            return [], {"output_found": False}
        payload = json.loads(path.read_text(encoding="utf-8"))
        blocks = payload.get("res", {}).get("parsing_res_list", [])
        tables = [_expand_table_html(str(block.get("block_content", ""))) for block in blocks if block.get("block_label") == "table"]
        grid = max(tables, key=lambda value: sum(bool(cell) for row in value for cell in row), default=[])
        return grid, {"output_found": True, "predicted_table_count": len(tables)}
    if engine == "docling":
        paths = (
            root / "raw_pages" / f"{sample_id}-page-001.json",
            root / "raw_pages" / f"{sample_id}.json",
        )
        path = next((candidate for candidate in paths if candidate.exists()), None)
        if path is None:
            return [], {"output_found": False}
        return docling_grid(json.loads(path.read_text(encoding="utf-8"))), {"output_found": True}

    matches = [path for path in archives if sample_id in str(path)]
    if not matches:
        return [], {"output_found": False}
    tables = []
    for archive_path in matches:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                markdown = next((name for name in archive.namelist() if Path(name).name == "markdown.md"), None)
                if markdown:
                    source = archive.read(markdown).decode("utf-8", errors="replace")
                    html_grid = _expand_table_html(source)
                    if html_grid:
                        tables.append(html_grid)
                    tables.extend(markdown_tables(source))
        except zipfile.BadZipFile:
            continue
    return max(tables, key=lambda value: sum(bool(cell) for row in value for cell in row), default=[]), {"output_found": True}


def score_grid(reference: list[list[str]], prediction: list[list[str]]) -> dict:
    ref_rows = len(reference)
    ref_columns = max((len(row) for row in reference), default=0)
    pred_rows = len(prediction)
    pred_columns = max((len(row) for row in prediction), default=0)
    rows, columns = max(ref_rows, pred_rows), max(ref_columns, pred_columns)
    matches = total = 0
    for row_index in range(rows):
        for column_index in range(columns):
            expected = reference[row_index][column_index] if row_index < ref_rows and column_index < len(reference[row_index]) else ""
            actual = prediction[row_index][column_index] if row_index < pred_rows and column_index < len(prediction[row_index]) else ""
            matches += bool(prediction) and normalize_text(expected) == normalize_text(actual)
            total += 1
    return {
        "reference_rows": ref_rows,
        "reference_columns": ref_columns,
        "predicted_rows": pred_rows,
        "predicted_columns": pred_columns,
        "cell_matches": matches,
        "cell_positions_scored": total,
        "cell_accuracy": matches / total if total else None,
        "shape_exact": ref_rows == pred_rows and ref_columns == pred_columns,
        "predicted_table_found": bool(prediction),
        "exact_grid": ref_rows == pred_rows and ref_columns == pred_columns and matches == total,
        "absolute_row_count_error": abs(ref_rows - pred_rows),
        "absolute_column_count_error": abs(ref_columns - pred_columns),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pp-root", type=Path, default=RESULTS / "pp-structurev3/table-150-v1")
    parser.add_argument("--mineru-root", type=Path, default=RESULTS / "mineru-basic/table-150-v1")
    parser.add_argument("--docling-root", type=Path, default=RESULTS / "docling/table-150-v1")
    parser.add_argument("--output", type=Path, default=RESULTS / "table-comparison.json")
    parser.add_argument("--include-locked-test", action="store_true")
    args = parser.parse_args()
    roots = {"pp-structurev3": args.pp_root, "mineru-basic": args.mineru_root, "docling": args.docling_root}
    archives = {name: list((root / "mineru-output").rglob("*.zip")) if (root / "mineru-output").exists() else list(root.rglob("*.zip")) for name, root in roots.items()}
    refs = [json.loads(line) for line in (DATASET / "reference.jsonl").read_text(encoding="utf-8").splitlines()]
    refs = [row for row in refs if args.include_locked_test or row["split"] != "locked_test"]
    items = []
    for ref in refs:
        item = {"reference_id": ref["reference_id"], "candidate_id": ref["candidate_id"], "issuer": ref["issuer"], "split": ref["split"], "engines": {}}
        for engine, root in roots.items():
            parser_engine = "mineru-basic" if engine == "mineru-basic" else engine
            prediction, metadata = extract_grid(parser_engine, ref["reference_id"], root, archives[engine])
            metrics = score_grid(ref["cell_grid"], prediction)
            if not metadata.get("output_found"):
                metrics = {**metrics, "cell_accuracy": None, "exact_grid": False}
            item["engines"][engine] = {**metrics, **metadata}
        items.append(item)

    def summarize(engine: str, selected_items: list[dict]) -> dict:
        available = [item["engines"][engine] for item in selected_items if item["engines"][engine]["cell_accuracy"] is not None]
        return {
            "sample_count": len(selected_items),
            "outputs_found": sum(item["engines"][engine].get("output_found", False) for item in selected_items),
            "predicted_tables_found": sum(row["predicted_table_found"] for row in available),
            "tables_scored": len(available),
            "micro_cell_accuracy": sum(row["cell_matches"] for row in available) / sum(row["cell_positions_scored"] for row in available) if available else None,
            "exact_grid_rate": statistics.mean(row["exact_grid"] for row in available) if available else None,
            "shape_exact_rate": statistics.mean(row["shape_exact"] for row in available) if available else None,
            "mean_absolute_row_count_error": statistics.mean(row["absolute_row_count_error"] for row in available) if available else None,
            "mean_absolute_column_count_error": statistics.mean(row["absolute_column_count_error"] for row in available) if available else None,
        }

    summary = {}
    for engine in roots:
        summary[engine] = summarize(engine, items)
        summary[engine]["by_split"] = {
            split: summarize(engine, [item for item in items if item["split"] == split])
            for split in sorted({item["split"] for item in items})
        }
    report = {
        "status": "complete" if all(value["outputs_found"] == len(items) for value in summary.values()) else "incomplete_run",
        "dataset_id": "vietnam-enterprise-table-reference-v1",
        "split_scored": "all" if args.include_locked_test else "development_and_validation_only",
        "label_provenance": "Assistant-adjudicated crop extents; source-PDF cell grids; cell text and merged spans are not independently human-reviewed.",
        "scoring": "Unicode/whitespace normalized exact cell-string accuracy; predictions and references are aligned by row/column index. Extra/missing cells are errors. TEDS/TEDS-Struct are not reported.",
        "results": summary,
        "items": items,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "results": summary, "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
