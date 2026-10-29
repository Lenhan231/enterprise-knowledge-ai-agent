"""Source-grounded scanned table reconstruction specialist."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from string import Template
from typing import Literal

from PIL import Image
from pydantic import BaseModel, Field

from agents.codex_cli import run_codex_json

TABLE_DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tables", "uncertain_items"],
    "properties": {
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["region_id", "grid"],
                "properties": {
                    "region_id": {"type": "string"},
                    "grid": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                },
            },
        },
        "uncertain_items": {"type": "array", "items": {"type": "string"}},
    },
}
ORIENTATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["clockwise_degrees"],
    "properties": {"clockwise_degrees": {"type": "integer", "enum": [0, 90, 180, 270]}},
}


class DraftTable(BaseModel):
    region_id: str = Field(min_length=1)
    grid: list[list[str]]


class GeneratedTableDraft(BaseModel):
    tables: list[DraftTable]
    uncertain_items: list[str]


class PageOrientation(BaseModel):
    clockwise_degrees: Literal[0, 90, 180, 270]


def rotate_bbox(bbox: list[float], clockwise_degrees: int) -> list[float]:
    x1, y1, x2, y2 = bbox
    points = [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]
    if clockwise_degrees == 90:
        points = [(1 - y, x) for x, y in points]
    elif clockwise_degrees == 180:
        points = [(1 - x, 1 - y) for x, y in points]
    elif clockwise_degrees == 270:
        points = [(y, 1 - x) for x, y in points]
    return [min(x for x, _ in points), min(y for _, y in points),
            max(x for x, _ in points), max(y for _, y in points)]


def normalize_reversed_columns(draft: GeneratedTableDraft) -> None:
    """Correct the clear case where Codex puts a total column first and row labels last."""
    for table in draft.tables:
        grid = table.grid
        if len(grid) < 2 or not grid[0] or grid[0][-1].strip():
            continue
        first_header = grid[0][0].casefold()
        if not any(marker in first_header for marker in ("total", "tổng", "cộng", "sum")):
            continue
        body = [row for row in grid[1:] if row]
        if not body:
            continue
        numeric_first = sum(bool(re.fullmatch(r"[\s\d.,()%+\-/–—]+", row[0])) and any(c.isdigit() for c in row[0]) for row in body)
        text_last = sum(any(char.isalpha() for char in row[-1]) for row in body)
        if numeric_first * 2 >= len(body) and text_last * 2 >= len(body):
            table.grid = [row[::-1] for row in grid]


def validate_table_draft(draft: GeneratedTableDraft, table_regions: list[dict]) -> None:
    expected_ids = [region.get("region_id") for region in table_regions]
    returned_ids = [table.region_id for table in draft.tables]
    if len(set(returned_ids)) != len(returned_ids) or set(returned_ids) != set(expected_ids):
        raise ValueError("Codex must return one table grid for each existing table region")
    for table in draft.tables:
        if not table.grid or not table.grid[0] or any(
            len(row) != len(table.grid[0]) for row in table.grid
        ):
            raise ValueError(f"Codex returned an empty or non-rectangular grid for {table.region_id}")


def run_table_agent(
    image_bytes: bytes,
    table_regions: list[dict],
    instruction: str = "",
    existing_grids: list[dict] | None = None,
) -> tuple[GeneratedTableDraft, str]:
    if not table_regions:
        raise ValueError("At least one table layout region is required")
    regions = [
        {key: region.get(key) for key in ("region_id", "bbox_norm")}
        for region in table_regions
    ]
    with Image.open(io.BytesIO(image_bytes)) as source:
        page = source.convert("RGB")
    orientation, _ = run_codex_json(
        [("source-page.jpg", image_bytes)],
        "Inspect the scanned page and decide how to rotate it clockwise so its printed text is upright. "
        "Return 0 if already upright, otherwise 90, 180, or 270. Judge from text orientation, not page shape.",
        ORIENTATION_SCHEMA, "codex-table-orientation-", "orientation.json", PageOrientation,
    )
    rotation = orientation.clockwise_degrees
    if rotation:
        page = page.rotate(-rotation, expand=True)
    page_width, page_height = page.size
    for region in regions:
        region["bbox_norm"] = rotate_bbox(region["bbox_norm"], rotation)
    images = []
    for index, region in enumerate(regions, start=1):
        x1, y1, x2, y2 = region["bbox_norm"]
        pad_x, pad_y = round(page_width * 0.015), round(page_height * 0.015)
        left = max(0, round(x1 * page_width) - pad_x)
        top = max(0, round(y1 * page_height) - pad_y)
        right = min(page_width, round(x2 * page_width) + pad_x)
        bottom = min(page_height, round(y2 * page_height) + pad_y)
        crop = page.crop((left, top, right, bottom))
        buffer = io.BytesIO()
        crop.save(buffer, format="PNG", optimize=True)
        images.append((f"table-{index:02d}.png", buffer.getvalue()))
    prompt = Template(Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8")).substitute(
        regions_json=json.dumps(regions, ensure_ascii=False),
        rotation=rotation,
        user_instruction=instruction or "Regenerate each table grid from the source image.",
        existing_grids_json=json.dumps(existing_grids or [], ensure_ascii=False),
    )
    draft, model = run_codex_json(
        images, prompt, TABLE_DRAFT_SCHEMA, "codex-table-draft-", "tables.json", GeneratedTableDraft,
    )
    normalize_reversed_columns(draft)
    validate_table_draft(draft, table_regions)
    return draft, f"{model}; page rotated clockwise {rotation} degrees before table cropping"
