"""Recognize chart content inside layout-detected chart regions."""

from __future__ import annotations

import json
import logging
import tempfile
from threading import Lock
from typing import Any

_log = logging.getLogger(__name__)
_MODEL_VERSION = "v1.5"
_pipeline: Any | None = None
_pipeline_device: str | None = None
_pipeline_lock = Lock()


def recognize_chart_regions(document: Any, config: dict[str, Any]) -> dict[int, dict[str, str]]:
    """Run PaddleOCR-VL on exact PP-DocLayout chart boxes, without padding."""
    if not config.get("docling_chart_recognition", True):
        return {}

    chart_items = [
        item for item, _level in document.iterate_items()
        if str(getattr(item.label, "value", item.label)).lower() == "chart"
    ]
    if not chart_items:
        return {}

    device = "gpu:0" if str(config.get("docling_device", "cpu")).lower() == "cuda" else "cpu"
    try:
        pipeline = _get_pipeline(device)
    except Exception:
        _log.exception("Could not initialize PaddleOCR-VL chart recognition")
        return {}

    page_images: dict[int, Any] = {}
    recognized: dict[int, dict[str, str]] = {}
    for item in chart_items:
        provenance = next(iter(getattr(item, "prov", []) or []), None)
        if provenance is None:
            continue
        page_number = int(provenance.page_no)
        page = document.pages.get(page_number)
        page_size = getattr(page, "size", None)
        if page is None or page_size is None:
            continue
        image = page_images.get(page_number)
        if image is None:
            try:
                image = page.get_image(scale=1.0)
            except Exception:
                _log.exception("Could not render page %s for chart recognition", page_number)
                continue
            if image is None:
                continue
            page_images[page_number] = image

        box = _top_left_bbox(provenance.bbox, float(page_size.height))
        if box is None:
            continue
        width, height = image.size
        sx, sy = width / float(page_size.width), height / float(page_size.height)
        x0, y0, x1, y1 = box
        crop_box = (
            max(0, min(width, round(x0 * sx))),
            max(0, min(height, round(y0 * sy))),
            max(0, min(width, round(x1 * sx))),
            max(0, min(height, round(y1 * sy))),
        )
        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            continue

        try:
            crop = image.convert("RGB").crop(crop_box)
            with tempfile.NamedTemporaryFile(suffix=".png") as temporary:
                crop.save(temporary.name, format="PNG")
                outputs = list(pipeline.predict(temporary.name))
            text = "\n".join(
                content
                for content in (_chart_blocks(output) for output in outputs)
                if content
            ).strip()
            if text:
                recognized[id(item)] = {
                    "text": text,
                    "model": f"PaddleOCR-VL {_MODEL_VERSION}",
                    "input": "exact_layout_chart_bbox_crop",
                }
        except Exception:
            _log.exception("PaddleOCR-VL failed on chart region on page %s", page_number)
    return recognized


def _get_pipeline(device: str) -> Any:
    global _pipeline, _pipeline_device
    with _pipeline_lock:
        if _pipeline is None or _pipeline_device != device:
            from paddleocr import PaddleOCRVL

            _pipeline = PaddleOCRVL(
                pipeline_version=_MODEL_VERSION,
                device=device,
                use_chart_recognition=True,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
            )
            _pipeline_device = device
    return _pipeline


def _chart_blocks(output: Any) -> str:
    payload = getattr(output, "json", {})
    if callable(payload):
        payload = payload()
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return ""
    if not isinstance(payload, dict):
        return ""
    result = payload.get("res", payload)
    blocks = result.get("parsing_res_list", []) if isinstance(result, dict) else []
    return "\n".join(
        str(block.get("block_content") or "").strip()
        for block in blocks
        if isinstance(block, dict)
        and str(block.get("block_label", "")).lower() == "chart"
        and str(block.get("block_content") or "").strip()
    )


def _top_left_bbox(bbox: Any, page_height: float) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    left, top, right, bottom = (float(bbox.l), float(bbox.t), float(bbox.r), float(bbox.b))
    if str(getattr(bbox, "coord_origin", "")).upper().endswith("BOTTOMLEFT"):
        top, bottom = page_height - bottom, page_height - top
    return left, top, right, bottom
