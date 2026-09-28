"""
PDF processor module for extracting and processing text from PDF documents.
"""

import logging
import os
import re
import shutil
import statistics
import subprocess
import csv
from html.parser import HTMLParser
from typing import Dict, List, Optional, Any, Tuple
import fitz  # PyMuPDF
from .text_processor import split_ranges

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


class PDFProcessor:
    """
    Handles PDF documents, extracting text and metadata.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the PDF processor with configuration options.

        Args:
            config: Configuration dictionary with processing options
        """
        self.config = config or {
            "extract_images": False,
            "ocr_fallback": False,
            "preserve_layout": True,
            "extract_tables": True,
        }
        self.config.setdefault("extract_tables", True)
        self.config.setdefault("paddle_layout", True)
        self.config.setdefault("paddle_formula_recognition", False)
        self.config.setdefault("tesseract_psm", 11)
        self.config.setdefault("tesseract_table_psm", 3)
        self.config.setdefault("ocr_render_scale", 1.5)
        self.config.setdefault("vision_captioning", False)
        self.config.setdefault("vision_caption_max_images", 3)

        # Initialize OCR if needed
        if self.config.get("ocr_fallback", False):
            self.ocr_available = shutil.which("tesseract") is not None
            if self.ocr_available:
                logger.info("Tesseract CLI OCR fallback enabled")
            else:
                logger.warning("tesseract executable not found, OCR fallback disabled")
        else:
            self.ocr_available = False

    def process(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a PDF document into chunks.

        Args:
            document: Document dictionary with PDF content

        Returns:
            A result with retrieval chunks and separately extracted tables
        """
        # Get file path from metadata if available
        file_path = None
        if "metadata" in document and "filepath" in document["metadata"]:
            file_path = document["metadata"]["filepath"]

        # Extract text and tables from the same opened PDF.
        if file_path and os.path.isfile(file_path):
            pdf_source = file_path
        elif "content" in document and isinstance(document["content"], bytes):
            pdf_source = document["content"]
        else:
            raise ValueError(
                "PDF document must have a valid filepath or binary content"
            )

        if self.config.get("paddle_layout", True):
            try:
                result = self._process_with_paddle(pdf_source, file_path, document)
                return self._caption_pdf_images(result, pdf_source, document)
            except ImportError:
                logger.warning("PaddleOCR is unavailable; using the existing PDF/OCR path")
            except Exception:
                logger.exception("Paddle layout processing failed; using the existing PDF/OCR path")

        pdf_text, pdf_metadata, tables, ocr_pages, page_headings = self._extract_pdf(
            pdf_source, file_path=file_path
        )

        # Merge extracted metadata with document metadata
        metadata = document.get("metadata", {}).copy()
        metadata.update(pdf_metadata)

        # Chunk each page separately so every chunk keeps accurate page provenance.
        chunks = []
        current_section_title = None
        page_pattern = re.compile(r"--- Page (\d+) ---")
        page_sections = page_pattern.split(pdf_text)
        for page_index in range(1, len(page_sections), 2):
            page_number = int(page_sections[page_index])
            page_text = page_sections[page_index + 1]
            page_text = " ".join(page_text.split())
            heading_positions = []
            search_from = 0
            for heading in page_headings.get(page_number, []):
                heading = " ".join(heading.split())
                position = page_text.find(heading, search_from)
                if position >= 0:
                    heading_positions.append((position, heading))
                    search_from = position + len(heading)
            heading_index = 0
            chunk_size = int(self.config.get("chunk_size", 800))
            overlap = int(self.config.get("chunk_overlap", 120))
            chunking_strategy = self.config.get("chunking_strategy", "sentence")
            for start, end in split_ranges(
                page_text,
                size=chunk_size,
                overlap=overlap,
                strategy=chunking_strategy,
            ):
                text = page_text[start:end].strip()
                if text:
                    while (
                        heading_index < len(heading_positions)
                        and heading_positions[heading_index][0] < end
                    ):
                        current_section_title = heading_positions[heading_index][1]
                        heading_index += 1
                    chunks.append({
                        "text": text,
                        "metadata": {
                            **metadata,
                            "chunk_index": len(chunks),
                            "page_number": page_number,
                            "chunk_strategy": "sentence" if chunking_strategy == "semantic" else chunking_strategy,
                            "chunk_size_chars": chunk_size,
                            "chunk_overlap_chars": overlap if chunking_strategy == "fixed" else 0,
                            "text_extraction_method": ocr_pages.get(
                                page_number, "pymupdf.get_text"
                            ),
                            "layout_type": "text",
                            "section_title": current_section_title,
                            "parser": "pymupdf",
                        },
                    })
        return self._caption_pdf_images({"chunks": chunks, "tables": tables}, pdf_source, document)

    def _caption_pdf_images(self, result: Dict[str, Any], source: Any, document: Dict[str, Any]) -> Dict[str, Any]:
        if not self.config["vision_captioning"]:
            return result

        pdf = fitz.open(stream=source, filetype="pdf") if isinstance(source, bytes) else fitz.open(source)
        try:
            candidates = []
            for page_number, page in enumerate(pdf, start=1):
                page_area = max(page.rect.get_area(), 1)
                for image in page.get_image_info(xrefs=True):
                    rect = fitz.Rect(image.get("bbox", (0, 0, 0, 0))).intersect(page.rect)
                    area_ratio = rect.get_area() / page_area
                    if 0.02 <= area_ratio <= 0.85:
                        candidates.append((area_ratio, page_number, rect))
            candidates.sort(reverse=True, key=lambda item: item[0])
            selected = candidates[:max(0, int(self.config["vision_caption_max_images"]))]
            if not selected:
                return result

            from core.llm.groq_provider import GroqProvider

            try:
                provider = GroqProvider()
            except Exception as error:
                logger.warning("Vision caption provider unavailable (%s)", type(error).__name__)
                return result
            try:
                metadata = document.get("metadata", {})
                for _, page_number, rect in selected:
                    try:
                        page = pdf[page_number - 1]
                        scale = min(2.0, 2048 / max(rect.width, rect.height))
                        image = page.get_pixmap(
                            matrix=fitz.Matrix(scale, scale), clip=rect, alpha=False,
                        ).tobytes("png")
                        caption = provider.caption_image(image, "image/png")
                    except Exception as error:
                        logger.warning(
                            "Vision caption failed for PDF page %d (%s)",
                            page_number, type(error).__name__,
                        )
                        continue
                    result["chunks"].append({
                        "text": f"AI-generated image caption (unverified): {caption}",
                        "metadata": {
                            **metadata,
                            "chunk_index": len(result["chunks"]),
                            "page_number": page_number,
                            "bbox": list(rect),
                            "bbox_coordinate_system": "pdf_points",
                            "element_type": "figure_caption",
                            "layout_type": "figure_caption",
                            "text_extraction_method": "groq_vision_caption",
                            "caption_model": provider.vision_model_name,
                            "is_model_generated": True,
                            "parser": "pymupdf.embedded_image_caption",
                        },
                    })
            finally:
                try:
                    provider.close()
                except Exception as error:
                    logger.warning("Could not close vision caption provider (%s)", type(error).__name__)
            return result
        finally:
            pdf.close()

    def _process_with_paddle(
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

    def extract_text(self, file_path: str) -> str:
        """
        Extract text from a PDF file.

        Args:
            file_path: Path to PDF file

        Returns:
            Extracted text content
        """
        text, _ = self.extract_text_and_metadata(file_path)
        return text

    def extract_text_and_metadata(self, file_path: str) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text and metadata from a PDF file.

        Args:
            file_path: Path to PDF file

        Returns:
            Tuple of (extracted text, metadata dictionary)
        """
        if not os.path.isfile(file_path):
            raise ValueError(f"PDF file not found: {file_path}")
        text, metadata, _, _, _ = self._extract_pdf(file_path, file_path=file_path)
        return text, metadata

    def extract_text_from_binary(self, pdf_binary: bytes) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text and metadata from binary PDF content.

        Args:
            pdf_binary: Binary PDF content

        Returns:
            Tuple of (extracted text, metadata dictionary)
        """
        text, metadata, _, _, _ = self._extract_pdf(pdf_binary)
        return text, metadata

    def _extract_pdf(
        self, source: Any, file_path: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]], Dict[int, str], Dict[int, List[str]]]:
        """Extract page text and table rows during one PDF traversal."""
        if isinstance(source, bytes):
            pdf_document = fitz.open(stream=source, filetype="pdf")
        else:
            pdf_document = fitz.open(source)

        extracted_text = []
        tables = []
        ocr_pages = {}
        ocr_table_words = {}
        page_headings = {}
        metadata = {
            "title": pdf_document.metadata.get("title", ""),
            "author": pdf_document.metadata.get("author", ""),
            "subject": pdf_document.metadata.get("subject", ""),
            "keywords": pdf_document.metadata.get("keywords", ""),
            "creator": pdf_document.metadata.get("creator", ""),
            "producer": pdf_document.metadata.get("producer", ""),
            "page_count": len(pdf_document),
        }
        if file_path:
            metadata["file_size_bytes"] = os.path.getsize(file_path)

        try:
            for page_num, page in enumerate(pdf_document):
                page_text = (
                    page.get_text("text")
                    if self.config.get("preserve_layout", True)
                    else page.get_text()
                )
                headings = self._extract_page_headings(page)
                if headings:
                    page_headings[page_num + 1] = headings
                native_text = page_text.strip()
                if (
                    self.ocr_available
                    and self.config.get("ocr_fallback", False)
                    and self._needs_ocr(page, native_text)
                ):
                    ocr_pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(self.config["ocr_render_scale"], self.config["ocr_render_scale"]),
                        alpha=False,
                    )
                    ocr_text = self._ocr_page(page, ocr_pixmap).strip()
                    if ocr_text:
                        if self.config.get("extract_tables", False) and self._looks_like_numeric_table(ocr_text):
                            ocr_table_words[page_num + 1] = self._ocr_page_words(page, ocr_pixmap)
                        if len(native_text) < 50:
                            page_text = ocr_text
                            ocr_pages[page_num + 1] = "tesseract"
                        else:
                            page_text = f"{page_text}\n{ocr_text}"
                            ocr_pages[page_num + 1] = "pymupdf+tesseract"
                        ocr_headings = self._extract_ocr_page_headings(ocr_text)
                        if ocr_headings:
                            page_headings[page_num + 1] = [
                                *page_headings.get(page_num + 1, []), *ocr_headings,
                            ]

                extracted_text.append(f"\n--- Page {page_num + 1} ---\n{page_text}")

                if self.config.get("extract_tables", False):
                    tables.extend(self._extract_page_tables(
                        page, page_num + 1, ocr_table_words.get(page_num + 1),
                        ocr_metadata=self._ocr_table_metadata(),
                    ))

                if self.config.get("extract_images", False) and file_path:
                    self._extract_images(page, page_num, file_path)
        except Exception as e:
            logger.error("Error extracting PDF content: %s", str(e))
            raise
        finally:
            pdf_document.close()

        return "\n".join(extracted_text), metadata, tables, ocr_pages, page_headings

    @staticmethod
    def _extract_page_headings(page) -> List[str]:
        """Return only short, visibly larger heading lines from native PDF text."""
        text_blocks = [block for block in page.get_text("dict").get("blocks", []) if block.get("type") == 0]
        lines = []
        font_sizes = []
        for block in text_blocks:
            for line in block.get("lines", []):
                spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
                text = " ".join("".join(span["text"] for span in spans).split())
                if not text:
                    continue
                size = max(float(span.get("size", 0)) for span in spans)
                font_sizes.extend(float(span.get("size", 0)) for span in spans)
                lines.append((line.get("bbox", [0, 0, 0, 0])[1], text, size))
        if not font_sizes:
            return []

        body_size = statistics.median(font_sizes)
        headings = []
        for _, text, size in sorted(lines):
            numbered_heading = any(pattern.match(text) for pattern in _HEADING_PATTERNS.values())
            visually_prominent = size >= body_size * 1.2
            sentence_like = text.endswith((".", ";", ","))
            if (
                2 <= len(text) <= 140
                and not sentence_like
                and (numbered_heading or visually_prominent)
                and not re.fullmatch(r"[\d\W]+", text)
            ):
                if not headings or headings[-1] != text:
                    headings.append(text)
        return headings

    @staticmethod
    def _extract_ocr_page_headings(text: str) -> List[str]:
        """Recover only explicitly numbered structural headings from OCR text."""
        headings = []
        for line in text.splitlines():
            line = " ".join(line.split()).strip(" .\t")
            if not line or len(line) > 140:
                continue
            if any(pattern.match(line) for pattern in _HEADING_PATTERNS.values()):
                if line not in headings:
                    headings.append(line)
        return headings

    @staticmethod
    def _needs_ocr(page, native_text: str) -> bool:
        """OCR sparse pages and mixed pages dominated by a large raster image."""
        if len(native_text) < 50:
            return True
        if len(native_text) >= 500:
            return False

        image_area = sum(
            fitz.Rect(image["bbox"]).intersect(page.rect).get_area()
            for image in page.get_image_info()
        )
        return image_area / max(page.rect.get_area(), 1) >= 0.25

    @staticmethod
    def _looks_like_numeric_table(text: str) -> bool:
        """Gate the extra OCR-box pass to OCR output with repeated numeric rows."""
        likely_rows = sum(
            len(re.findall(r"(?:[-+]?\d[\d.,]*|[-–—])", line)) >= 2
            for line in text.splitlines()
        )
        return likely_rows >= 3

    def _ocr_table_metadata(self) -> Dict[str, Any]:
        return {
            "engine": "tesseract",
            "language": self.config.get("ocr_language", "vie+eng"),
            "table_psm": self.config["tesseract_table_psm"],
            "render_scale": self.config["ocr_render_scale"],
        }

    @staticmethod
    def _extract_page_tables(
        page, page_number: int, ocr_words=None, ocr_metadata=None,
    ) -> List[Dict[str, Any]]:
        """Return detected page tables as column names and row dictionaries."""
        try:
            found_tables = page.find_tables().tables
        except Exception as e:
            logger.warning("Table detection failed on page %d: %s", page_number, e)
            return []

        extracted = []
        for table_index, table in enumerate(found_tables):
            matrix = table.extract()
            if not matrix:
                continue

            width = max((len(row) for row in matrix), default=0)
            header = getattr(table, "header", None)
            header_names = getattr(header, "names", None) or []
            columns = [str(name).strip() for name in header_names]
            columns = [name or f"column_{i + 1}" for i, name in enumerate(columns)]
            if len(columns) < width:
                columns.extend(
                    f"column_{i + 1}" for i in range(len(columns), width)
                )

            if not columns:
                columns = [f"column_{i + 1}" for i in range(width)]
                data_rows = matrix
            else:
                data_rows = matrix if getattr(header, "external", False) else matrix[1:]

            rows = []
            for row in data_rows:
                values = list(row) + [None] * max(0, len(columns) - len(row))
                rows.append(dict(zip(columns, values)))

            extracted.append(
                {
                    "page_number": page_number,
                    "table_index": table_index,
                    "columns": columns,
                    "rows": rows,
                    "metadata": {
                        "element_type": "table",
                        "layout_type": "table",
                        "table_extraction_method": "pymupdf.find_tables",
                    },
                }
            )
        if not extracted:
            words = page.get_text("words")
            numeric_rows: Dict[float, List[Tuple[float, float]]] = {}
            for word in words:
                x0, y0, x1, _, value = word[:5]
                value = str(value).strip().replace("−", "-")
                if re.fullmatch(r"(?:\(?[-+]?\d[\d.,]*\)?|[-–—])%?", value):
                    numeric_rows.setdefault(round((y0 + word[3]) / 2, 1), []).append((x0, x1))
            aligned_rows = 0
            for row in numeric_rows.values():
                positions = sorted(row)
                if any(right[0] - left[1] >= 40 for left, right in zip(positions, positions[1:])):
                    aligned_rows += 1
            if aligned_rows >= 3:
                try:
                    text_tables = page.find_tables(strategy="text").tables
                except Exception as e:
                    logger.warning("Text-based table detection failed on page %d: %s", page_number, e)
                else:
                    for table in text_tables:
                        extracted.extend(
                            PDFProcessor._split_aligned_text_table(
                                table, page, page_number, len(extracted), words,
                            )
                        )
        if not extracted and ocr_words:
            extracted = PDFProcessor._tables_from_aligned_words(
                ocr_words, page.rect, page_number, ocr_metadata=ocr_metadata,
            )
        return extracted

    @staticmethod
    def _tables_from_aligned_words(
        words, page_rect, page_number: int, ocr_metadata=None,
    ) -> List[Dict[str, Any]]:
        """Build borderless scanned tables from OCR word boxes and repeated values."""
        def is_number(value: str) -> bool:
            value = str(value or "").strip().replace("−", "-")
            return bool(re.fullmatch(r"(?:\(?[-+]?\d[\d.,]*\)?|[-–—])%?", value))

        ordered = sorted(words, key=lambda word: ((word[1] + word[3]) / 2, word[0]))
        row_groups = []
        for word in ordered:
            center_y = (word[1] + word[3]) / 2
            if not row_groups or abs(center_y - row_groups[-1][0]) > 4:
                row_groups.append([center_y, [word]])
            else:
                center, row = row_groups[-1]
                row.append(word)
                row_groups[-1][0] = sum((item[1] + item[3]) / 2 for item in row) / len(row)
        candidates = []
        for center_y, row in row_groups:
            numeric = [word for word in row if is_number(word[4])]
            numeric.sort(key=lambda word: word[0])
            if len(numeric) >= 2 and any(
                right[0] - left[2] >= 40 for left, right in zip(numeric, numeric[1:])
            ):
                candidates.append((center_y, sorted(row, key=lambda word: word[0]), numeric))
        if len(candidates) < 3:
            return []

        alignments = []
        for edge_index in (0, 2):
            edges = sorted(word[edge_index] for _, _, numeric in candidates for word in numeric)
            edge_clusters = []
            for edge in edges:
                if not edge_clusters or edge - edge_clusters[-1][-1] > 15:
                    edge_clusters.append([edge])
                else:
                    edge_clusters[-1].append(edge)
            supported = [cluster for cluster in edge_clusters if len(cluster) >= 3]
            if len(supported) >= 2:
                spread = sum(cluster[-1] - cluster[0] for cluster in supported)
                alignments.append((
                    sum(map(len, supported)), -spread, edge_index,
                    [sum(cluster) / len(cluster) for cluster in supported],
                ))
        if not alignments:
            return []
        _, _, alignment_edge, columns = max(alignments)
        gaps = [right - left for left, right in zip(columns, columns[1:])]
        typical_gap = statistics.median(gaps) if gaps else 0
        split_gap = max(page_rect.width * 0.15, typical_gap * 2.5)
        column_groups = []
        for column in columns:
            if column_groups and column - column_groups[-1][-1] <= split_gap:
                column_groups[-1].append(column)
            else:
                column_groups.append([column])
        column_groups = [group for group in column_groups if len(group) >= 2]
        if not column_groups:
            return []

        result = []
        for group_index, column_group in enumerate(column_groups):
            previous_right = column_groups[group_index - 1][-1] if group_index else page_rect.x0
            rows, row_boxes = [], []
            for center_y, row, numeric in candidates:
                aligned = []
                for edge in column_group:
                    match = min(numeric, key=lambda word: abs(word[alignment_edge] - edge))
                    aligned.append(match if abs(match[alignment_edge] - edge) <= 18 else None)
                if sum(word is not None for word in aligned) < 2:
                    continue
                first_value = next(word for word in aligned if word is not None)
                lower = previous_right + 3 if group_index else page_rect.x0
                label_words = [
                    word for word in row
                    if word[0] >= lower and word[2] <= first_value[0]
                    and not is_number(word[4])
                ]
                label = " ".join(word[4] for word in label_words).strip()
                if not label:
                    continue
                value_words = [word[4] if word is not None else "" for word in aligned]
                rows.append([label, *value_words])
                row_boxes.extend(label_words)
                row_boxes.extend(word for word in aligned if word is not None)
            if len(rows) < 3:
                continue
            headers = [f"value_{index}" for index in range(1, len(column_group) + 1)]
            columns_out = ["label", *headers]
            result.append({
                "page_number": page_number,
                "table_index": len(result),
                "columns": columns_out,
                "rows": [dict(zip(columns_out, row)) for row in rows],
                "metadata": {
                    "element_type": "table",
                    "layout_type": "table",
                    "table_extraction_method": "tesseract.tsv_aligned_columns",
                    "table_detection_strategy": "ocr_word_boxes",
                    **({"ocr": ocr_metadata} if ocr_metadata else {}),
                    "column_alignment": "left" if alignment_edge == 0 else "right",
                    "bbox": (
                        min(word[0] for word in row_boxes),
                        min(word[1] for word in row_boxes),
                        max(word[2] for word in row_boxes),
                        max(word[3] for word in row_boxes),
                    ),
                    "bbox_coordinate_system": "pdf_points",
                },
            })
        return result

    @staticmethod
    def _split_aligned_text_table(
        table, page, page_number: int, first_index: int, words=None,
    ) -> List[Dict[str, Any]]:
        """Rebuild borderless tables from repeated numeric columns in text grids."""
        matrix = table.extract()
        if not matrix:
            return []
        width = max((len(row) for row in matrix), default=0)
        if width < 3:
            return []
        matrix = [list(row) + [None] * (width - len(row)) for row in matrix]
        cells = getattr(table, "cells", [])
        if len(cells) != width * len(matrix):
            return []
        words = words if words is not None else page.get_text("words")

        def is_number(value: Any) -> bool:
            text = str(value or "").strip().replace("−", "-")
            return bool(re.fullmatch(r"(?:\(?[-+]?\d[\d.,]*\)?|[-–—])%?", text))

        numeric_columns = [
            column for column in range(width)
            if sum(is_number(row[column]) for row in matrix) >= 3
        ]
        groups: List[List[int]] = []
        for column in numeric_columns:
            if groups and column - groups[-1][-1] <= 2:
                groups[-1].append(column)
            else:
                groups.append([column])
        groups = [group for group in groups if len(group) >= 2]
        if not groups:
            return []

        result = []
        for group_index, numeric_group in enumerate(groups):
            previous_end = groups[group_index - 1][-1] + 1 if group_index else 0
            previous_numeric = groups[group_index - 1][-1] if group_index else None
            rows = []
            row_indices = []
            for row_index, matrix_row in enumerate(matrix):
                values = [matrix_row[column] for column in numeric_group]
                if sum(is_number(value) for value in values) < 2:
                    continue
                first_cell = cells[numeric_group[0] * len(matrix) + row_index]
                if not first_cell:
                    continue
                left = (
                    cells[previous_numeric * len(matrix) + row_index][2]
                    if previous_numeric is not None
                    and cells[previous_numeric * len(matrix) + row_index]
                    else table.bbox[0]
                )
                right = first_cell[0]
                center_y = (first_cell[1] + first_cell[3]) / 2
                label_words = [
                    word for word in words
                    if left - 1 <= word[0] and word[2] <= right + 1
                    and abs((word[1] + word[3]) / 2 - center_y) <= 4
                ]
                label = " ".join(word[4] for word in sorted(label_words, key=lambda word: word[0]))
                if not label:
                    continue
                rows.append([label, *values])
                row_indices.append(row_index)
            if len(rows) < 3:
                continue

            value_columns = []
            for value_index, column in enumerate(numeric_group, start=1):
                header = next((
                    str(row[column]).strip()
                    for row in matrix
                    if row[column] is not None
                    and re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", str(row[column]).strip())
                ), f"value_{value_index}")
                value_columns.append(header)
            columns = ["label", *value_columns]
            records = [dict(zip(columns, row)) for row in rows]
            label_cell = cells[previous_end * len(matrix) + row_indices[0]]
            last_value_cell = cells[numeric_group[-1] * len(matrix) + row_indices[-1]]
            bbox = (
                label_cell[0],
                cells[numeric_group[0] * len(matrix) + row_indices[0]][1],
                last_value_cell[2],
                last_value_cell[3],
            ) if label_cell and last_value_cell else table.bbox
            result.append({
                "page_number": page_number,
                "table_index": first_index + len(result),
                "columns": columns,
                "rows": records,
                "metadata": {
                    "element_type": "table",
                    "layout_type": "table",
                    "table_extraction_method": "pymupdf.find_tables_text_aligned_columns",
                    "table_detection_strategy": "text",
                    "numeric_columns": numeric_group,
                    "bbox": bbox,
                    "bbox_coordinate_system": "pdf_points",
                },
            })
        return result

    def _ocr_page(self, page, pixmap=None) -> str:
        """
        Perform OCR on a PDF page.

        Args:
            page: PyMuPDF page object

        Returns:
            Extracted text from OCR
        """
        if not self.ocr_available:
            return ""

        try:
            if pixmap is None:
                render_scale = self.config["ocr_render_scale"]
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(render_scale, render_scale), alpha=False,
                )
            return subprocess.run(
                ["tesseract", "stdin", "stdout", "-l", self.config.get("ocr_language", "vie+eng"), "--psm", str(self.config["tesseract_psm"])],
                input=pixmap.tobytes("png"), capture_output=True, check=True, timeout=90,
            ).stdout.decode("utf-8", errors="replace").strip()
        except (OSError, subprocess.SubprocessError) as e:
            logger.error("OCR error: %s", str(e))
            return ""

    def _ocr_page_words(self, page, pixmap=None) -> List[Tuple[float, float, float, float, str, int, int, int]]:
        """Return Tesseract word boxes in PDF points for scanned-table layout."""
        if not self.ocr_available:
            return []
        if pixmap is None:
            render_scale = self.config["ocr_render_scale"]
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(render_scale, render_scale), alpha=False,
            )
        try:
            output = subprocess.run(
                ["tesseract", "stdin", "stdout", "-l", self.config.get("ocr_language", "vie+eng"), "--psm", str(self.config["tesseract_table_psm"]), "tsv"],
                input=pixmap.tobytes("png"), capture_output=True,
                check=True, timeout=90,
            ).stdout.decode("utf-8", errors="replace")
            scale_x = pixmap.width / page.rect.width
            scale_y = pixmap.height / page.rect.height
            words = []
            for row in csv.DictReader(output.splitlines(), delimiter="\t"):
                if row.get("level") != "5" or not row.get("text", "").strip():
                    continue
                x0 = page.rect.x0 + int(row["left"]) / scale_x
                y0 = page.rect.y0 + int(row["top"]) / scale_y
                x1 = x0 + int(row["width"]) / scale_x
                y1 = y0 + int(row["height"]) / scale_y
                words.append((
                    x0, y0, x1, y1, row["text"],
                    int(row["block_num"]), int(row["line_num"]), int(row["word_num"]),
                ))
            return words
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
            logger.warning("OCR word-box extraction failed on page %d: %s", page.number + 1, e)
            return []

    def _extract_images(self, page, page_num: int, file_path: str) -> None:
        """
        Extract images from a PDF page.

        Args:
            page: PyMuPDF page object
            page_num: Page number
            file_path: Path to PDF file
        """
        try:
            # Create directory for images if it doesn't exist
            pdf_name = os.path.splitext(os.path.basename(file_path))[0]
            image_dir = f"{pdf_name}_images"
            os.makedirs(image_dir, exist_ok=True)

            # Extract images
            image_list = page.get_images(full=True)

            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]
                base_image = page.parent.extract_image(xref)

                if base_image:
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    image_path = os.path.join(
                        image_dir, f"page{page_num+1}_img{img_index+1}.{image_ext}"
                    )

                    with open(image_path, "wb") as img_file:
                        img_file.write(image_bytes)

                    logger.debug("Extracted image: %s", image_path)

        except Exception as e:
            logger.error(
                "Error extracting images from page %d: %s", page_num + 1, str(e)
            )
