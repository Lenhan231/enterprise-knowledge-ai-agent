"""Codex specialist for refining existing page layout boxes."""

from __future__ import annotations

import colorsys
import io
import json
import math
from pathlib import Path
from string import Template
from typing import Literal

from PIL import Image, ImageDraw
from pydantic import BaseModel, Field

from agents.codex_cli import run_codex_json

BBOX_DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["regions"],
    "properties": {
        "regions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["region_id", "bbox_norm"],
                "properties": {
                    "region_id": {"type": "string"},
                    "bbox_norm": {
                        "type": "array",
                        "minItems": 4,
                        "maxItems": 4,
                        "items": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
        },
    },
}
ORIENTATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["clockwise_degrees"],
    "properties": {"clockwise_degrees": {"type": "integer", "enum": [0, 90, 180, 270]}},
}


class DraftBBox(BaseModel):
    region_id: str = Field(min_length=1)
    bbox_norm: list[float] = Field(min_length=4, max_length=4)


class GeneratedBBoxDraft(BaseModel):
    regions: list[DraftBBox]


class PageOrientation(BaseModel):
    clockwise_degrees: Literal[0, 90, 180, 270]


def bbox_overlay_color(index: int) -> tuple[int, int, int]:
    hue = (index * 0.61803398875) % 1.0
    return tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, 0.88, 0.92))


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


def prepare_bbox_reference_image(image: Image.Image, regions: list[dict]) -> bytes:
    image = image.copy()
    draw = ImageDraw.Draw(image)
    width, height = image.size
    line_width = max(2, round(min(width, height) / 700))

    for index, region in enumerate(regions):
        x1, y1, x2, y2 = region["bbox_norm"]
        box = (
            max(0, min(width - 1, round(x1 * width))),
            max(0, min(height - 1, round(y1 * height))),
            max(0, min(width - 1, round(x2 * width))),
            max(0, min(height - 1, round(y2 * height))),
        )
        draw.rectangle(box, outline=bbox_overlay_color(index), width=line_width)

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=94)
    return output.getvalue()


def validate_bbox_draft(draft: GeneratedBBoxDraft, existing_regions: list[dict]) -> None:
    expected_ids = [region.get("region_id") for region in existing_regions]
    returned_ids = [region.region_id for region in draft.regions]
    if len(set(returned_ids)) != len(returned_ids) or set(returned_ids) != set(expected_ids):
        raise ValueError("Codex bbox draft must return each existing region_id exactly once")
    for region in draft.regions:
        x1, y1, x2, y2 = region.bbox_norm
        if not all(math.isfinite(value) for value in region.bbox_norm):
            raise ValueError(f"Codex returned non-finite bbox coordinates for {region.region_id}")
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError(f"Codex returned invalid normalized bbox for {region.region_id}: {region.bbox_norm}")


def run_bbox_agent(
    image_bytes: bytes, regions: list[dict], instruction: str = ""
) -> tuple[GeneratedBBoxDraft, str]:
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("RGB")
    orientation, model = run_codex_json(
        [("source-page.jpg", image_bytes)],
        "Inspect the page image and decide how to rotate it clockwise so its printed text is upright. "
        "Return 0 if already upright, otherwise 90, 180, or 270. Judge from text orientation, not page shape.",
        ORIENTATION_SCHEMA, "codex-bbox-orientation-", "orientation.json", PageOrientation,
    )
    rotation = orientation.clockwise_degrees
    if rotation:
        image = image.rotate(-rotation, expand=True)
    prompt_path = Path(__file__).with_name("system_prompt.md")
    prompt_template = Template(prompt_path.read_text(encoding="utf-8"))
    drafts = []
    model = ""
    for start in range(0, len(regions), 4):
        batch = regions[start:start + 4]
        legend = [
            {
                "region_id": region["region_id"],
                "label": region.get("label"),
                "overlay_color_rgb": bbox_overlay_color(index),
                "bbox_norm": rotate_bbox(region["bbox_norm"], rotation),
            }
            for index, region in enumerate(batch)
        ]
        prompt = prompt_template.substitute(
            region_legend_json=json.dumps(legend, ensure_ascii=False),
            user_instruction=instruction or "Refine all existing boxes only where the source image supports a change.",
        )
        draft, model = run_codex_json(
            [("source-page.jpg", prepare_bbox_reference_image(image, batch))],
            prompt, BBOX_DRAFT_SCHEMA, "codex-bbox-draft-", "bbox-draft.json", GeneratedBBoxDraft,
        )
        expected = {region["region_id"] for region in batch}
        if len({item.region_id for item in draft.regions}) != len(draft.regions) or {
            item.region_id for item in draft.regions
        } != expected:
            raise ValueError("Codex bbox draft must return each region in its image exactly once")
        if rotation:
            for item in draft.regions:
                item.bbox_norm = rotate_bbox(item.bbox_norm, (360 - rotation) % 360)
        drafts.extend(draft.regions)
    result = GeneratedBBoxDraft(regions=drafts)
    validate_bbox_draft(result, regions)
    return result, model
