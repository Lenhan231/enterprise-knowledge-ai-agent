"""Convert MinerU JSON and Markdown results to shared parser output."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

import fitz

from core.document_processing.headings import HEADING_PATTERNS, heading_level, section_metadata
from core.document_processing.pipelines.helpers.table_parser import parse_html_table


def _markdown_table(markdown: str) -> tuple[list[str], list[dict[str, str]]] | None:
    lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines if "|" in line]
    rows = [row for row in rows if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in row)]
    if len(rows) < 2:
        return None
    columns = rows[0]
    values = [row + [""] * max(0, len(columns) - len(row)) for row in rows[1:]]
    return columns, [dict(zip(columns, row[:len(columns)])) for row in values]


def _html_table(content: str) -> tuple[list[str], list[dict[str, str]]] | None:
    grid = parse_html_table(content)
    if len(grid) < 2:
        return None
    columns = [value or f"column_{index + 1}" for index, value in enumerate(grid[0])]
    rows = [dict(zip(columns, row + [""] * max(0, len(columns) - len(row)))) for row in grid[1:]]
    return columns, rows


class MineruResultMapper:
    """Normalize MinerU output blocks, tables, section context, and provenance."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def markdown_result(self, markdown: str, document: dict[str, Any]) -> dict[str, Any]:
        metadata = document.get("metadata", {})
        image_chunks_by_asset: dict[str, list[dict[str, Any]]] = document.get(
            "image_chunks_by_asset", {},
        )
        events: list[tuple[int, int, str, str]] = [
            (match.start(), match.end(), "html_table", match.group())
            for match in re.finditer(r"<table\b.*?</table\s*>", markdown, re.IGNORECASE | re.DOTALL)
        ]
        lines = markdown.splitlines(keepends=True)
        for index in range(len(lines) - 1):
            if "|" not in lines[index] or not re.fullmatch(
                r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*\n?",
                lines[index + 1],
            ):
                continue
            end_index = index + 2
            while end_index < len(lines) and "|" in lines[end_index] and lines[end_index].strip():
                end_index += 1
            start = sum(len(line) for line in lines[:index])
            end = sum(len(line) for line in lines[:end_index])
            events.append((start, end, "markdown_table", "".join(lines[index:end_index])))
        events.extend(
            (match.start(), match.end(), "image", match.group(1))
            for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", markdown)
        )
        events.sort(key=lambda event: (event[0], -(event[1] - event[0])))

        elements: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        section_stack: list[str] = []
        prose: list[str] = []
        seen_assets: set[str] = set()

        def section_metadata_now() -> dict[str, Any]:
            title = section_stack[-1] if section_stack else None
            return {
                "section_title": title,
                "section_path": list(section_stack),
                "heading_level": len(section_stack) if title else None,
            }

        def flush_prose() -> None:
            text = "\n".join(prose).strip()
            prose.clear()
            if not text:
                return
            elements.append({
                "text": text,
                "metadata": {
                    **metadata,
                    **section_metadata_now(),
                    "element_type": "text",
                    "layout_type": "text",
                    "parser": "mineru",
                    "mineru_tier": "flash",
                    "text_extraction_method": "mineru.flash",
                },
            })

        def consume_text(text: str) -> None:
            for line in text.splitlines():
                heading = re.match(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$", line)
                if heading:
                    flush_prose()
                    level = len(heading.group(1))
                    title = heading.group(2).strip().strip("* ")
                    section_stack[:] = section_stack[:level - 1]
                    section_stack.append(title)
                else:
                    prose.append(line)

        def add_image(path: str) -> None:
            flush_prose()
            normalized_path = PurePosixPath(path.split("?", 1)[0]).as_posix()
            candidates = (normalized_path, PurePosixPath(normalized_path).name)
            found_key = next((key for key in candidates if key in image_chunks_by_asset), None)
            if found_key is None:
                basename = PurePosixPath(normalized_path).name
                found_key = next(
                    (key for key in image_chunks_by_asset if PurePosixPath(key).name == basename),
                    None,
                )
            if found_key is None:
                return
            seen_assets.add(found_key)
            context = section_metadata_now()
            for source_element in image_chunks_by_asset[found_key]:
                element = {**source_element, "metadata": dict(source_element.get("metadata") or {})}
                chunk_metadata = element["metadata"]
                chunk_metadata.update(context)
                chunk_metadata.update({"element_type": "image", "layout_type": "image"})
                text = str(element.get("text") or "").strip()
                title = context.get("section_title")
                if title and text and not text.startswith(f"Section: {title}\n"):
                    element["text"] = f"Section: {title}\n{text}"
                elements.append(element)

        def add_table(block: str, method: str) -> None:
            flush_prose()
            parsed = _html_table(block) if method == "html" else _markdown_table(block)
            if not parsed:
                prose.append(block)
                return
            columns, rows = parsed
            table_index = len(tables)
            table_metadata = {
                **section_metadata_now(),
                "parser": "mineru",
                "mineru_tier": "flash",
                "table_extraction_method": f"mineru.flash.{method}",
            }
            table = {
                "table_index": table_index,
                "columns": columns,
                "rows": rows,
                "metadata": table_metadata,
            }
            tables.append(table)
            elements.append({
                "element_type": "table", "table_ref": len(tables) - 1,
                "metadata": {
                    **metadata,
                    **section_metadata_now(),
                    "element_type": "table",
                    "table_index": table_index,
                    "parser": "mineru",
                    "mineru_tier": "flash",
                    "text_extraction_method": "mineru.flash",
                },
            })

        cursor = 0
        for start, end, kind, value in events:
            if start < cursor:
                continue
            consume_text(markdown[cursor:start])
            if kind == "html_table":
                add_table(value, "html")
            elif kind == "markdown_table":
                add_table(value, "markdown")
            else:
                add_image(value)
            cursor = end
        consume_text(markdown[cursor:])
        flush_prose()

        # Keep extracted assets that MinerU emitted without a Markdown reference as
        # separate OCR chunks, rather than silently dropping their recognized text.
        for asset, asset_chunks in image_chunks_by_asset.items():
            if asset in seen_assets or PurePosixPath(asset).name in seen_assets:
                continue
            elements.extend(asset_chunks)
        return {"elements": elements, "tables": tables}

    @staticmethod
    def _block_text(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(text for item in value if (text := MineruResultMapper._block_text(item)))
        if isinstance(value, dict):
            return MineruResultMapper._block_text(value.get("content", ""))
        return ""

    @staticmethod
    def _selected_pages(page_count: int, page_range: str) -> list[int] | None:
        if not page_range:
            return None
        selected: list[int] = []
        for part in page_range.split(","):
            bounds = [int(value) for value in part.split("-")]
            selected.extend(range(bounds[0], bounds[-1] + 1))
        if any(page < 1 or page > page_count for page in selected):
            raise RuntimeError("MinerU page range is outside the uploaded PDF")
        return selected

    def to_parser_result(
        self,
        payload: dict[str, Any],
        source: bytes | str | Path,
        version: str | None,
    ) -> dict[str, Any]:
        pdf = fitz.open(stream=source, filetype="pdf") if isinstance(source, bytes) else fitz.open(source)
        tables: list[dict[str, Any]] = []
        elements: list[dict[str, Any]] = []
        current_section_title = None
        current_heading_level = None
        page_count = len(pdf)
        selected_pages = self._selected_pages(page_count, self.config.get("mineru_page_range", ""))
        try:
            for page_data in payload.get("pages", []):
                page_idx = int(page_data.get("page_idx", 0))
                page_number = selected_pages[page_idx] if selected_pages and page_idx < len(selected_pages) else page_idx + 1
                if not 1 <= page_number <= page_count:
                    continue
                page_rect = pdf[page_number - 1].rect
                for block in page_data.get("blocks", []):
                    kind = str(block.get("type", "text")).lower()
                    text = " ".join(self._block_text(block.get("content")).split())
                    if not text or kind in {"header", "footer", "page_number", "image", "chart"}:
                        continue
                    bbox = block.get("bbox")
                    point_bbox = None
                    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                        point_bbox = [
                            float(bbox[0]) * page_rect.width,
                            float(bbox[1]) * page_rect.height,
                            float(bbox[2]) * page_rect.width,
                            float(bbox[3]) * page_rect.height,
                        ]

                    element_type = "title" if kind in {"doc_title", "paragraph_title"} else kind
                    table_index = None
                    if kind == "table":
                        is_html = bool(re.search(r"<table\b", text, re.IGNORECASE))
                        parsed_table = _html_table(text) if is_html else _markdown_table(text)
                        if parsed_table:
                            columns, rows = parsed_table
                            table_index = sum(item["page_number"] == page_number for item in tables)
                            tables.append({
                                "page_number": page_number, "table_index": table_index,
                                "columns": columns, "rows": rows,
                                "metadata": {
                                    "element_type": "table", "layout_type": "table",
                                    "bbox": point_bbox, "bbox_coordinate_system": "pdf_point",
                                    "parser": "mineru", "mineru_tier": "basic",
                                    "table_extraction_method": "mineru_html_table" if is_html else "mineru_markdown_table",
                                },
                            })
                            text = ""
                        element_type = "table"
                    heading_kind = next(
                        (name for name, pattern in HEADING_PATTERNS.items() if pattern.match(text)), None,
                    )
                    if heading_kind:
                        element_type = "title"
                    if element_type == "title":
                        current_section_title = text
                        current_heading_level = heading_level(text) or 1
                    if table_index is not None:
                        elements.append({
                            "element_type": "table", "table_ref": len(tables) - 1,
                            "metadata": {
                                "page_number": page_number,
                                **section_metadata(current_section_title, current_heading_level),
                                "bbox": point_bbox,
                                "bbox_coordinate_system": "pdf_point",
                                "text_extraction_method": "mineru.local.basic",
                                "parser": "mineru",
                                "mineru_tier": "basic",
                                "table_index": table_index,
                            },
                        })
                        continue
                    element_metadata = {
                            "page_number": page_number,
                            "element_type": element_type,
                            "layout_type": element_type,
                            **section_metadata(current_section_title, current_heading_level),
                            "bbox": point_bbox,
                            "bbox_coordinate_system": "pdf_point",
                            "text_extraction_method": "mineru.local.basic",
                            "parser": "mineru", "mineru_tier": "basic",
                        }
                    if heading_kind:
                        element_metadata["heading_kind"] = heading_kind
                    elements.append({"text": text, "metadata": element_metadata})
        finally:
            pdf.close()
        return {
            "elements": elements,
            "tables": tables,
            "metadata": {
                "page_count": page_count,
                "layout_parser": "mineru.local",
                "mineru_version": version,
                "mineru_runtime": "local",
            },
        }
