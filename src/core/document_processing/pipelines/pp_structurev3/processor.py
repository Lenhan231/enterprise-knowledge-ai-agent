"""Optional PaddleOCR layout/table extraction path for PDF documents."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import fitz

from core.document_processing.headings import HEADING_PATTERNS, section_metadata
from .page_parser import parse_pages


class PPStructureV3Processor:
    """Run PP-Structure layout and return ordered semantic blocks and tables."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def process_image(
        self, content: bytes, suffix: str, document: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Wrap one raster input as a single-page PDF for PP-StructureV3."""
        image = fitz.open(stream=content, filetype=suffix.lstrip("."))
        try:
            pdf_bytes = image.convert_to_pdf()
        finally:
            image.close()
        return self.process(pdf_bytes, None, document)

    def process(
        self, source: Any, file_path: Optional[str], document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run layout detection/OCR page by page, then chunk within detected sections."""
        from paddleocr import PPStructureV3

        if isinstance(source, bytes):
            pdf_document = fitz.open(stream=source, filetype="pdf")
        else:
            pdf_document = fitz.open(source)

        pipeline = PPStructureV3(
            device=self.config.get("paddle_device", "cpu"),
            enable_mkldnn=False,
            layout_detection_model_name=self.config.get("paddle_layout_model", "PP-DocLayout-S"),
            text_detection_model_name=self.config.get("paddle_detection_model", "PP-OCRv5_mobile_det"),
            text_recognition_model_name=self.config.get("paddle_recognition_model", "PP-OCRv5_mobile_rec"),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            use_formula_recognition=bool(self.config["paddle_formula_recognition"]),
            use_chart_recognition=bool(self.config.get("paddle_chart_recognition", False)),
            use_seal_recognition=False,
        )
        page_count = len(pdf_document)
        try:
            tables, page_blocks, render_scale = parse_pages(pdf_document, pipeline, self.config)
        finally:
            pdf_document.close()

        sections: List[str] = []
        for block in page_blocks:
            if block["type"] == "title":
                heading_kind = block.get("heading_kind")
                if heading_kind == "chapter":
                    sections = [block["text"]]
                elif heading_kind == "article":
                    chapter = (
                        sections[:1]
                        if sections and HEADING_PATTERNS["chapter"].match(sections[0])
                        else []
                    )
                    sections = chapter + [block["text"]]
                elif heading_kind == "subsection":
                    sections = sections[:2] + [block["text"]]
                elif len(sections) > 1:
                    sections = sections[:2] + [block["text"]]
                else:
                    sections = [block["text"]]
            block["section_path"] = sections.copy()
            block["heading_level"] = len(sections) or None

        elements = []
        grouped: Dict[Tuple[int, Tuple[str, ...], str, Optional[int]], List[Dict[str, Any]]] = {}
        for block in page_blocks:
            key = (
                block["page_number"], tuple(block["section_path"]), block["type"],
                block.get("table_index") if block["type"] == "table" else None,
            )
            grouped.setdefault(key, []).append(block)

        for (page_number, section_path, element_type, table_index), blocks in grouped.items():
            text = "\n".join(block["text"] for block in blocks)
            boxes = [block["bbox"] for block in blocks if block.get("bbox")]
            bbox = (
                [
                    min(box[0] for box in boxes),
                    min(box[1] for box in boxes),
                    max(box[2] for box in boxes),
                    max(box[3] for box in boxes),
                ]
                if boxes
                else None
            )
            if element_type == "table":
                table_ref = next(
                    index for index, item in enumerate(tables)
                    if item["page_number"] == page_number and item["table_index"] == table_index
                )
                elements.append({
                    "element_type": "table", "table_ref": table_ref,
                    "metadata": {
                        "page_number": page_number,
                        "section_path": list(section_path),
                        **section_metadata(
                            section_path[-1] if section_path else None,
                            len(section_path) or None,
                        ),
                        "bbox": bbox,
                        "bbox_coordinate_system": "rendered_page_pixel",
                        "render_scale": render_scale,
                        "parser": "paddleocr.PP-StructureV3",
                        "layout_model": self.config.get("paddle_layout_model", "PP-DocLayout-S"),
                        "ocr_model": self.config.get("paddle_recognition_model", "PP-OCRv5_mobile_rec"),
                        "table_index": table_index,
                    },
                })
                continue
            elements.append({
                "text": text,
                "metadata": {
                        "page_number": page_number,
                        "section_path": list(section_path),
                        **section_metadata(
                            section_path[-1] if section_path else None,
                            len(section_path) or None,
                        ),
                        "element_type": element_type,
                        "layout_type": element_type,
                        **({"table_index": table_index} if table_index is not None else {}),
                        "bbox": bbox,
                        "bbox_coordinate_system": "rendered_page_pixel",
                        "render_scale": render_scale,
                        "parser": "paddleocr.PP-StructureV3",
                        "layout_model": self.config.get("paddle_layout_model", "PP-DocLayout-S"),
                        "ocr_model": self.config.get("paddle_recognition_model", "PP-OCRv5_mobile_rec"),
                        **({
                            "contains_formula": True,
                            "formula_representation": "latex",
                        } if element_type == "formula" else {}),
                        **({
                            "visual_content_extracted": True,
                            "source_layout_label": blocks[0]["source_layout_label"],
                        } if element_type in {"image", "figure", "chart"} else {}),
                },
            })

        metadata = {
            "page_count": page_count,
            "layout_parser": "paddleocr.PP-StructureV3",
        }
        if file_path:
            metadata["file_size_bytes"] = os.path.getsize(file_path)
        for element in elements:
            element["metadata"].update(document.get("metadata", {}))
        return {"elements": elements, "tables": tables, "metadata": metadata}
