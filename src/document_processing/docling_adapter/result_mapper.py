"""Map Docling document items into the shared chunk and table result shape."""

from __future__ import annotations

import math
from typing import Any

from document_processing.element_taxonomy import normalize_element_label
from .formats.docx_semantics import apply_docx_semantics, docx_text_key

def map_result(
    result: Any,
    config: dict[str, Any],
    table_item_type: type,
    do_ocr: bool,
    docling_version: str | None,
    source_format: str,
    source_bytes: bytes | None = None,
    embedded_image_results: dict[int, dict[str, Any]] | None = None,
    preserve_chart_items: bool = False,
) -> dict[str, Any]:
    """Normalize Docling items, provenance, structured tables, and parser metadata."""
    elements: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    section_path: list[str] = []
    table_number_by_page: dict[int | None, int] = {}
    layout_table_cell_texts: set[str] = set()
    ocr_engine = str(config.get("docling_ocr_engine", "tesseract")).lower()
    included_content_layers = None
    if source_format in {"docx", "pdf", "png", "jpg", "jpeg", "tif", "tiff"}:
        from docling_core.types.doc import ContentLayer

        # Docling stores detected page headers and footers as furniture;
        # its default iteration includes BODY only, so request both layers.
        included_content_layers = {ContentLayer.BODY, ContentLayer.FURNITURE}

    for item, _level in result.document.iterate_items(
        included_content_layers=included_content_layers
    ):
        label = getattr(item.label, "value", str(item.label)).lower()
        element_label = normalize_element_label(label)
        if (
            source_format == "docx"
            and element_label == "text"
            and getattr(item.content_layer, "value", item.content_layer) == "furniture"
        ):
            furniture_label = _docx_furniture_label(item, result.document)
            if furniture_label:
                element_label = furniture_label
        text = str(getattr(item, "text", "") or "").strip()
        provenance = next(iter(getattr(item, "prov", []) or []), None)
        page_number = int(provenance.page_no) if provenance is not None else None
        bbox = _bbox(provenance.bbox) if provenance is not None else None
        base_metadata = {
            **({"page_number": page_number} if page_number is not None else {}),
            **({
                "bbox": bbox,
                "bbox_coordinate_system": "docling_page_coordinate",
                "bbox_coordinate_origin": str(
                    getattr(provenance.bbox.coord_origin, "value", provenance.bbox.coord_origin)
                ).upper(),
            } if bbox is not None else {}),
            "parser": "docling",
            "docling_label": label,
            "docling_version": docling_version,
            "text_extraction_method": (
                f"docling.{ocr_engine}" if do_ocr and source_format in {"pdf", "png", "jpg", "jpeg", "tif", "tiff"}
                else "docling.native"
            ),
        }

        image_result = (embedded_image_results or {}).get(id(item))
        if image_result is not None:
            image_metadata = {
                "source_type": "office_embedded_image",
                "office_source_format": source_format,
                "office_image_index": image_result["image_index"],
                "office_picture_label": label,
                "text_extraction_method": f"docling.{ocr_engine}",
            }
            if page_number is not None:
                image_metadata["page_number"] = page_number
            if bbox is not None:
                image_metadata["office_bbox"] = bbox

            image_output = image_result["output"]
            table_offset = len(tables)
            for image_table in image_output.get("tables", []):
                table = {**image_table, "metadata": dict(image_table.get("metadata") or {})}
                metadata = table["metadata"]
                image_bbox = metadata.pop("bbox", None)
                metadata.pop("bbox_coordinate_system", None)
                metadata.pop("page_number", None)
                metadata.update(image_metadata)
                if image_bbox is not None:
                    metadata["embedded_image_bbox"] = image_bbox
                table_index = table_number_by_page.get(page_number, 0)
                table_number_by_page[page_number] = table_index + 1
                table["table_index"] = table_index
                table.pop("page_number", None)
                if page_number is not None:
                    table["page_number"] = page_number
                tables.append(table)

            for image_element in image_output.get("elements", []):
                element = {**image_element}
                metadata = dict(element.get("metadata") or {})
                image_bbox = metadata.pop("bbox", None)
                metadata.pop("bbox_coordinate_system", None)
                metadata.pop("page_number", None)
                metadata.update(image_metadata)
                if image_bbox is not None:
                    metadata["embedded_image_bbox"] = image_bbox
                if element.get("element_type") == "table":
                    table_ref = element.get("table_ref")
                    if isinstance(table_ref, int):
                        element["table_ref"] = table_offset + table_ref
                        element["metadata"] = metadata
                        metadata["table_index"] = tables[element["table_ref"]]["table_index"]
                element["metadata"] = metadata
                elements.append(element)
            continue

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
                if source_format == "docx":
                    cell_texts = [
                        _cell(cell.text) for cell in data.table_cells if _cell(cell.text)
                    ]
                    if cell_texts:
                        layout_table_cell_texts.update(docx_text_key(value) for value in cell_texts)
                        elements.append({
                            "text": " | ".join(cell_texts),
                            "metadata": {
                                **base_metadata,
                                "element_type": "text",
                                "layout_type": "text",
                            },
                        })
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
            elements.append({
                "element_type": "table", "table_ref": len(tables) - 1,
                "metadata": {
                    **base_metadata,
                    "element_type": "table",
                    "layout_type": "table",
                    "table_index": table_index,
                },
            })
            continue

        if label == "chart" and preserve_chart_items:
            elements.append({
                "text": text,
                "metadata": {
                    **base_metadata,
                    "element_type": "figure",
                    "layout_type": "figure",
                },
            })
            continue
        if not text and element_label not in {"figure", "seal"}:
            continue
        if source_format == "docx" and docx_text_key(text) in layout_table_cell_texts:
            continue
        if element_label in {"title", "section_header"}:
            section_path = [text] if element_label == "title" else (section_path[:1] + [text])
        elements.append({
            "text": text,
            "metadata": {
                **base_metadata,
                "element_type": element_label,
                "layout_type": element_label,
                "section_path": list(section_path),
                "section_title": section_path[-1] if section_path else None,
                "heading_level": min(len(section_path), 2) or None,
            },
        })

    mapped = {
        "elements": elements,
        "tables": tables,
        "metadata": {"docling_version": docling_version},
    }
    if source_format == "docx":
        apply_docx_semantics(mapped, source_bytes)
    return mapped


def _bbox(box: Any) -> list[float] | None:
    if box is None:
        return None
    left, top, right, bottom = (float(box.l), float(box.t), float(box.r), float(box.b))
    if str(getattr(box, "coord_origin", "")).upper().endswith("BOTTOMLEFT"):
        return [left, bottom, right, top]
    return [left, top, right, bottom]


def _docx_furniture_label(item: Any, document: Any) -> str | None:
    """Classify DOCX furniture text using its enclosing header/footer group."""
    parent = getattr(item, "parent", None)
    while parent is not None:
        parent = parent.resolve(doc=document)
        name = str(getattr(parent, "name", "") or "").strip().lower()
        if name == "page header":
            return "page_header"
        if name == "page footer":
            return "page_footer"
        parent = getattr(parent, "parent", None)
    return None


def _cell(value: Any) -> str:
    if value is None:
        return ""
    try:
        if math.isnan(float(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()
