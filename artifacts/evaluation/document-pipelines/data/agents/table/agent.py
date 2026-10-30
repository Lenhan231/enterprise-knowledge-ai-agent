"""Source-grounded scanned table reconstruction specialist."""

from __future__ import annotations

import io
import json
from pathlib import Path
from string import Template

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


class DraftTable(BaseModel):
    region_id: str = Field(min_length=1)
    grid: list[list[str]]


class GeneratedTableDraft(BaseModel):
    tables: list[DraftTable]
    uncertain_items: list[str]


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
    image_bytes: bytes, table_regions: list[dict]
) -> tuple[GeneratedTableDraft, str]:
    if not table_regions:
        raise ValueError("At least one table layout region is required")
    regions = [
        {key: region.get(key) for key in ("region_id", "bbox_norm")}
        for region in table_regions
    ]
    with Image.open(io.BytesIO(image_bytes)) as source:
        page = source.convert("RGB")
        page_width, page_height = page.size
        images = []
        for index, region in enumerate(table_regions, start=1):
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
        regions_json=json.dumps(regions, ensure_ascii=False)
    )
    draft, model = run_codex_json(
        images, prompt, TABLE_DRAFT_SCHEMA, "codex-table-draft-", "tables.json", GeneratedTableDraft,
    )
    validate_table_draft(draft, table_regions)
    return draft, model
