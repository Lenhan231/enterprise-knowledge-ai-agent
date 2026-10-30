"""Map Docling document items into the shared chunk and table result shape."""

from __future__ import annotations

import logging
import math
from typing import Any

from document_processing.element_taxonomy import normalize_element_label
from .digital_born.docx_semantics import apply_docx_semantics, docx_text_key
from .scanned.postprocessing import clean_ocr_elements, recover_empty_cell_dashes

_log = logging.getLogger(__name__)

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
    page_images: dict[int, Any] = {}
    dash_recovery: dict[int, list[list[int]]] = {}
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
        page = result.document.pages.get(page_number) if page_number is not None else None
        page_size = getattr(page, "size", None)
        bbox = (
            _bbox(provenance.bbox, float(page_size.height) if page_size is not None else None)
            if provenance is not None else None
        )
        base_metadata = {
            **({"page_number": page_number} if page_number is not None else {}),
            **({
                "bbox": bbox,
                "bbox_coordinate_system": "docling_page_coordinate",
                "bbox_coordinate_origin": "TOPLEFT",
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
                "source_type": "pdf_embedded_image" if source_format == "pdf" else "office_embedded_image",
                "embedded_image_source_format": source_format,
                "embedded_image_index": image_result["image_index"],
                "embedded_picture_label": label,
                "text_extraction_method": f"docling.{ocr_engine}",
            }
            if source_format != "pdf":
                image_metadata.update({
                    "office_source_format": source_format,
                    "office_image_index": image_result["image_index"],
                    "office_picture_label": label,
                })
            if page_number is not None:
                image_metadata["page_number"] = page_number
            if bbox is not None:
                image_metadata["office_bbox" if source_format != "pdf" else "source_bbox"] = bbox

            image_output = image_result["output"]
            image_size = image_result.get("image_size")
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
                    if source_format == "pdf" and bbox is not None and image_size:
                        metadata.update(_project_embedded_bbox(image_bbox, bbox, image_size))
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
                    if source_format == "pdf" and bbox is not None and image_size:
                        metadata.update(_project_embedded_bbox(image_bbox, bbox, image_size))
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
            recovered: list[list[int]] = []
            header_rows: set[int] = set()
            for cell in data.table_cells:
                row = int(cell.start_row_offset_idx)
                column = int(cell.start_col_offset_idx)
                if 0 <= row < row_count and 0 <= column < column_count:
                    grid[row][column] = _cell(cell.text)
                    if cell.column_header:
                        header_rows.add(row)
            if do_ocr and page is not None and row_count and column_count:
                image = _get_page_image(page, page_images, page_number)
                if image is not None:
                    recovered = recover_empty_cell_dashes(
                        list(data.table_cells), grid, image,
                        float(page_size.width), float(page_size.height),
                    )
                    if recovered:
                        dash_recovery[int(page_number)] = dash_recovery.get(int(page_number), []) + recovered
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
            if recovered:
                table["metadata"]["dash_recovery"] = {
                    "count": len(recovered),
                    "row_column_indices": recovered,
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

    page_sizes = {
        int(number): (float(page.size.width), float(page.size.height))
        for number, page in result.document.pages.items()
    }
    ocr_elements_present = any(
        str((element.get("metadata") or {}).get("text_extraction_method", ""))
        in {"docling.vietocr", "docling.tesseract"}
        for element in elements
    )
    cleanup_diagnostics = []
    if ocr_elements_present:
        ocr_pages = {
            int((element.get("metadata") or {}).get("page_number"))
            for element in elements
            if (element.get("metadata") or {}).get("page_number") is not None
            and (element.get("metadata") or {}).get("text_extraction_method")
            in {"docling.vietocr", "docling.tesseract"}
        }
        for page_number in ocr_pages:
            page = result.document.pages.get(page_number)
            _get_page_image(page, page_images, page_number)
        elements, cleanup_diagnostics = clean_ocr_elements(
            elements, tables, page_images, page_sizes, ocr_engine
        )

    mapped = {
        "elements": elements,
        "tables": tables,
        "metadata": {
            "docling_version": docling_version,
            **({"ocr_cleanup": cleanup_diagnostics} if cleanup_diagnostics else {}),
            **({"table_dash_recovery": dash_recovery} if dash_recovery else {}),
        },
    }
    if source_format == "docx":
        apply_docx_semantics(mapped, source_bytes)
    return mapped


def _get_page_image(page: Any, cache: dict[int, Any], page_number: int | None):
    if page is None or page_number is None:
        return None
    page_number = int(page_number)
    if page_number in cache:
        return cache[page_number]
    try:
        import cv2
        import numpy as np

        image = page.get_image(scale=1.0)
        if image is None:
            return None
        cache[page_number] = cv2.cvtColor(
            np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR
        )
    except Exception:
        _log.debug("Could not load source page image for OCR post-processing", exc_info=True)
        return None
    return cache[page_number]


def _bbox(box: Any, page_height: float | None = None) -> list[float] | None:
    if box is None:
        return None
    left, top, right, bottom = (float(box.l), float(box.t), float(box.r), float(box.b))
    if str(getattr(box, "coord_origin", "")).upper().endswith("BOTTOMLEFT"):
        if page_height is not None:
            return [left, page_height - top, right, page_height - bottom]
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


def _project_embedded_bbox(
    image_bbox: list[float], source_bbox: list[float], image_size: list[int],
) -> dict[str, Any]:
    """Map an OCR box from a cropped PDF image back onto its source page."""
    image_width, image_height = image_size
    left, top, right, bottom = source_bbox
    scale_x = (right - left) / image_width
    scale_y = (bottom - top) / image_height
    x0, y0, x1, y1 = image_bbox
    return {
        "bbox": [
            left + x0 * scale_x,
            top + y0 * scale_y,
            left + x1 * scale_x,
            top + y1 * scale_y,
        ],
        "bbox_coordinate_system": "docling_page_coordinate",
        "bbox_coordinate_origin": "TOPLEFT",
    }
