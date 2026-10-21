"""Built-in PyMuPDF and Tesseract parser pipeline for PDFs."""

import logging
import math
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from .table_extractor import PDFTableExtractor
from .scanned.pdf_ocr import PDFOCRProcessor
from .table_processor import PDFTableProcessor
from .text_extractor import PDFTextExtractor
from .text_chunks import PDFTextChunker
from .pdf_images import caption_pdf_images, extract_pdf_images

logger = logging.getLogger(__name__)

class BuiltInProcessor:
    """Extract PDF text and tables with PyMuPDF and optional Tesseract OCR."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the PDF processor with configuration options.

        Args:
            config: Configuration dictionary with processing options
        """
        self.config = dict(config or {})
        self.config.setdefault("extract_images", False)
        self.config.setdefault(
            "ocr_fallback",
            self.config.get("parser_engine", "built_in") == "built_in",
        )
        self.config.setdefault("preserve_layout", True)
        self.config.setdefault("extract_tables", True)
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
        page_numbers = self.config.get("page_numbers")
        self.page_numbers = None if page_numbers is None else {int(number) for number in page_numbers}
        if self.page_numbers is not None and (not self.page_numbers or min(self.page_numbers) < 1):
            raise ValueError("page_numbers must contain positive PDF page numbers")

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
        self.text_chunker = PDFTextChunker(self.config)
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
        Parse a PDF into semantic text blocks and structured tables.

        Args:
            document: Document dictionary with PDF content

        Returns:
            Blocks and tables; shared chunking runs in DocumentProcessor.
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

        extraction = self._extract_pdf(pdf_source, file_path=file_path)
        elements = self.text_chunker.process(extraction, document)
        tables = extraction[2]
        for table_index, table in enumerate(tables):
            table.setdefault("table_index", table_index)
            table.setdefault("metadata", {}).setdefault("parser", "pymupdf")
            elements.append({
                "element_type": "table", "table_ref": table_index,
                "metadata": {**table["metadata"], "table_index": table["table_index"]},
            })
        result = {"elements": elements, "tables": tables}
        return self._caption_pdf_images(result, pdf_source, document)

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
        extract_pdf_images(page, page_num, file_path)

    def _extract_pdf(self, source: Any, file_path: Optional[str] = None):
        return self.text_extractor._extract_pdf(source, file_path=file_path)

    def _caption_pdf_images(self, result: Dict[str, Any], source: Any, document: Dict[str, Any]) -> Dict[str, Any]:
        return caption_pdf_images(self.config, result, source, document)


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
