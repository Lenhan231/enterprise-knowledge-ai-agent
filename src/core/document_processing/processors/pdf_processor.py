"""
PDF processor module for extracting and processing text from PDF documents.
"""

import logging
import os
import re
import statistics
import shutil
import subprocess
import csv
from typing import Dict, List, Optional, Any, Tuple
import fitz  # PyMuPDF
from .pdf_layout_processor import PaddleLayoutProcessor, _HEADING_PATTERNS
from .pdf_table_extractor import PDFTableExtractor
from .text_processor import split_ranges

logger = logging.getLogger(__name__)


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
        self.config.setdefault("ocr_table_render_scale", 2.5)
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
        metadata.pop("uploaded_by", None)
        metadata.pop("title", None)
        metadata.pop("author", None)
        metadata.pop("subject", None)
        metadata.pop("keywords", None)
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


    def _process_with_paddle(self, source: Any, file_path: Optional[str], document: Dict[str, Any]) -> Dict[str, Any]:
        return PaddleLayoutProcessor(self.config).process(source, file_path, document)

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
                            table_render_scale = self.config["ocr_table_render_scale"]
                            table_pixmap = (
                                ocr_pixmap
                                if table_render_scale == self.config["ocr_render_scale"]
                                else page.get_pixmap(
                                    matrix=fitz.Matrix(table_render_scale, table_render_scale),
                                    alpha=False,
                                )
                            )
                            ocr_table_words[page_num + 1] = self._ocr_page_words(page, table_pixmap)
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
            "render_scale": self.config["ocr_table_render_scale"],
        }


    @staticmethod
    def _extract_page_tables(page, page_number: int, ocr_words=None, ocr_metadata=None):
        return PDFTableExtractor._extract_page_tables(page, page_number, ocr_words, ocr_metadata)

    @staticmethod
    def _tables_from_aligned_words(words, page_rect, page_number: int, ocr_metadata=None):
        return PDFTableExtractor._tables_from_aligned_words(words, page_rect, page_number, ocr_metadata)

    @staticmethod
    def _ocr_period_header(value: str) -> Optional[str]:
        return PDFTableExtractor._ocr_period_header(value)

    @staticmethod
    def _split_aligned_text_table(table, page, page_number: int, first_index: int, words=None):
        return PDFTableExtractor._split_aligned_text_table(table, page, page_number, first_index, words)

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
