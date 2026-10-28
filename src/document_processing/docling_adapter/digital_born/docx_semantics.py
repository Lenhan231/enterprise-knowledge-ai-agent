"""Restore paragraph structure from native Word formatting."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict, deque
from io import BytesIO
from typing import Any


def apply_docx_semantics(result: dict[str, Any], source_bytes: bytes | None) -> None:
    """Use Word styles and formatting to label mapped elements and sections."""
    if not source_bytes:
        return
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn

        word_document = Document(BytesIO(source_bytes))
    except (ImportError, ValueError, OSError):
        return

    hints: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for paragraph in word_document.paragraphs:
        text = " ".join(paragraph.text.split())
        if not text:
            continue
        style = paragraph.style
        style_id = str(getattr(style, "style_id", "") or "")
        style_name = str(getattr(style, "name", "") or "")
        paragraph_properties = paragraph._p.pPr
        style_properties = style._element.pPr
        outline_level = _outline_level(paragraph_properties, qn)
        if outline_level is None:
            outline_level = _outline_level(style_properties, qn)
        heading_style = re.search(r"heading\s*([1-9])", f"{style_id} {style_name}", re.IGNORECASE)
        if outline_level is None and heading_style:
            outline_level = int(heading_style.group(1)) - 1

        has_numbering = _has_numbering(paragraph_properties, qn) or _has_numbering(style_properties, qn)
        bold = any(run.bold is True for run in paragraph.runs if run.text.strip())
        uppercase = text == text.upper() and any(char.isalpha() for char in text)
        centered_title = (
            paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER and bold and uppercase and len(text) < 180
        )
        numbered_heading = re.match(r"^(\d+(?:\.\d+)*[.)]?)\s+", text) if bold else None
        number = re.match(r"^\d+(?:\.\d+)*", numbered_heading.group()) if numbered_heading else None
        numbered_depth = len(number.group().split(".")) if number else None
        heading_level = outline_level + 1 if outline_level is not None else numbered_depth
        list_item = (
            has_numbering
            or "list" in style_id.lower()
            or bool(re.match(r"^(?:[-*•‣]|\d+[.)])\s+", text) and not numbered_heading)
        )
        hints[docx_text_key(text)].append({
            "heading_level": heading_level,
            "centered_title": centered_title,
            "list_item": list_item,
        })

    section_path: list[str] = []
    pending_table_title: str | None = None
    for element in result.get("elements", []):
        metadata = element.setdefault("metadata", {})
        if metadata.get("element_type") in {"page_header", "page_footer"}:
            continue
        if metadata.get("element_type") == "title_table":
            pending_table_title = str(element.get("text") or "").strip() or None
            continue
        if element.get("element_type") == "table":
            table_ref = element.get("table_ref")
            if isinstance(table_ref, int) and 0 <= table_ref < len(result.get("tables", [])):
                table = result["tables"][table_ref]
                table_name = pending_table_title or (section_path[-1] if section_path else None)
                if table_name:
                    table["table_name"] = table_name
                    table.setdefault("context", {})["table_title"] = table_name
                    table.setdefault("metadata", {})["table_name"] = table_name
            pending_table_title = None
            continue
        pending_table_title = None
        key = docx_text_key(str(element.get("text") or ""))
        candidates = hints.get(key)
        if not candidates:
            metadata["section_path"] = list(section_path)
            metadata["section_title"] = section_path[-1] if section_path else None
            continue

        hint = candidates.popleft()
        heading_level = hint["heading_level"]
        if heading_level is not None:
            heading_level = min(max(int(heading_level), 1), 9)
            section_path = section_path[: heading_level - 1] + [str(element.get("text") or "")]
            metadata.update({
                "element_type": "title",
                "layout_type": "section_header",
                "heading_level": heading_level,
            })
        elif hint["centered_title"]:
            metadata.update({"element_type": "title", "layout_type": "title"})
        elif hint["list_item"]:
            metadata.update({"element_type": "list_item", "layout_type": "list_item"})
        metadata["section_path"] = list(section_path)
        metadata["section_title"] = section_path[-1] if section_path else None


def _outline_level(properties: Any, qn: Any) -> int | None:
    if properties is None:
        return None
    value = properties.find(qn("w:outlineLvl"))
    return int(value.get(qn("w:val"))) if value is not None else None


def _has_numbering(properties: Any, qn: Any) -> bool:
    return properties is not None and properties.find(qn("w:numPr")) is not None


def docx_text_key(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()
