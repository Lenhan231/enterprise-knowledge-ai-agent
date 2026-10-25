"""Validate owner-reviewed annotations and refresh the active track references."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
TRACKS = ("ocr", "layout", "table", "end-to-end")
LABELS = {"title", "title_table", "text", "table", "figure", "seal"}


def _source_exists(page: dict) -> bool:
    source = page.get("source_image")
    if not isinstance(source, str) or not source:
        return False
    path = (DATA_DIR / source).resolve()
    return path.is_relative_to(DATA_DIR.resolve()) and path.is_file()


def _valid_regions(page: dict) -> bool:
    regions = page.get("layout_regions")
    if not isinstance(regions, list) or not regions:
        return False
    seen = set()
    for region in regions:
        if not isinstance(region, dict) or region.get("label") not in LABELS:
            return False
        region_id = region.get("region_id")
        box = region.get("bbox_norm")
        if not isinstance(region_id, str) or not region_id or region_id in seen:
            return False
        if not isinstance(box, list) or len(box) != 4:
            return False
        try:
            x1, y1, x2, y2 = map(float, box)
        except (TypeError, ValueError):
            return False
        if not all(map(math.isfinite, (x1, y1, x2, y2))):
            return False
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            return False
        seen.add(region_id)
    return True


def _table_drafts(page: dict) -> list[dict]:
    drafts = page.get("table_reference_drafts") or []
    if not drafts and isinstance(page.get("table_reference_draft"), dict):
        drafts = [page["table_reference_draft"]]
    return drafts if isinstance(drafts, list) else []


def _valid_grid(grid: object) -> bool:
    if not isinstance(grid, list) or not grid or not all(isinstance(row, list) and row for row in grid):
        return False
    width = len(grid[0])
    return width > 0 and all(len(row) == width and all(cell is not None for cell in row) for row in grid)


def _common(page: dict) -> dict:
    return {
        "reference_id": f"{page.get('document_id', 'PAGE')}-p{page.get('source_page_number', 1)}",
        "document_id": page.get("document_id"),
        "source_page_number_1based": int(page.get("source_page_number", 1)),
        "source_image": page.get("source_image"),
        "source_image_sha256": page.get("source_image_sha256"),
        "reference_status": "owner_reviewed_against_original_source",
        "owner_reviewed_at": page.get("owner_reviewed_at"),
    }


def build_tracks(reviews: list[dict]) -> tuple[dict[str, list[dict]], dict]:
    reviewed_at = datetime.now(timezone.utc).isoformat()
    records = {track: [] for track in TRACKS}
    for row in reviews:
        if row.get("annotation_status") != "owner_reviewed":
            continue
        page = row.get("page_data") or {}
        common = _common(page)
        source_ok = _source_exists(page)
        transcript = str(page.get("ocr_reference_draft") or "").strip()
        regions_ok = _valid_regions(page)
        regions = page.get("layout_regions") if regions_ok else []
        table_regions = [r for r in regions if r.get("label") == "table"]
        if source_ok and transcript:
            records["ocr"].append({**common, "ocr_reference_text": transcript})
        if source_ok and regions_ok:
            records["layout"].append({
                **common,
                "coordinate_system": "normalized_top_left_0_1",
                "regions": regions,
                "reading_order": page.get("reading_order", []),
            })

        table_records = []
        for index, table in enumerate(_table_drafts(page), start=1):
            if not isinstance(table, dict) or not _valid_grid(table.get("grid")):
                continue
            region_id = table.get("region_id")
            region = next((r for r in table_regions if r.get("region_id") == region_id), None)
            if region is None and len(table_regions) == 1:
                region = table_regions[0]
            if not source_ok or region is None:
                continue
            record = {
                **common,
                "reference_id": f"{common['reference_id']}-t{index}",
                "table_index_1based": index,
                "table_name": str(table.get("table_name") or "").strip(),
                "table_region_id": region["region_id"],
                "table_bbox_norm": region["bbox_norm"],
                "cell_grid": table["grid"],
                "row_count": len(table["grid"]),
                "column_count": len(table["grid"][0]),
            }
            table_records.append(record)
            records["table"].append(record)

        if source_ok and transcript and regions_ok and table_records:
            records["end-to-end"].append({
                **common,
                "ocr_reference_text": transcript,
                "layout_regions": regions,
                "reading_order": page.get("reading_order", []),
                "table_references": [
                    {
                        "reference_id": table["reference_id"],
                        "table_name": table["table_name"],
                        "table_region_id": table["table_region_id"],
                        "table_bbox_norm": table["table_bbox_norm"],
                        "cell_grid": table["cell_grid"],
                    }
                    for table in table_records
                ],
            })

    summary = {"generated_at": reviewed_at, "track_record_counts": {track: len(rows) for track, rows in records.items()}}
    return records, summary


def write_tracks(reviews: list[dict]) -> dict:
    records, summary = build_tracks(reviews)
    root = DATA_DIR
    for track, rows in records.items():
        directory = root / track
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "reference.jsonl"
        temporary = path.with_suffix(".jsonl.tmp")
        temporary.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    return summary["track_record_counts"]


def main() -> None:
    state = json.loads((DATA_DIR / "local-review-state.json").read_text(encoding="utf-8"))
    print(json.dumps(write_tracks(state.get("reviews", [])), ensure_ascii=False))


if __name__ == "__main__":
    main()
