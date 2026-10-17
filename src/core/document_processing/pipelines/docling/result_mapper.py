"""Map Docling document items into the shared chunk and table result shape."""

from __future__ import annotations

import math
from typing import Any

from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.chunking.router import build_chunks


def map_result(
    result: Any,
    config: dict[str, Any],
    chunking: ChunkingConfig,
    table_item_type: type,
    do_ocr: bool,
    docling_version: str | None,
    source_format: str,
) -> dict[str, Any]:
    """Normalize Docling items, provenance, structured tables, and parser metadata."""
    chunks: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    section_path: list[str] = []
    table_number_by_page: dict[int | None, int] = {}

    for item, _level in result.document.iterate_items():
        label = getattr(item.label, "value", str(item.label)).lower()
        text = str(getattr(item, "text", "") or "").strip()
        provenance = next(iter(getattr(item, "prov", []) or []), None)
        page_number = int(provenance.page_no) if provenance is not None else None
        bbox = _bbox(provenance.bbox) if provenance is not None else None
        base_metadata = {
            **({"page_number": page_number} if page_number is not None else {}),
            **({
                "bbox": bbox,
                "bbox_coordinate_system": "docling_page_coordinate",
            } if bbox is not None else {}),
            "parser": "docling",
            "docling_label": label,
            "docling_version": docling_version,
            "text_extraction_method": (
                "docling.rapidocr" if do_ocr and source_format in {"pdf", "png", "jpg", "jpeg", "tif", "tiff"}
                else "docling.native"
            ),
        }

        if isinstance(item, table_item_type) and config.get("docling_table_structure", True):
            data = item.data
            row_count, column_count = int(data.num_rows), int(data.num_cols)
            grid = [[""] * column_count for _ in range(row_count)]
            header_rows: set[int] = set()
            for cell in data.table_cells:
                row = int(cell.start_row_offset_idx)
                column = int(cell.start_col_offset_idx)
                if 0 <= row < row_count and 0 <= column < column_count:
                    grid[row][column] = _cell(cell.text)
                    if cell.column_header:
                        header_rows.add(row)
            has_header = bool(header_rows and 0 in header_rows)
            if has_header:
                columns = [value or f"column_{index + 1}" for index, value in enumerate(grid[0])]
                value_rows = grid[1:]
            else:
                columns = [f"column_{index + 1}" for index in range(column_count)]
                value_rows = grid
            rows = [dict(zip(columns, values)) for values in value_rows]
            if not columns or not rows:
                continue
            table_index = table_number_by_page.get(page_number, 0)
            table_number_by_page[page_number] = table_index + 1
            table = {
                "table_index": table_index,
                "columns": columns,
                "rows": rows,
                "context": {},
                "metadata": {
                    **base_metadata,
                    "element_type": "table",
                    "layout_type": "table",
                    "table_structure_model": "Docling TableFormer",
                },
            }
            if page_number is not None:
                table["page_number"] = page_number
            tables.append(table)
            chunks.extend(build_chunks(
                tables[-1], chunking, kind="table", metadata=base_metadata,
            ))
            continue

        if label in {"page_header", "page_footer", "picture", "chart"} or not text:
            continue
        if label in {"title", "section_header"}:
            section_path = [text] if label == "title" else (section_path[:1] + [text])
        element_type = {
            "title": "title",
            "section_header": "title",
            "list_item": "list_item",
            "formula": "formula",
            "caption": "figure_caption",
            "footnote": "footnote",
        }.get(label, "paragraph")
        chunks.append({
            "text": text,
            "metadata": {
                **base_metadata,
                "element_type": element_type,
                "layout_type": label,
                "section_path": list(section_path),
                "section_title": section_path[-1] if section_path else None,
                "heading_level": min(len(section_path), 2) or None,
            },
        })

    for index, chunk in enumerate(chunks):
        chunk["metadata"]["chunk_index"] = index
    return {
        "chunks": chunks,
        "tables": tables,
        "metadata": {"docling_version": docling_version},
    }


def _bbox(box: Any) -> list[float] | None:
    if box is None:
        return None
    left, top, right, bottom = (float(box.l), float(box.t), float(box.r), float(box.b))
    if str(getattr(box, "coord_origin", "")).upper().endswith("BOTTOMLEFT"):
        return [left, bottom, right, top]
    return [left, top, right, bottom]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    try:
        if math.isnan(float(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()
