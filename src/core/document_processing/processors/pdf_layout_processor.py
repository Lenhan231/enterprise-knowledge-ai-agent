"""Optional PaddleOCR layout/table extraction path for PDF documents."""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

import fitz

from .text_processor import TextProcessor

logger = logging.getLogger(__name__)

_HEADING_PATTERNS = {
    "chapter": re.compile(r"^chapter\s*(?:[ivxlcdm]+|\d+)", re.IGNORECASE),
    "article": re.compile(r"^article\s*\d+(?:\.\d+)*", re.IGNORECASE),
    "subsection": re.compile(r"^(?:\d+(?:\.\d+)+|\([a-z0-9ivx]+\))\s+\S", re.IGNORECASE),
}


class _TableHTMLParser(HTMLParser):
    """Read table rows/cells from PaddleOCR's HTML table output."""

    def __init__(self):
        super().__init__()
        self.rows: List[List[str]] = []
        self._row: Optional[List[str]] = None
        self._cell: Optional[List[str]] = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

class PaddleLayoutProcessor:
    """Run the opt-in PP-Structure layout path using the supplied parser config."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def process(
        self, source: Any, file_path: Optional[str], document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run layout detection/OCR page by page, then chunk within detected sections."""
        from paddleocr import PPStructureV3

        if isinstance(source, bytes):
            pdf_document = fitz.open(stream=source, filetype="pdf")
        else:
            pdf_document = fitz.open(source)

        page_count = len(pdf_document)
        pipeline = PPStructureV3(
            device="cpu",
            layout_detection_model_name="PP-DocLayout-S",
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="PP-OCRv5_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            use_formula_recognition=bool(self.config["paddle_formula_recognition"]),
            use_chart_recognition=True,
            use_seal_recognition=False,
        )
        tables: List[Dict[str, Any]] = []
        page_blocks: List[Dict[str, Any]] = []
        try:
            for page_number, page in enumerate(pdf_document, start=1):
                render_scale = self.config["ocr_render_scale"]
                pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
                import numpy as np

                image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )
                output = next(iter(pipeline.predict(input=image)))
                result = getattr(output, "json", output)
                if not isinstance(result, dict):
                    result = result.to_dict()
                result = result.get("res", result)
                blocks = result.get("parsing_res_list", [])

                for block in blocks:
                    label = str(block.get("block_label", "text")).lower()
                    content = block.get("block_content")
                    bbox = block.get("block_bbox")
                    if label == "table":
                        parser = _TableHTMLParser()
                        parser.feed(str(content or ""))
                        if parser.rows:
                            columns = parser.rows[0]
                            rows = []
                            for row in parser.rows[1:]:
                                values = row + [None] * max(0, len(columns) - len(row))
                                rows.append(dict(zip(columns, values)))
                            table_index = sum(t["page_number"] == page_number for t in tables)
                            table = {
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
                                    "layout_model": "PP-DocLayout-S",
                                    "table_model": "PP-TableStructureV3",
                                },
                            }
                            tables.append(table)
                            table_text = " | ".join(columns) + "\n" + "\n".join(
                                " | ".join(str(row.get(column) or "") for column in columns)
                                for row in rows
                            )
                            if table_text.strip():
                                page_blocks.append(
                                    {
                                        "page_number": page_number,
                                        "type": "table",
                                        "text": table_text,
                                        "bbox": bbox,
                                        "section_path": [],
                                    }
                                )
                        continue

                    text = " ".join(str(content or "").split())
                    if not text:
                        continue
                    if label in ("header", "footer", "page_number"):
                        continue
                    heading_kind = next(
                        (
                            kind
                            for kind, pattern in _HEADING_PATTERNS.items()
                            if pattern.match(text)
                        ),
                        None,
                    )
                    # ponytail: titles over 180 chars are body text; use a ToC detector if real titles exceed this.
                    if len(text) > 180:
                        element_type = "paragraph"
                        heading_kind = None
                    elif label in ("doc_title", "paragraph_title") or heading_kind:
                        element_type = "title"
                        heading_kind = heading_kind or "section"
                    elif label in ("figure_title", "figure_caption"):
                        element_type = "figure_caption"
                    elif label == "table_title":
                        element_type = "table_caption"
                    elif label == "formula":
                        element_type = "formula"
                    elif label in ("image", "figure", "chart"):
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
                    if label in ("image", "figure", "chart"):
                        block_metadata["visual_content_extracted"] = True
                        block_metadata["source_layout_label"] = label
                    elif label == "formula":
                        block_metadata["contains_formula"] = True
                        block_metadata["formula_representation"] = "latex"
                    page_blocks.append(block_metadata)
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
                        if sections and _HEADING_PATTERNS["chapter"].match(sections[0])
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

        from .text_processor import TextProcessor

        text_processor = TextProcessor(self.config)
        chunks = []
        grouped: Dict[Tuple[int, Tuple[str, ...], str], List[Dict[str, Any]]] = {}
        for block in page_blocks:
            key = (block["page_number"], tuple(block["section_path"]), block["type"])
            grouped.setdefault(key, []).append(block)

        for (page_number, section_path, element_type), blocks in grouped.items():
            text = "\n".join(block["text"] for block in blocks)
            context_path = section_path[:-1] if element_type == "title" else section_path
            context_prefix = " > ".join(context_path)
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
            for chunk in text_processor.process({"text": text, "metadata": {}}):
                if context_prefix:
                    chunk["text"] = f"Section: {context_prefix}\n{chunk['text']}"
                chunk["metadata"].update(
                    {
                        "page_number": page_number,
                        "section_path": list(section_path),
                        "section_title": section_path[-1] if section_path else None,
                        "element_type": element_type,
                        "layout_type": element_type,
                        "bbox": bbox,
                        "bbox_coordinate_system": "rendered_page_pixel",
                                    "render_scale": render_scale,
                        "parser": "paddleocr.PP-StructureV3",
                        "layout_model": "PP-DocLayout-S",
                        "ocr_model": "PP-OCRv5_mobile",
                        "chunking_method": self.config.get("chunking_strategy", "fixed"),
                        **({
                            "contains_formula": True,
                            "formula_representation": "latex",
                        } if element_type == "formula" else {}),
                        **({
                            "visual_content_extracted": True,
                            "source_layout_label": blocks[0]["source_layout_label"],
                        } if element_type in {"image", "figure", "chart"} else {}),
                    }
                )
                chunk["metadata"]["chunk_index"] = len(chunks)
                chunks.append(chunk)

        metadata = {
            "page_count": page_count,
            "layout_parser": "paddleocr.PP-StructureV3",
        }
        if file_path:
            metadata["file_size_bytes"] = os.path.getsize(file_path)
        for chunk in chunks:
            chunk["metadata"].update(document.get("metadata", {}))
        return {"chunks": chunks, "tables": tables, "metadata": metadata}
