"""Score reviewed locked-test table HTML with GriTS-Top and GriTS-Con."""

from __future__ import annotations

import argparse
import html
import json
import zipfile
from pathlib import Path
from typing import Any

from grits import GritsEvaluator, html_to_grids

from evaluate_document_pipeline_tables import markdown_tables

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/evaluation/document-pipelines"
REFERENCE = BASE / "tables/reference/reference.jsonl"
RESULTS = BASE / "results/table-150-v1"
ENGINE_ROOTS = {
    "pp-structurev3": RESULTS / "pp-structurev3/table-150-v1",
    "mineru-basic": RESULTS / "mineru-basic/table-150-v1",
    "docling": RESULTS / "docling/table-150-v1",
}


def matrix_to_html(rows: list[list[str]]) -> str:
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<table>{body}</table>" if rows else ""


def docling_tables(payload: dict[str, Any]) -> list[str]:
    rendered = []
    for table in payload.get("tables", []):
        data = table.get("data", {})
        row_count = int(data.get("num_rows", 0))
        col_count = int(data.get("num_cols", 0))
        cells: dict[tuple[int, int], dict[str, Any]] = {}
        for cell in data.get("table_cells", []):
            row = int(cell.get("start_row_offset_idx", 0))
            column = int(cell.get("start_col_offset_idx", 0))
            if 0 <= row < row_count and 0 <= column < col_count:
                cells[(row, column)] = cell

        occupied: set[tuple[int, int]] = set()
        table_rows = []
        for row in range(row_count):
            output_cells = []
            for column in range(col_count):
                if (row, column) in occupied:
                    continue
                cell = cells.get((row, column))
                if cell is None:
                    output_cells.append("<td></td>")
                    continue
                row_span = max(1, int(cell.get("row_span", 1)))
                col_span = max(1, int(cell.get("col_span", 1)))
                for covered_row in range(row, min(row + row_span, row_count)):
                    for covered_column in range(column, min(column + col_span, col_count)):
                        if (covered_row, covered_column) != (row, column):
                            occupied.add((covered_row, covered_column))
                tag = "th" if cell.get("column_header") else "td"
                attrs = "" if row_span == col_span == 1 else f' rowspan="{row_span}" colspan="{col_span}"'
                output_cells.append(f"<{tag}{attrs}>{html.escape(str(cell.get('text', '')))}</{tag}>")
            table_rows.append("<tr>" + "".join(output_cells) + "</tr>")
        if table_rows:
            rendered.append("<table>" + "".join(table_rows) + "</table>")
    return rendered


def choose_largest(tables: list[str]) -> str | None:
    valid = []
    for table in tables:
        try:
            grids = html_to_grids(table)
        except (ValueError, TypeError, IndexError):
            continue
        if grids.get("con"):
            cell_count = sum(len(row) for row in grids["con"])
            valid.append((cell_count, len(table), table))
    return max(valid, default=(0, 0, None))[2]


def predicted_html(engine: str, table_id: str, root: Path) -> tuple[str | None, str]:
    if engine == "pp-structurev3":
        path = root / "raw_pages" / f"{table_id}-page-001.json"
        if not path.exists():
            return None, "raw_output_missing"
        payload = json.loads(path.read_text(encoding="utf-8"))
        blocks = payload.get("res", {}).get("parsing_res_list", [])
        tables = [
            str(block.get("block_content", ""))
            for block in blocks
            if block.get("block_label") == "table" and block.get("block_content")
        ]
        chosen = choose_largest(tables)
        return chosen, "pp_table_html" if chosen else "no_table_block"

    if engine == "docling":
        paths = [root / "raw_pages" / f"{table_id}.json", root / "raw_pages" / f"{table_id}-page-001.json"]
        path = next((candidate for candidate in paths if candidate.exists()), None)
        if path is None:
            return None, "raw_output_missing"
        chosen = choose_largest(docling_tables(json.loads(path.read_text(encoding="utf-8"))))
        return chosen, "docling_table_cells" if chosen else "no_table"

    archives = sorted((root / "mineru-output" / table_id).glob("*.zip"))
    if not archives:
        return None, "raw_output_missing"
    tables: list[str] = []
    for archive_path in archives:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                markdown = next((name for name in archive.namelist() if Path(name).name == "markdown.md"), None)
                if markdown:
                    source = archive.read(markdown).decode("utf-8", errors="replace")
                    tables.extend(markdown_tables(source))
                    # Preserve native HTML table spans when MinerU emitted HTML.
                    if "<table" in source.casefold():
                        tables.append(source)
        except zipfile.BadZipFile:
            continue
    chosen = choose_largest([*tables, *[matrix_to_html(table) for table in tables if table and isinstance(table[0], list)]])
    return chosen, "mineru_markdown_or_html" if chosen else "no_table"


def load_reviewed_items(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("task") != "tables" or payload.get("dataset_id") != "vietnam-enterprise-table-reference-v1":
        raise ValueError("Expected the exported table review JSON for vietnam-enterprise-table-reference-v1")
    items = payload.get("reviewed_items", [])
    reference_rows = [
        json.loads(line)
        for line in REFERENCE.read_text(encoding="utf-8").splitlines()
        if line
    ]
    expected = {
        row["reference_id"] for row in reference_rows if row.get("split") == "locked_test"
    }
    by_id = {item.get("id"): item for item in items}
    if set(by_id) != expected or len(items) != len(expected):
        raise ValueError(f"Review export must contain exactly the {len(expected)} locked-test tables")
    for table_id, item in by_id.items():
        if not item.get("reviewed") or not str(item.get("reviewer", "")).strip():
            raise ValueError(f"Table {table_id} is not marked reviewed with a reviewer ID")
        table_html = str(item.get("reviewed_html", ""))
        if "<table" not in table_html.casefold() or not html_to_grids(table_html).get("con"):
            raise ValueError(f"Table {table_id} has invalid reviewed HTML")
    return [by_id[table_id] for table_id in sorted(expected)]


def score(reviewed_path: Path, output_path: Path) -> dict[str, Any]:
    reviewed_items = load_reviewed_items(reviewed_path)
    evaluators = {engine: GritsEvaluator(metrics=["top", "con"]) for engine in ENGINE_ROOTS}
    item_results = []
    for item in reviewed_items:
        row = {
            "reference_id": item["id"],
            "split": item.get("split"),
            "reviewer": item["reviewer"],
            "engines": {},
        }
        for engine, root in ENGINE_ROOTS.items():
            prediction, source = predicted_html(engine, item["id"], root)
            predictions = [prediction] if prediction else []
            evaluators[engine].eval_htmls([item["reviewed_html"]], predictions)
            one = GritsEvaluator(metrics=["top", "con"])
            one.eval_htmls([item["reviewed_html"]], predictions)
            row["engines"][engine] = {
                **one.compute_grits(),
                "prediction_found": prediction is not None,
                "prediction_source": source,
            }
        item_results.append(row)

    summary = {engine: evaluator.compute_grits() for engine, evaluator in evaluators.items()}
    report = {
        "status": "complete",
        "dataset_id": "vietnam-enterprise-table-reference-v1",
        "split_scored": "locked_test_retrospective",
        "reference_provenance": "prediction-blind human-reviewed HTML export; see per-item reviewer IDs",
        "metric": "GriTS-Top and GriTS-Con; official GriTS micro aggregation",
        "package": "grits-metric==0.6.1",
        "pipeline_summaries": summary,
        "prediction_coverage": {
            engine: {
                "tables_with_prediction": sum(
                    item["engines"][engine]["prediction_found"] for item in item_results
                ),
                "reference_tables": len(item_results),
            }
            for engine in ENGINE_ROOTS
        },
        "items": item_results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite GriTS report: {output_path}")
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-reference", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS / "grits-locked-test-v1.json",
    )
    args = parser.parse_args()
    report = score(args.reviewed_reference, args.output)
    print(json.dumps({"status": report["status"], "pipeline_summaries": report["pipeline_summaries"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
