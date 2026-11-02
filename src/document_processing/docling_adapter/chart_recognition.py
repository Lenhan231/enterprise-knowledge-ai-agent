"""Recognize chart content inside layout-detected chart regions."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import base64
from threading import Lock
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps

_log = logging.getLogger(__name__)
_MODEL_VERSION = "v1.5"
_PAGE_RENDER_SCALE = 3.0
_pipeline: Any | None = None
_pipeline_device: str | None = None
_pipeline_lock = Lock()
_groq_client: Any | None = None
_groq_api_key: str | None = None
_groq_lock = Lock()
_NUMERIC_CELL = re.compile(r"\d")
_NON_TEXT_VALUE = re.compile(r"^[\s.,%$€£¥()+\-−–—/]+$")
_CORRECTION_SYSTEM = """You correct OCR spelling in Vietnamese chart tables.
The supplied PaddleOCR-VL table is the source of truth for structure and every numeric cell.
The image is authoritative for spelling; OCR line candidates are noisy references.
Return only JSON: {\"corrections\":[{\"row\":0,\"column\":0,\"text\":\"corrected text\"}]}.
Rows and columns are zero-based in the supplied pipe-delimited table, including its header.
Return corrections only for cells listed as editable. Do not add, remove, reorder, or combine cells.
Never return numeric cells, values, or a replacement table. If uncertain, omit the correction."""


def recognize_chart_regions(
    document: Any,
    config: dict[str, Any],
    chart_regions: list[dict[str, Any]] | None = None,
    *,
    page_source: Any = None,
    source_format: str | None = None,
) -> list[dict[str, Any]]:
    """Run PaddleOCR-VL on chart boxes, including a clearly matched title when present."""
    if not chart_regions:
        return []

    recognition_regions = []
    seen_groups = set()
    for region in chart_regions:
        group_id = region.get("recognition_group_id")
        if group_id and group_id in seen_groups:
            continue
        if group_id:
            seen_groups.add(group_id)
            region = {
                **region,
                "bbox": region["recognition_group_bbox"],
                "member_bboxes": region["recognition_group_member_bboxes"],
            }
        recognition_regions.append(region)
    recognition_regions.sort(key=lambda region: int(region["page_no"]))

    results = [
        {
            "page_no": int(region["page_no"]),
            "bbox": list(map(float, region["bbox"])),
            "recognition_bbox": list(map(float, region.get("recognition_bbox", region["bbox"]))),
            "member_bboxes": region.get("member_bboxes"),
            "title_bbox": region.get("title_bbox"),
            "title_match_score": region.get("title_match_score"),
            "text": "",
            "model": f"PaddleOCR-VL {_MODEL_VERSION}",
            "text_refinement": "paddleocr_vl_only",
            "input": (
                "chart_and_matched_title_union_crop"
                if region.get("title_bbox") else "exact_layout_chart_bbox_crop"
            ),
        }
        for region in recognition_regions
    ]
    if not config.get("docling_chart_recognition", True):
        for result in results:
            result["input"] = "disabled_chart_recognition"
        return results

    device = "gpu:0" if str(config.get("docling_device", "cpu")).lower() == "cuda" else "cpu"
    try:
        pipeline = _get_pipeline(device)
    except Exception:
        _log.exception("Could not initialize PaddleOCR-VL chart recognition")
        return results

    pdf_document = None
    if source_format == "pdf" and page_source is not None:
        try:
            import pypdfium2 as pdfium

            pdf_document = pdfium.PdfDocument(page_source)
        except Exception:
            _log.exception("Could not open source PDF for high-resolution chart rendering")

    cached_page_number: int | None = None
    page_image: Any | None = None
    for result, region in zip(results, recognition_regions):
        page_number = int(region["page_no"])
        page = document.pages.get(page_number)
        page_size = getattr(page, "size", None)
        if page is None or page_size is None:
            continue
        if page_number != cached_page_number:
            cached_page_number = page_number
            page_image = None
            try:
                if pdf_document is not None:
                    pdf_page = pdf_document[page_number - 1]
                    rendered = pdf_page.render(scale=_PAGE_RENDER_SCALE * 1.5, rotation=0)
                    page_image = rendered.to_pil().copy()
                    rendered.close()
                    page_image = page_image.resize((
                        round(float(page_size.width) * _PAGE_RENDER_SCALE),
                        round(float(page_size.height) * _PAGE_RENDER_SCALE),
                    ))
                elif source_format in {"png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"} and page_source is not None:
                    image_source = BytesIO(page_source) if isinstance(page_source, bytes) else page_source
                    with Image.open(image_source) as source_image:
                        if getattr(source_image, "n_frames", 1) > 1:
                            source_image.seek(page_number - 1)
                        page_image = ImageOps.exif_transpose(source_image).convert("RGB").copy()
                else:
                    image_ref = getattr(page, "image", None)
                    page_image = getattr(image_ref, "pil_image", None)
                    if page_image is not None:
                        page_image = page_image.resize((
                            round(float(page_size.width) * _PAGE_RENDER_SCALE),
                            round(float(page_size.height) * _PAGE_RENDER_SCALE),
                        ))
            except Exception:
                _log.exception("Could not render page %s for chart recognition", page_number)
                continue
        if page_image is None:
            continue

        box = tuple(map(float, region.get("recognition_bbox", region["bbox"])))
        width, height = page_image.size
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
            crop = page_image.convert("RGB").crop(crop_box)
            with tempfile.NamedTemporaryFile(suffix=".png") as temporary:
                crop.save(temporary.name, format="PNG")
                outputs = list(pipeline.predict(temporary.name))
            text = "\n".join(
                content
                for content in (_chart_blocks(output) for output in outputs)
                if content
            ).strip()
            result["text"] = text
            if text and config.get("docling_chart_llm_correction", True):
                ocr_references = _ocr_text_candidates(page, box)
                corrected = _correct_chart_text(crop, text, ocr_references)
                if corrected is not None:
                    result["text"] = corrected
                    result["text_refinement"] = "groq_ocr_referenced_text_only"
                    groq_model = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
                    result["model"] = f"PaddleOCR-VL {_MODEL_VERSION} + Groq {groq_model}"
        except Exception:
            _log.exception("PaddleOCR-VL failed on chart region on page %s", page_number)
    if pdf_document is not None:
        pdf_document.close()
    return results


def _ocr_text_candidates(page: Any, bbox: tuple[float, float, float, float]) -> list[str]:
    """Collect existing OCR lines whose centers fall within the chart/title crop."""
    x0, y0, x1, y1 = bbox
    candidates = []
    for cell in getattr(page, "cells", []):
        if not getattr(cell, "from_ocr", False) or not str(getattr(cell, "text", "")).strip():
            continue
        box = cell.to_bounding_box()
        if x0 <= (box.l + box.r) / 2 <= x1 and y0 <= (box.t + box.b) / 2 <= y1:
            candidates.append((box.t, box.l, str(cell.text).strip()))
    return [text for _, _, text in sorted(candidates)[:100]]


def _correct_chart_text(crop: Image.Image, table_text: str, ocr_references: list[str]) -> str | None:
    """Ask Groq to correct text cells only, then merge changes into Paddle's table."""
    table_lines = [line for line in table_text.splitlines() if "|" in line]
    rows = [line.split("|") for line in table_lines]
    editable = [
        {"row": row_index, "column": column_index, "text": cell.strip()}
        for row_index, row in enumerate(rows)
        for column_index, cell in enumerate(row)
        if cell.strip() and not _NUMERIC_CELL.search(cell) and not _NON_TEXT_VALUE.fullmatch(cell)
    ]
    if not rows or not editable or not ocr_references:
        return None
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None

    buffer = BytesIO()
    crop.save(buffer, format="PNG")
    image_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    prompt = (
        "Correct spelling and Vietnamese diacritics in editable table labels only. "
        "Use the chart image and OCR lines as references. Preserve the source table exactly.\n\n"
        f"PaddleOCR-VL table:\n{table_text}\n\n"
        f"Editable text cells (row/column/text):\n{json.dumps(editable, ensure_ascii=False)}\n\n"
        f"OCR line candidates:\n{json.dumps(ocr_references, ensure_ascii=False)}"
    )
    try:
        response = _get_groq_client(api_key).chat.completions.create(
            model=os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b"),
            messages=[
                {"role": "system", "content": _CORRECTION_SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}},
                ]},
            ],
            temperature=0,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        allowed = {(item["row"], item["column"]) for item in editable}
        for item in payload.get("corrections", []):
            if not isinstance(item, dict):
                continue
            row_index, column_index = item.get("row"), item.get("column")
            replacement = item.get("text")
            if (
                type(row_index) is int and type(column_index) is int
                and (row_index, column_index) in allowed
                and isinstance(replacement, str) and replacement.strip()
                and not _NUMERIC_CELL.search(replacement)
                and not _NON_TEXT_VALUE.fullmatch(replacement)
            ):
                original = rows[row_index][column_index]
                leading = original[:len(original) - len(original.lstrip())]
                trailing = original[len(original.rstrip()):]
                rows[row_index][column_index] = f"{leading}{replacement.strip()}{trailing}"
        corrected_lines = iter("|".join(row) for row in rows)
        return "\n".join(
            next(corrected_lines) if "|" in line else line
            for line in table_text.splitlines()
        )
    except Exception:
        _log.exception("Groq chart text correction failed; keeping PaddleOCR-VL output")
        return None


def _get_groq_client(api_key: str) -> Any:
    global _groq_client, _groq_api_key
    with _groq_lock:
        if _groq_client is None or _groq_api_key != api_key:
            from openai import OpenAI

            _groq_client = OpenAI(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=60,
                max_retries=1,
            )
            _groq_api_key = api_key
    return _groq_client


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
