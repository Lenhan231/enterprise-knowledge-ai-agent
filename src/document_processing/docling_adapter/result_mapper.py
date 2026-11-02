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
    chart_regions: list[dict[str, Any]] | None = None,
    chart_recognition_results: list[dict[str, Any]] | None = None,
    layout_detections: list[dict[str, Any]] | None = None,
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
        if (
            do_ocr
            and source_format in {"pdf", "png", "jpg", "jpeg", "tif", "tiff"}
            and page_number is not None
            and bbox is not None
            and _inside_chart_region(bbox, page_number, chart_regions or [])
        ):
            continue
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

        if not text and element_label not in {"figure", "seal"}:
            continue
        if source_format == "docx" and docx_text_key(text) in layout_table_cell_texts:
            continue
        if element_label == "title":
            section_path = [text] if label != "section_header" else (section_path[:1] + [text])
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

    for chart in chart_recognition_results or []:
        page_number = int(chart["page_no"])
        bbox = list(map(float, chart["bbox"]))
        chart_text = str(chart.get("text") or "").strip()
        elements.append({
            "text": chart_text,
            "metadata": {
                "page_number": page_number,
                "bbox": bbox,
                "bbox_coordinate_system": "docling_page_coordinate",
                "bbox_coordinate_origin": "TOPLEFT",
                "parser": "paddleocr_vl" if chart_text else "docling",
                "docling_label": "chart",
                "docling_version": docling_version,
                "text_extraction_method": (
                    f"paddleocr_vl.{chart.get('text_refinement')}"
                    if chart_text and chart.get("text_refinement") != "paddleocr_vl_only"
                    else "paddleocr_vl.chart_recognition" if chart_text else "layout_only.chart"
                ),
                "chart_recognition_bbox": chart.get("recognition_bbox", bbox),
                "chart_recognition_input": chart.get("input"),
                **({"chart_member_bboxes": chart["member_bboxes"]} if chart.get("member_bboxes") else {}),
                **({
                    "chart_title_bbox": chart["title_bbox"],
                    "chart_title_match_score": chart.get("title_match_score"),
                } if chart.get("title_bbox") else {}),
                **({
                    "chart_recognition_model": chart.get("model"),
                } if chart_text else {}),
                **({
                    "chart_text_refinement": chart["text_refinement"],
                } if chart_text and chart.get("text_refinement") else {}),
                "element_type": "chart",
                "layout_type": "chart",
            },
        })

    _associate_layout_titles(layout_detections or [], elements, tables, page_sizes)

    mapped = {
        "elements": elements,
        "tables": tables,
        "metadata": {
            "docling_version": docling_version,
            **({
                "layout_model": config["docling_layout_model"],
                "layout_score_threshold": config["docling_layout_score_threshold"],
            } if config.get("docling_layout_model") else {}),
            **({"ocr_cleanup": cleanup_diagnostics} if cleanup_diagnostics else {}),
            **({"table_dash_recovery": dash_recovery} if dash_recovery else {}),
        },
    }
    if layout_detections:
        mapped["layout_detections"] = layout_detections
    if source_format == "docx":
        apply_docx_semantics(mapped, source_bytes)
    return mapped


def _associate_layout_titles(
    detections: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    page_sizes: dict[int, tuple[float, float]],
) -> None:
    """Link title detections to the nearest aligned chart, figure, or table."""
    targets: list[dict[str, Any]] = []
    for table_index, table in enumerate(tables):
        metadata = table.get("metadata") or {}
        bbox = metadata.get("bbox")
        page_number = table.get("page_number", metadata.get("page_number"))
        if bbox and page_number is not None:
            targets.append({
                "type": "table", "index": table_index,
                "page_number": int(page_number), "bbox": list(map(float, bbox)),
                "metadata": metadata, "record": table,
            })
    for element_index, element in enumerate(elements):
        metadata = element.get("metadata") or {}
        label = normalize_element_label(
            metadata.get("element_type") or metadata.get("layout_type") or element.get("element_type")
        )
        if label not in {"chart", "figure"}:
            continue
        bbox = metadata.get("bbox")
        page_number = metadata.get("page_number")
        if bbox and page_number is not None:
            targets.append({
                "type": label, "index": element_index,
                "page_number": int(page_number), "bbox": list(map(float, bbox)),
                "metadata": metadata, "record": element,
            })

    for detection_index, detection in enumerate(detections):
        if detection.get("associated_target"):
            continue
        source_label = str(detection.get("label", "")).lower()
        if source_label not in {
            "figure_title", "diagram_title", "table_title", "title_table", "paragraph_title",
        }:
            continue
        title_bbox = detection.get("bbox")
        page_number = detection.get("page_number")
        if not title_bbox or page_number is None:
            continue
        title_bbox = list(map(float, title_bbox))
        page_number = int(page_number)
        page_width, page_height = page_sizes.get(page_number, (0.0, 0.0))
        candidates = []
        for target in targets:
            if target["page_number"] != page_number:
                continue
            if source_label in {"table_title", "title_table"} and target["type"] != "table":
                continue
            if source_label == "diagram_title" and target["type"] not in {"chart", "figure"}:
                continue
            score = _title_target_distance(
                title_bbox, target["bbox"], page_width, page_height
            )
            if score is not None:
                candidates.append((score, target))
        if not candidates:
            continue

        distance, target = min(candidates, key=lambda pair: pair[0])
        association = {
            "target_type": target["type"],
            "target_index": target["index"],
            "target_bbox": target["bbox"],
            "method": "nearest_aligned_bbox",
            "distance_score": round(distance, 4),
        }
        detection["associated_target"] = association
        title_text, title_elements = _text_inside_bbox(elements, page_number, title_bbox)
        if title_text:
            detection["associated_title_text"] = title_text
            target_metadata = target["metadata"]
            target_metadata.setdefault("associated_titles", []).append({
                "text": title_text,
                "source_label": source_label,
                "bbox": title_bbox,
                "layout_detection_index": detection_index,
            })
            target_metadata["title"] = title_text
            if target["type"] == "table":
                target["record"].setdefault("context", {})["title"] = title_text
                target_metadata["table_name"] = title_text
        for title_element in title_elements:
            title_element.setdefault("metadata", {})["associated_target"] = association


def associate_chart_title_regions(
    chart_regions: list[dict[str, Any]],
    detections: list[dict[str, Any]],
    page_sizes: dict[int, tuple[float, float]],
) -> None:
    """Attach only unambiguous title boxes so chart crops can include them."""
    title_boxes = [
        (index, detection)
        for index, detection in enumerate(detections)
        if str(detection.get("label", "")).lower()
        in {"figure_title", "diagram_title", "paragraph_title"}
        and detection.get("bbox")
        and detection.get("page_number") is not None
    ]
    chart_candidates: dict[int, list[tuple[float, int]]] = {}
    title_candidates: dict[int, list[tuple[float, int]]] = {}
    for chart_index, chart in enumerate(chart_regions):
        page_number = int(chart["page_no"])
        page_width, page_height = page_sizes.get(page_number, (0.0, 0.0))
        for title_index, title in title_boxes:
            if int(title["page_number"]) != page_number:
                continue
            score = _title_target_distance(
                list(map(float, title["bbox"])),
                list(map(float, chart["bbox"])),
                page_width,
                page_height,
            )
            if score is None:
                continue
            chart_candidates.setdefault(chart_index, []).append((score, title_index))
            title_candidates.setdefault(title_index, []).append((score, chart_index))

    def unique_best(candidates: list[tuple[float, int]]) -> tuple[float, int] | None:
        ordered = sorted(candidates)
        if len(ordered) > 1 and ordered[1][0] - ordered[0][0] < 0.2:
            return None
        return ordered[0] if ordered else None

    grouped_charts: set[int] = set()
    for title_index, candidates in title_candidates.items():
        title = detections[title_index]
        title_bbox = list(map(float, title["bbox"]))
        page_number = int(title["page_number"])
        page_width, page_height = page_sizes.get(page_number, (0.0, 0.0))
        ordered = sorted(candidates)
        nearby = [item for item in ordered if item[0] - ordered[0][0] < 0.2]
        if len(nearby) < 2:
            continue
        if any(index in grouped_charts for _, index in nearby):
            continue
        chart_boxes = [list(map(float, chart_regions[index]["bbox"])) for _, index in nearby]
        group_left = min(box[0] for box in chart_boxes)
        group_top = min(box[1] for box in chart_boxes)
        group_right = max(box[2] for box in chart_boxes)
        group_bottom = max(box[3] for box in chart_boxes)
        title_left, title_top, title_right, title_bottom = title_bbox
        centers_inside_title = all(
            title_left <= (box[0] + box[2]) / 2 <= title_right
            for box in chart_boxes
        )
        same_row = max(box[1] for box in chart_boxes) - min(box[1] for box in chart_boxes) <= page_height * 0.08
        title_covers_group = title_right - title_left >= (group_right - group_left) * 0.6
        if not (centers_inside_title and same_row and title_covers_group):
            continue

        group_id = f"{page_number}:{title_index}"
        recognition_bbox = [
            min(group_left, title_left), min(group_top, title_top),
            max(group_right, title_right), max(group_bottom, title_bottom),
        ]
        for score, chart_index in nearby:
            chart = chart_regions[chart_index]
            chart.update({
                "title_bbox": title_bbox,
                "title_detection_index": title_index,
                "title_match_score": round(score, 4),
                "recognition_bbox": recognition_bbox,
                "recognition_group_id": group_id,
                "recognition_group_bbox": [group_left, group_top, group_right, group_bottom],
                "recognition_group_member_bboxes": chart_boxes,
            })
            grouped_charts.add(chart_index)

    for chart_index, candidates in chart_candidates.items():
        if chart_index in grouped_charts:
            continue
        best_title = unique_best(candidates)
        if best_title is None:
            continue
        score, title_index = best_title
        best_chart = unique_best(title_candidates[title_index])
        if best_chart is None or best_chart[1] != chart_index:
            continue
        title = detections[title_index]
        title_bbox = list(map(float, title["bbox"]))
        chart = chart_regions[chart_index]
        chart_bbox = list(map(float, chart["bbox"]))
        chart["title_bbox"] = title_bbox
        chart["title_detection_index"] = title_index
        chart["title_match_score"] = round(score, 4)
        chart["recognition_bbox"] = [
            min(chart_bbox[0], title_bbox[0]),
            min(chart_bbox[1], title_bbox[1]),
            max(chart_bbox[2], title_bbox[2]),
            max(chart_bbox[3], title_bbox[3]),
        ]


def _title_target_distance(
    title: list[float], target: list[float], page_width: float, page_height: float,
) -> float | None:
    left, top, right, bottom = title
    target_left, target_top, target_right, target_bottom = target
    title_width, title_height = max(0.0, right - left), max(0.0, bottom - top)
    if not title_width or not title_height:
        return None
    overlap_x = max(0.0, min(right, target_right) - max(left, target_left))
    overlap_y = max(0.0, min(bottom, target_bottom) - max(top, target_top))
    horizontal_alignment = overlap_x / title_width
    center_offset = abs((left + right - target_left - target_right) / 2)
    center_limit = max((target_right - target_left) * 0.25, page_width * 0.025)
    horizontally_aligned = horizontal_alignment >= 0.35 or center_offset <= center_limit

    if horizontally_aligned and bottom <= target_top:
        gap = target_top - bottom
        max_gap = max(title_height * 2.5, page_height * 0.045)
        if gap <= max_gap:
            return gap / max_gap + (1.0 - min(1.0, horizontal_alignment))
    if horizontally_aligned and top >= target_bottom:
        gap = top - target_bottom
        max_gap = max(title_height * 2.5, page_height * 0.045)
        if gap <= max_gap:
            return 1.1 + gap / max_gap + (1.0 - min(1.0, horizontal_alignment))
    if overlap_y / title_height >= 0.5:
        if right <= target_left:
            gap = target_left - right
        elif left >= target_right:
            gap = left - target_right
        else:
            return 0.25
        max_gap = max(title_height * 1.5, page_width * 0.02)
        if gap <= max_gap:
            return 1.5 + gap / max_gap
    return None


def _text_inside_bbox(
    elements: list[dict[str, Any]], page_number: int, box: list[float],
) -> tuple[str, list[dict[str, Any]]]:
    left, top, right, bottom = box
    box_area = max(0.0, right - left) * max(0.0, bottom - top)
    if not box_area:
        return "", []
    matches = []
    for element in elements:
        metadata = element.get("metadata") or {}
        if metadata.get("page_number") != page_number:
            continue
        text = str(element.get("text") or "").strip()
        element_box = metadata.get("bbox")
        if not text or not element_box:
            continue
        element_box = list(map(float, element_box))
        x0, y0, x1, y1 = element_box
        area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        intersection = (
            max(0.0, min(right, x1) - max(left, x0))
            * max(0.0, min(bottom, y1) - max(top, y0))
        )
        if area and (
            intersection / area >= 0.5
            or (area <= box_area * 2 and intersection / box_area >= 0.5)
        ):
            matches.append((y0, x0, text, element))
    matches.sort(key=lambda item: (item[0], item[1]))
    unique_text = list(dict.fromkeys(item[2] for item in matches))
    return " ".join(unique_text), [item[3] for item in matches]


def _inside_chart_region(
    element_box: list[float],
    page_number: int,
    chart_regions: list[dict[str, Any]],
) -> bool:
    left, top, right, bottom = element_box
    area = max(0.0, right - left) * max(0.0, bottom - top)
    if not area:
        return False
    for chart in chart_regions:
        if int(chart.get("page_no", -1)) != page_number:
            continue
        chart_left, chart_top, chart_right, chart_bottom = map(float, chart["bbox"])
        intersection = (
            max(0.0, min(right, chart_right) - max(left, chart_left))
            * max(0.0, min(bottom, chart_bottom) - max(top, chart_top))
        )
        if intersection / area >= 0.5:
            return True
    return False


def _get_page_image(page: Any, cache: dict[int, Any], page_number: int | None):
    if page is None or page_number is None:
        return None
    page_number = int(page_number)
    if page_number in cache:
        return cache[page_number]
    try:
        import cv2
        import numpy as np

        page_image = getattr(page, "image", None)
        image = getattr(page_image, "pil_image", None)
        if image is None:
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
