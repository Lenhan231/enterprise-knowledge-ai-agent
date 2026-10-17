"""
PDF processor module for extracting and processing text from PDF documents.
"""

import logging
import math
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import fitz  # PyMuPDF
from core.document_processing.pipelines.pp_structurev3.processor import PPStructureV3Processor
from .table_extractor import PDFTableExtractor
from .scanned.ocr import PDFOCRProcessor
from .table_processor import PDFTableProcessor
from .text_extractor import PDFTextExtractor
from .table_chunks import PDFTableChunker
from .text_chunks import PDFTextChunker
from core.document_processing.chunking.config import ChunkingConfig

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
        self.config = dict(config or {})
        self.chunking = ChunkingConfig.from_config(self.config)
        self.config.setdefault("extract_images", False)
        self.config.setdefault(
            "ocr_fallback",
            self.config.get("parser_engine", "pymupdf_tesseract") == "pymupdf_tesseract",
        )
        self.config.setdefault("preserve_layout", True)
        self.config.setdefault("extract_tables", True)
        self.config.setdefault("paddle_chart_recognition", False)
        self.config.setdefault("paddle_formula_recognition", False)
        self.config["paddle_layout"] = bool(
            self.config.get("paddle_layout", False)
            or self.config.get("parser_engine") == "pp-structurev3"
            or self.config["paddle_formula_recognition"]
        )
        self.tesseract_data_dir = None
        if self.config["ocr_fallback"]:
            self.config.setdefault("tesseract_psm", 11)
            self.config.setdefault("tesseract_table_psm", 3)
            self.config.setdefault("ocr_language", "vie+eng")
            self.config.setdefault("tessdata_variant", "system")
            if self.config["tessdata_variant"] not in {"system", "fast", "best"}:
                raise ValueError("tessdata_variant must be system, fast, or best")
            if self.config["tessdata_variant"] != "system":
                env_name = f"TESSDATA_{self.config['tessdata_variant'].upper()}_DIR"
                configured_dir = os.getenv(env_name)
                if not configured_dir or not Path(configured_dir).is_dir():
                    raise ValueError(f"Set {env_name} to the selected traineddata directory")
                missing_languages = [
                    language for language in self.config["ocr_language"].split("+")
                    if not (Path(configured_dir) / f"{language}.traineddata").is_file()
                ]
                if missing_languages:
                    raise ValueError(f"{env_name} is missing traineddata for: {', '.join(missing_languages)}")
                self.tesseract_data_dir = Path(configured_dir)
            self.config.setdefault("ocr_orientation_detection", True)
            self.config.setdefault("ocr_deskew", True)
            self.config.setdefault("ocr_render_scale", float(os.getenv("DOCUMENT_OCR_RENDER_SCALE", "1.5")))
            self.config.setdefault("ocr_table_render_scale", float(os.getenv("DOCUMENT_OCR_TABLE_RENDER_SCALE", "2.5")))
            for setting in ("ocr_render_scale", "ocr_table_render_scale"):
                if not any(math.isclose(float(self.config[setting]), allowed, abs_tol=1e-9) for allowed in (1.5, 167 / 72, 2.5, 3.5)):
                    raise ValueError(f"{setting} must be one of 1.5, 167 DPI, 2.5, or 3.5")
        self.config.setdefault("vision_captioning", False)
        self.config.setdefault("vision_caption_max_images", 3)
        self.config.setdefault("table_chunk_replacement_threshold", 0.8)
        page_numbers = self.config.get("page_numbers")
        self.page_numbers = None if page_numbers is None else {int(number) for number in page_numbers}
        if self.page_numbers is not None and (not self.page_numbers or min(self.page_numbers) < 1):
            raise ValueError("page_numbers must contain positive PDF page numbers")
        if not 0.5 <= float(self.config["table_chunk_replacement_threshold"]) <= 1.0:
            raise ValueError("table_chunk_replacement_threshold must be between 0.5 and 1")

        # Initialize OCR if needed
        if self.config.get("ocr_fallback", False):
            self.ocr_available = shutil.which("tesseract") is not None
            if self.ocr_available:
                logger.info("Tesseract CLI OCR fallback enabled")
            else:
                logger.warning("tesseract executable not found, OCR fallback disabled")
        else:
            self.ocr_available = False

        self.ocr = PDFOCRProcessor(self.config, self.tesseract_data_dir, self.ocr_available)
        self.tables = PDFTableProcessor()
        self.text_chunker = PDFTextChunker(self.config, self.chunking)
        self.table_chunker = PDFTableChunker(self.config, self.chunking)
        self.text_extractor = PDFTextExtractor(
            self.config, self.page_numbers, self.ocr, self.tables,
            ocr_page=self._ocr_page,
            ocr_page_words=self._ocr_page_words,
            extract_images=self._extract_images,
        )

    # Keep the existing private helper hooks available while their implementations
    # live in the focused OCR and table modules.
    _looks_like_numeric_table = staticmethod(PDFOCRProcessor._looks_like_numeric_table)
    _remove_ocr_duplicates = staticmethod(PDFOCRProcessor._remove_ocr_duplicates)
    _has_meaningful_ocr_additions = staticmethod(PDFOCRProcessor._has_meaningful_ocr_additions)
    _restore_table_coordinates = staticmethod(PDFTableProcessor._restore_table_coordinates)
    _link_continued_tables = staticmethod(PDFTableProcessor._link_continued_tables)
    _extract_page_tables = staticmethod(PDFTableExtractor._extract_page_tables)
    _tables_from_aligned_words = staticmethod(PDFTableExtractor._tables_from_aligned_words)
    _ocr_period_header = staticmethod(PDFTableExtractor._ocr_period_header)
    _split_aligned_text_table = staticmethod(PDFTableExtractor._split_aligned_text_table)

    def _ocr_page_words(self, *args, **kwargs):
        return self.ocr._ocr_page_words(*args, **kwargs)

    def _ocr_page(self, *args, **kwargs):
        return self.ocr._ocr_page(*args, **kwargs)

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

        if self.config.get("parser_engine") == "docling":
            from core.document_processing.pipelines.docling.processor import DoclingProcessor

            result = DoclingProcessor(self.config).process(pdf_source, file_path, document)
            return self._caption_pdf_images(result, pdf_source, document)

        if self.config.get("paddle_layout", True) and self.config.get("parser_engine") != "mineru":
            try:
                result = self._process_with_pp_structurev3(pdf_source, file_path, document)
                return self._caption_pdf_images(result, pdf_source, document)
            except ImportError:
                logger.warning("PP-StructureV3 is unavailable; using the existing PDF/OCR path")
            except Exception:
                logger.exception("PP-StructureV3 processing failed; using the existing PDF/OCR path")

        if self.config.get("parser_engine") == "mineru":
            from core.document_processing.pipelines.mineru.processor import MineruProcessor

            result = MineruProcessor(self.config).process(pdf_source, file_path, document)
            return self._caption_pdf_images(result, pdf_source, document)

        extraction = self._extract_pdf(pdf_source, file_path=file_path)
        chunks = self.text_chunker.process(extraction, document)
        tables = extraction[2]
        chunks = self.table_chunker.replace_flat_table_chunks(chunks, tables)
        result = {"chunks": chunks, "tables": tables}
        return self._caption_pdf_images(result, pdf_source, document)

    def _replace_flat_table_chunks(self, chunks, tables):
        """Keep the existing PDF helper hook while table chunking has its own module."""
        return self.table_chunker.replace_flat_table_chunks(chunks, tables)

    @staticmethod
    def _remove_page_counter_footer(text: str) -> str:
        return PDFTextExtractor._remove_page_counter_footer(text)

    @staticmethod
    def _extract_page_headings(page, excluded_bboxes=()):
        return PDFTextExtractor._extract_page_headings(page, excluded_bboxes)

    @staticmethod
    def _extract_ocr_page_headings(text: str, *, allow_unstructured: bool = True):
        return PDFTextExtractor._extract_ocr_page_headings(
            text, allow_unstructured=allow_unstructured,
        )

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

    def _extract_pdf(self, source: Any, file_path: Optional[str] = None):
        return self.text_extractor._extract_pdf(source, file_path=file_path)

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


    def _process_with_pp_structurev3(self, source: Any, file_path: Optional[str], document: Dict[str, Any]) -> Dict[str, Any]:
        return PPStructureV3Processor(self.config).process(source, file_path, document)

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
        text, metadata, *_ = self._extract_pdf(file_path, file_path=file_path)
        return text, metadata

    def extract_text_from_binary(self, pdf_binary: bytes) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text and metadata from binary PDF content.

        Args:
            pdf_binary: Binary PDF content

        Returns:
            Tuple of (extracted text, metadata dictionary)
        """
        text, metadata, *_ = self._extract_pdf(pdf_binary)
        return text, metadata
