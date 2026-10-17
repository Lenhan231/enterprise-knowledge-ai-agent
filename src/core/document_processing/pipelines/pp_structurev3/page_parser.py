"""Parse PP-StructureV3 page predictions into ordered blocks and table records."""

from __future__ import annotations

from typing import Any

import fitz

from core.document_processing.headings import HEADING_PATTERNS
from core.document_processing.pipelines.helpers.table_parser import parse_html_table


def parse_pages(pdf_document, pipeline, config: dict[str, Any]):
    """Render pages, run PP-StructureV3, and return normalized blocks and tables."""
    tables: list[dict[str, Any]] = []
    page_blocks: list[dict[str, Any]] = []
    render_scale = config.get("paddle_render_scale")
    if render_scale is None:
        render_scale = config.get("ocr_render_scale", 1.5)

    for page_number, page in enumerate(pdf_document, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
        import numpy as np

        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        output = next(iter(pipeline.predict(input=image)))
        result = getattr(output, "json", output)
        if not isinstance(result, dict):
            result = result.to_dict()
        blocks = result.get("res", result).get("parsing_res_list", [])

        for block in blocks:
            label = str(block.get("block_label", "text")).lower()
            content = block.get("block_content")
            bbox = block.get("block_bbox")
            if label == "table":
                table_grid = parse_html_table(str(content or ""))
                if table_grid:
                    columns = table_grid[0]
                    rows = [
                        dict(zip(columns, [cell or None for cell in row]))
                        for row in table_grid[1:]
                    ]
                    table_index = sum(table["page_number"] == page_number for table in tables)
                    tables.append({
                        "page_number": page_number,
                        "table_index": table_index,
                        "columns": columns,
                        "rows": rows,
                        "metadata": {
                            "element_type": "table",
                            "layout_type": "table",
                            "bbox": bbox,
                            "bbox_coordinate_system": "rendered_page_pixel",
                            "render_scale": render_scale,
                            "parser": "paddleocr.PP-StructureV3",
                            "layout_model": config.get("paddle_layout_model", "PP-DocLayout-S"),
                            "table_model": config.get("paddle_table_model", "PP-TableStructureV3"),
                            "ocr": {
                                "engine": "paddleocr.PP-StructureV3",
                                "detection_model": config.get(
                                    "paddle_detection_model", "PP-OCRv5_mobile_det",
                                ),
                                "recognition_model": config.get(
                                    "paddle_recognition_model", "PP-OCRv5_mobile_rec",
                                ),
                                "render_scale": render_scale,
                            },
                            "table_extraction_method": config.get(
                                "paddle_table_model", "PP-TableStructureV3",
                            ),
                            "table_detection_strategy": config.get(
                                "paddle_layout_model", "PP-DocLayout-S",
                            ),
                        },
                    })
                    page_blocks.append({
                        "page_number": page_number,
                        "type": "table",
                        "text": "",
                        "bbox": bbox,
                        "section_path": [],
                        "table_index": table_index,
                    })
                continue

            text = " ".join(str(content or "").split())
            if not text or label in {"header", "footer", "page_number"}:
                continue
            heading_kind = next(
                (kind for kind, pattern in HEADING_PATTERNS.items() if pattern.match(text)),
                None,
            )
            # ponytail: titles over 180 chars are body text; use a ToC detector if real titles exceed this.
            if len(text) > 180:
                element_type, heading_kind = "paragraph", None
            elif label in {"doc_title", "paragraph_title"} or heading_kind:
                element_type = "title"
                heading_kind = heading_kind or "section"
            elif label in {"figure_title", "figure_caption"}:
                element_type = "figure_caption"
            elif label == "table_title":
                element_type = "table_caption"
            elif label == "formula":
                element_type = "formula"
            elif label in {"image", "figure", "chart"}:
                element_type = label
            else:
                element_type = "paragraph"
            block_metadata = {
                "page_number": page_number,
                "type": element_type,
                "text": text,
                "bbox": bbox,
                "section_path": [],
                "heading_kind": heading_kind,
            }
            if label in {"image", "figure", "chart"}:
                block_metadata.update({"visual_content_extracted": True, "source_layout_label": label})
            elif label == "formula":
                block_metadata.update({"contains_formula": True, "formula_representation": "latex"})
            page_blocks.append(block_metadata)
    return tables, page_blocks, render_scale
