"""Full-page OCR, layout, and table-draft specialist."""

from __future__ import annotations

import json
import math
from pathlib import Path
from string import Template
from typing import Literal

from pydantic import BaseModel, Field

from agents.codex_cli import run_codex_json

PAGE_DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ocr_text", "regions", "reading_order", "tables", "uncertain_items"],
    "properties": {
        "ocr_text": {"type": "string"},
        "regions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["region_id", "label", "bbox_norm"],
                "properties": {
                    "region_id": {"type": "string"},
                    "label": {"type": "string", "enum": ["title", "text", "table", "figure"]},
                    "bbox_norm": {
                        "type": "array", "minItems": 4, "maxItems": 4,
                        "items": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
        },
        "reading_order": {"type": "array", "items": {"type": "string"}},
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["region_id", "table_name", "grid"],
                "properties": {
                    "region_id": {"type": "string"},
                    "table_name": {"type": "string", "maxLength": 200},
                    "grid": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                },
            },
        },
        "uncertain_items": {"type": "array", "items": {"type": "string"}},
    },
}


class DraftRegion(BaseModel):
    region_id: str = Field(min_length=1)
    label: Literal["title", "text", "table", "figure"]
    bbox_norm: list[float] = Field(min_length=4, max_length=4)


class DraftTable(BaseModel):
    region_id: str = Field(min_length=1)
    table_name: str = Field(default="", max_length=200)
    grid: list[list[str]]


class GeneratedPageDraft(BaseModel):
    ocr_text: str
    regions: list[DraftRegion]
    reading_order: list[str]
    tables: list[DraftTable]
    uncertain_items: list[str]


def validate_page_draft(draft: GeneratedPageDraft) -> None:
    regions = {region.region_id: region for region in draft.regions}
    if len(regions) != len(draft.regions):
        raise ValueError("Codex returned duplicate layout region IDs")
    for region in draft.regions:
        x1, y1, x2, y2 = region.bbox_norm
        if not all(map(math.isfinite, region.bbox_norm)):
            raise ValueError("Codex returned a non-finite region coordinate")
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError(
                "Codex returned an invalid normalized region box "
                f"for {region.region_id}: {region.bbox_norm}; expected 0 <= x1 < x2 <= 1 "
                "and 0 <= y1 < y2 <= 1"
            )
    if len(set(draft.reading_order)) != len(draft.reading_order) or any(
        region_id not in regions for region_id in draft.reading_order
    ):
        raise ValueError("Codex returned reading order IDs that do not match the layout regions")
    table_region_ids = {region.region_id for region in draft.regions if region.label == "table"}
    seen_tables: set[str] = set()
    for table in draft.tables:
        if table.region_id not in table_region_ids or table.region_id in seen_tables:
            raise ValueError("Codex table grid region IDs must uniquely match table regions")
        if not table.grid or not table.grid[0] or any(len(row) != len(table.grid[0]) for row in table.grid):
            raise ValueError("Codex returned an empty or non-rectangular table grid")
        seen_tables.add(table.region_id)


def run_page_draft_agent(image_bytes: bytes) -> tuple[GeneratedPageDraft, str]:
    prompt = Template(Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8")).substitute()
    draft, model = run_codex_json(
        [("source-page.jpg", image_bytes)], prompt, PAGE_DRAFT_SCHEMA,
        "codex-page-draft-", "page-draft.json", GeneratedPageDraft,
    )
    validate_page_draft(draft)
    return draft, model
