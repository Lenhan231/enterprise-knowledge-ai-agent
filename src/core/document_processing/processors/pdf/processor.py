"""
PDF processor module for extracting and processing text from PDF documents.
"""

import logging
import math
import os
import re
import statistics
import shutil
import subprocess
import csv
import unicodedata
from io import BytesIO
from pathlib import Path
from difflib import SequenceMatcher
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import fitz  # PyMuPDF
from .layout_processor import PaddleLayoutProcessor, _HEADING_PATTERNS
from .table_extractor import PDFTableExtractor
from core.chunking.text_chunker import ChunkingConfig, split_ranges

logger = logging.getLogger(__name__)

_TESSERACT_BOOLEAN_OPTIONS = (
    "preserve_interword_spaces",
    "load_system_dawg",
    "load_freq_dawg",
    "tessedit_do_invert",
    "textord_tablefind_recognize_tables",
    "textord_tabfind_find_tables",
    "lstm_use_matrix",
)
_TESSERACT_NUMERIC_OPTIONS = {
    "thresholding_method": {0, 1, 2},
    "lstm_rating_coefficient": {3, 5, 7},
}


def _tesseract_config_args(config: Dict[str, Any]) -> List[str]:
    """Build Tesseract -c arguments from the small OCR Lab allowlist."""
    settings = config.get("tesseract_config", {})
    args = []
    for name in _TESSERACT_BOOLEAN_OPTIONS:
        if name in settings:
            args.extend(["-c", f"{name}={int(bool(settings[name]))}"])
    for name, allowed_values in _TESSERACT_NUMERIC_OPTIONS.items():
        if name in settings:
            value = int(settings[name])
            if value not in allowed_values:
                raise ValueError(f"Unsupported Tesseract setting: {name}={value}")
            args.extend(["-c", f"{name}={value}"])
    return args


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
        self.config.setdefault("ocr_fallback", True)
        self.config.setdefault("preserve_layout", True)
        self.config.setdefault("extract_tables", True)
        self.config.setdefault("paddle_chart_recognition", False)
        self.config.setdefault("paddle_formula_recognition", False)
        self.config["paddle_layout"] = bool(
            self.config.get("paddle_layout", False)
            or self.config.get("parser_engine") == "pp-structurev3"
            or self.config["paddle_formula_recognition"]
        )
        self.config.setdefault("tesseract_psm", 11)
        self.config.setdefault("tesseract_table_psm", 3)
        self.config.setdefault("ocr_language", "vie+eng")
        self.config.setdefault("tessdata_variant", "system")
        if self.config["tessdata_variant"] not in {"system", "fast", "best"}:
            raise ValueError("tessdata_variant must be system, fast, or best")
        self.tesseract_data_dir = None
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

    def _tesseract_cli_config_args(self) -> List[str]:
        args = []
        if self.tesseract_data_dir is not None:
            args.extend(["--tessdata-dir", str(self.tesseract_data_dir)])
        return [*args, *_tesseract_config_args(self.config)]

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

        if self.config.get("paddle_layout", True) and self.config.get("parser_engine") != "mineru":
            try:
                result = self._process_with_paddle(pdf_source, file_path, document)
                return self._caption_pdf_images(result, pdf_source, document)
            except ImportError:
                logger.warning("PaddleOCR is unavailable; using the existing PDF/OCR path")
            except Exception:
                logger.exception("Paddle layout processing failed; using the existing PDF/OCR path")

        if self.config.get("parser_engine") == "mineru":
            from .mineru_processor import MineruProcessor

            result = MineruProcessor(self.config).process(pdf_source, file_path, document)
            return self._caption_pdf_images(result, pdf_source, document)

        pdf_text, pdf_metadata, tables, ocr_pages, page_headings, ocr_rotations, ocr_deskews = self._extract_pdf(
            pdf_source, file_path=file_path
        )
        ocr_render_scales = pdf_metadata.pop("_ocr_render_scales", {})
        ocr_details = pdf_metadata.pop("_ocr_details", {})
        ocr_diagnostics = pdf_metadata.pop("_ocr_diagnostics", {})

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
            diagnostics_attached = False
            for start, end in split_ranges(
                page_text,
                size=self.chunking.size,
                overlap=self.chunking.overlap,
                strategy=self.chunking.strategy,
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
                            "chunk_strategy": self.chunking.strategy,
                            "chunk_size_chars": self.chunking.size,
                            "chunk_overlap_chars": self.chunking.overlap if self.chunking.strategy == "fixed" else 0,
                            "text_extraction_method": ocr_pages.get(
                                page_number, "pymupdf.get_text"
                            ),
                            "layout_type": "text",
                            "section_title": current_section_title,
                            "parser": "pymupdf",
                            **({"ocr_diagnostics": ocr_diagnostics[page_number]}
                               if page_number in ocr_diagnostics and not diagnostics_attached else {}),
                            **({
                                "ocr": {
                                    "engine": "tesseract",
                                    "language": self.config["ocr_language"],
                                    "page_psm": ocr_details.get(page_number, {}).get(
                                        "page_psm", self.config["tesseract_psm"],
                                    ),
                                    "render_scale": ocr_render_scales.get(
                                        page_number, self.config["ocr_render_scale"],
                                    ),
                                    **ocr_details.get(page_number, {}),
                                    **({"orientation_correction_degrees": ocr_rotations[page_number]}
                                       if page_number in ocr_rotations else {}),
                                    **({"deskew_correction_degrees": ocr_deskews[page_number]}
                                       if page_number in ocr_deskews else {}),
                                },
                            } if page_number in ocr_pages else {}),
                        },
                    })
                    if page_number in ocr_diagnostics:
                        diagnostics_attached = True
        chunks = self._replace_flat_table_chunks(chunks, tables)
        return self._caption_pdf_images({"chunks": chunks, "tables": tables}, pdf_source, document)

    @staticmethod
    def _remove_page_counter_footer(text: str) -> str:
        """Drop a standalone trailing page counter while preserving page provenance."""
        lines = text.splitlines()
        for index in range(len(lines) - 1, -1, -1):
            line = lines[index].strip()
            if not line:
                continue
            if len(line) <= 180 and re.search(
                r"\b(?:page|trang)\s+\d+\s*(?:/|of|trên)\s*\d+\s*$",
                line,
                re.IGNORECASE,
            ):
                lines.pop(index)
            break
        return "\n".join(lines).strip()

    def _replace_flat_table_chunks(self, chunks: List[Dict[str, Any]], tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Use row/column-aware table text when it safely matches a same-page chunk.

        Unmatched table fragments are added without deleting source text. This
        keeps uncertain parser output searchable while avoiding a lossy swap.
        """
        threshold = float(self.config["table_chunk_replacement_threshold"])
        replacements: Dict[int, Dict[str, Any]] = {}
        additions: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        claimed_chunks = set()

        for table in tables:
            page_number = int(table.get("page_number") or 0)
            table_context = table.get("context") or {}
            table_title = str(table_context.get("table_title") or "").strip()
            fragments = self._structured_table_fragments(
                table, self.chunking.size, table_title=table_title,
            )
            for fragment_index, fragment in enumerate(fragments):
                best = None
                for chunk_index, chunk in enumerate(chunks):
                    if chunk_index in claimed_chunks:
                        continue
                    if int(chunk.get("metadata", {}).get("page_number") or 0) != page_number:
                        continue
                    chunk_coverage, table_coverage = self._table_match_coverage(
                        chunk.get("text", ""), fragment["match_text"],
                    )
                    score = min(chunk_coverage, table_coverage)
                    if best is None or score > best[0]:
                        best = (score, chunk_coverage, table_coverage, chunk_index)

                matched_chunk_index = None
                chunk_coverage = table_coverage = 0.0
                best_chunk_index = None
                if best:
                    _, chunk_coverage, table_coverage, best_chunk_index = best
                if best and chunk_coverage >= threshold and table_coverage >= threshold:
                    matched_chunk_index = best_chunk_index
                    claimed_chunks.add(matched_chunk_index)

                context_chunk_index = matched_chunk_index if matched_chunk_index is not None else best_chunk_index
                source_metadata = (
                    chunks[context_chunk_index].get("metadata", {})
                    if context_chunk_index is not None
                    else next((
                        chunk.get("metadata", {}) for chunk in chunks
                        if int(chunk.get("metadata", {}).get("page_number") or 0) == page_number
                    ), chunks[0].get("metadata", {}) if chunks else {})
                )
                metadata = {
                    **source_metadata,
                    **table.get("metadata", {}),
                    "page_number": page_number,
                    "chunk_strategy": source_metadata.get("chunk_strategy", "sentence"),
                    "layout_type": "table",
                    "element_type": "table",
                    "table_index": table.get("table_index"),
                    "table_fragment_index": fragment_index,
                    "table_fragment_count": len(fragments),
                    **({"table_title": table_title} if table_title else {}),
                    "table_extraction_method": table.get("metadata", {}).get("table_extraction_method"),
                    "parser": "pymupdf.structured_table_chunk",
                    "table_chunk_match_threshold": threshold,
                    "table_chunk_match": {
                        "matched_source_chunk": matched_chunk_index is not None,
                        "chunk_token_coverage": round(chunk_coverage, 4),
                        "table_token_coverage": round(table_coverage, 4),
                        "best_candidate_chunk_index": (
                            chunks[best_chunk_index].get("metadata", {}).get("chunk_index")
                            if best_chunk_index is not None else None
                        ),
                        "matched_source_chunk_index": (
                            chunks[matched_chunk_index].get("metadata", {}).get("chunk_index")
                            if matched_chunk_index is not None else None
                        ),
                    },
                }
                table_chunk = {"text": fragment["text"], "metadata": metadata}
                if matched_chunk_index is not None:
                    replacements[matched_chunk_index] = table_chunk
                else:
                    additions[page_number].append(table_chunk)

        by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        unpaged = []
        for index, chunk in enumerate(chunks):
            page_number = int(chunk.get("metadata", {}).get("page_number") or 0)
            if page_number:
                by_page[page_number].append(replacements.get(index, chunk))
            else:
                unpaged.append(replacements.get(index, chunk))

        result = []
        for page_number in sorted(set(by_page) | set(additions)):
            result.extend(by_page.get(page_number, []))
            result.extend(additions.get(page_number, []))
        result.extend(unpaged)
        for index, chunk in enumerate(result):
            chunk["metadata"]["chunk_index"] = index
        return result

    @staticmethod
    def _structured_table_fragments(
        table: Dict[str, Any], max_chars: int, *, table_title: str = "",
    ) -> List[Dict[str, str]]:
        columns = [str(column or f"column_{index + 1}").strip() for index, column in enumerate(table.get("columns", []))]
        rows = table.get("rows", [])
        if not columns and rows:
            columns = list(dict.fromkeys(str(key) for row in rows for key in row))
        if not columns:
            return []

        column_line = "Columns: " + " | ".join(columns)
        title_line = f"Table: {table_title}" if table_title else ""
        context_length = len(title_line) + (1 if title_line else 0)
        row_lines = []
        for row_index, row in enumerate(rows, start=1):
            cells = [str(row.get(column) if row.get(column) is not None else "").strip() for column in columns]
            if any(cells):
                row_lines.append((f"Row {row_index}: " + " | ".join(
                    f"{column}: {value}" for column, value in zip(columns, cells)
                ), cells))
        if not row_lines:
            return []

        groups = []
        current = []
        current_length = context_length + len(column_line)
        for line, cells in row_lines:
            if current and current_length + len(line) + 1 > max_chars:
                groups.append(current)
                current = []
                current_length = context_length + len(column_line)
            current.append((line, cells))
            current_length += len(line) + 1
        if current:
            groups.append(current)

        return [
            {
                "text": "\n".join(part for part in (
                    title_line, column_line, *(line for line, _ in group),
                ) if part),
                "match_text": " ".join([
                    *columns, *(value for _, cells in group for value in cells),
                ]),
            }
            for group in groups
        ]

    @staticmethod
    def _table_match_coverage(chunk_text: str, table_text: str) -> Tuple[float, float]:
        def tokens(value: str) -> Counter:
            normalized = unicodedata.normalize("NFKD", value).casefold()
            normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
            return Counter(re.findall(r"[\w]+", normalized, flags=re.UNICODE))

        chunk_tokens = tokens(chunk_text)
        table_tokens = tokens(table_text)
        if not chunk_tokens or not table_tokens:
            return 0.0, 0.0
        matched = sum((chunk_tokens & table_tokens).values())
        return matched / sum(chunk_tokens.values()), matched / sum(table_tokens.values())

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

    def _extract_pdf(
        self, source: Any, file_path: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]], Dict[int, str], Dict[int, List[str]], Dict[int, int], Dict[int, float]]:
        """Extract page text and table rows during one PDF traversal."""
        if isinstance(source, bytes):
            pdf_document = fitz.open(stream=source, filetype="pdf")
        else:
            pdf_document = fitz.open(source)

        extracted_text = []
        tables = []
        ocr_pages = {}
        ocr_table_words = {}
        ocr_page_rects = {}
        ocr_rotations = {}
        ocr_deskews = {}
        ocr_render_scales = {}
        ocr_details = {}
        ocr_diagnostics = {}
        page_headings = {}
        metadata = {
            "page_count": len(pdf_document),
        }
        if file_path:
            metadata["file_size_bytes"] = os.path.getsize(file_path)

        try:
            if self.page_numbers is not None:
                invalid_pages = self.page_numbers - set(range(1, len(pdf_document) + 1))
                if invalid_pages:
                    raise ValueError(f"PDF page numbers out of range: {sorted(invalid_pages)}")
            for page_num, page in enumerate(pdf_document):
                if self.page_numbers is not None and page_num + 1 not in self.page_numbers:
                    continue
                page_text = (
                    page.get_text("text")
                    if self.config.get("preserve_layout", True)
                    else page.get_text()
                )
                native_text = page_text.strip()
                ocr_headings = []
                ocr_text = ""
                page_needs_ocr = self._needs_ocr(page, native_text)
                if self.ocr_available and self.config.get("ocr_fallback", False) and page_needs_ocr:
                    ocr_pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(self.config["ocr_render_scale"], self.config["ocr_render_scale"]),
                        alpha=False,
                    )
                    ocr_rotation = self._detect_ocr_rotation(ocr_pixmap)
                    if ocr_rotation:
                        try:
                            ocr_pixmap = self._rotate_ocr_pixmap(ocr_pixmap, ocr_rotation)
                        except (OSError, ValueError) as error:
                            logger.warning("Could not rotate OCR image for page %d: %s", page_num + 1, error)
                            ocr_rotation = 0
                        if ocr_rotation:
                            ocr_page_rects[page_num + 1] = self._oriented_page_rect(page.rect, ocr_rotation)
                            ocr_rotations[page_num + 1] = ocr_rotation
                    ocr_text = self._ocr_page(page, ocr_pixmap).strip()
                    if not ocr_rotation:
                        ocr_rotation, ocr_pixmap, ocr_text = self._recover_sparse_landscape_orientation(
                            page, ocr_pixmap, ocr_text,
                        )
                        if ocr_rotation:
                            ocr_page_rects[page_num + 1] = self._oriented_page_rect(page.rect, ocr_rotation)
                            ocr_rotations[page_num + 1] = ocr_rotation
                    table_pixmap_source = ocr_pixmap
                    if self.config.get("ocr_deskew", True) and ocr_text:
                        deskew = self._estimate_ocr_skew(ocr_pixmap)
                        if deskew:
                            try:
                                deskewed_pixmap = self._rotate_ocr_pixmap_by_angle(ocr_pixmap, deskew)
                                ocr_pixmap = deskewed_pixmap
                                ocr_text = self._ocr_page(page, ocr_pixmap).strip()
                                ocr_deskews[page_num + 1] = deskew
                            except (OSError, ValueError) as error:
                                logger.debug("Could not deskew OCR image for page %d: %s", page_num + 1, error)
                    if ocr_text:
                        if self.config.get("extract_tables", False) and self._looks_like_numeric_table(ocr_text):
                            table_render_scale = self.config["ocr_table_render_scale"]
                            table_pixmap = (
                                table_pixmap_source
                                if table_render_scale == self.config["ocr_render_scale"]
                                else page.get_pixmap(
                                    matrix=fitz.Matrix(table_render_scale, table_render_scale),
                                    alpha=False,
                                )
                            )
                            if ocr_rotation and table_render_scale != self.config["ocr_render_scale"]:
                                table_pixmap = self._rotate_ocr_pixmap(table_pixmap, ocr_rotation)
                            table_deskew = ocr_deskews.get(page_num + 1, 0.0)
                            if table_deskew:
                                table_pixmap = self._rotate_ocr_pixmap_by_angle(table_pixmap, table_deskew)
                            ocr_table_words[page_num + 1] = self._ocr_page_words(
                                page, table_pixmap, page_rect=ocr_page_rects.get(page_num + 1),
                            )
                        if len(native_text) < 50:
                            page_text = ocr_text
                            ocr_pages[page_num + 1] = "tesseract"
                        else:
                            additions = self._remove_ocr_duplicates(native_text, ocr_text)
                            if additions and self._has_meaningful_ocr_additions(native_text, ocr_text):
                                page_text = f"{page_text}\n{additions}"
                                ocr_pages[page_num + 1] = "pymupdf+tesseract"
                            else:
                                ocr_text = ""
                elif self.ocr_available and self.config.get("ocr_fallback", False):
                    image_scale = self.config["ocr_table_render_scale"]
                    image_texts = []
                    image_words = []
                    for image_rect in self._embedded_image_regions(page):
                        image_pixmap = page.get_pixmap(
                            matrix=fitz.Matrix(image_scale, image_scale),
                            clip=image_rect,
                            alpha=False,
                        )
                        words = self._ocr_page_words(page, image_pixmap, page_rect=image_rect)
                        if len(words) < 4:
                            ocr_diagnostics.setdefault(page_num + 1, []).append({
                                "scope": "embedded_image_region",
                                "status": "rejected",
                                "reason": "insufficient_ocr_words",
                                "word_count": len(words),
                            })
                            continue
                        confidences = [word[8] for word in words if len(word) > 8 and word[8] >= 0]
                        mean_confidence = statistics.mean(confidences) if confidences else 0.0
                        # ponytail: reject weak embedded-image OCR rather than index a
                        # malformed table; lower this only with reviewed mixed-page labels.
                        if mean_confidence < 60:
                            ocr_diagnostics.setdefault(page_num + 1, []).append({
                                "scope": "embedded_image_region",
                                "status": "rejected",
                                "reason": "low_mean_word_confidence",
                                "mean_word_confidence": round(mean_confidence, 1),
                                "minimum_word_confidence": 60,
                            })
                            logger.info(
                                "Skipping embedded image OCR on page %d (mean confidence %.1f)",
                                page_num + 1, mean_confidence,
                            )
                            continue
                        image_words.extend(words)
                        image_texts.append(self._ocr_words_to_text(words))
                    image_text = "\n".join(text for text in image_texts if text).strip()
                    if image_text:
                        additions = self._remove_ocr_duplicates(native_text, image_text)
                        if additions and self._has_meaningful_ocr_additions(native_text, image_text):
                            page_text = f"{page_text}\n{additions}"
                            ocr_text = image_text
                            ocr_pages[page_num + 1] = "pymupdf+tesseract"
                            ocr_render_scales[page_num + 1] = image_scale
                            ocr_details[page_num + 1] = {
                                "page_psm": self.config["tesseract_table_psm"],
                                "scope": "embedded_image_regions",
                                "mean_word_confidence": round(mean_confidence, 1),
                            }
                        if self.config.get("extract_tables", False) and image_words:
                            ocr_table_words[page_num + 1] = image_words

                page_text = self._remove_page_counter_footer(page_text)

                if self.config.get("extract_tables", False):
                    table_words = ocr_table_words.get(page_num + 1, [])
                    table_confidences = [
                        word[8] for word in table_words
                        if len(word) > 8 and word[8] >= 0
                    ]
                    mean_word_confidence = (
                        round(statistics.mean(table_confidences), 1)
                        if table_confidences else None
                    )
                    tables.extend(self._extract_page_tables(
                        page, page_num + 1, table_words,
                        ocr_metadata=self._ocr_table_metadata(
                            ocr_rotations.get(page_num + 1, 0),
                            ocr_deskews.get(page_num + 1, 0.0),
                            mean_word_confidence,
                        ),
                        ocr_page_rect=ocr_page_rects.get(page_num + 1),
                    ))

                    # On scan-only pages, keep table content in its structured
                    # row-aware chunks. Rebuild the prose chunk from the same
                    # word boxes outside extracted table regions so a noisy
                    # full-page OCR value cannot conflict with the table value.
                    page_tables = [
                        table for table in tables
                        if table.get("page_number") == page_num + 1
                    ]
                    if (
                        ocr_pages.get(page_num + 1) == "tesseract"
                        and table_words
                        and page_tables
                    ):
                        prose_words = self._exclude_table_words(table_words, page_tables)
                        prose_text = self._ocr_words_to_text(prose_words).strip()
                        if prose_text:
                            page_text = self._remove_page_counter_footer(prose_text)
                            ocr_render_scales[page_num + 1] = self.config["ocr_table_render_scale"]
                            ocr_details[page_num + 1] = {
                                "page_psm": self.config["tesseract_table_psm"],
                                "scope": "page_words_outside_structured_tables",
                            }

                table_bboxes = [
                    table["metadata"]["bbox"] for table in tables
                    if table.get("page_number") == page_num + 1
                    and table.get("metadata", {}).get("bbox")
                ]
                headings = self._extract_page_headings(page, table_bboxes)
                if ocr_text:
                    has_ocr_table = any(
                        table.get("page_number") == page_num + 1 for table in tables
                    )
                    ocr_headings = self._extract_ocr_page_headings(
                        ocr_text,
                        allow_unstructured=not has_ocr_table and not headings,
                    )
                headings.extend(heading for heading in ocr_headings if heading not in headings)
                if headings:
                    page_headings[page_num + 1] = headings
                for table in tables:
                    if table.get("page_number") == page_num + 1:
                        table_title = self._extract_table_title(
                            page, table, ocr_table_words.get(page_num + 1),
                        )
                        if table_title:
                            table.setdefault("context", {})["table_title"] = table_title

                extracted_text.append(f"\n--- Page {page_num + 1} ---\n{page_text}")

                if self.config.get("extract_images", False) and file_path:
                    self._extract_images(page, page_num, file_path)

            for table in tables:
                rotation = ocr_rotations.get(table.get("page_number"), 0)
                deskew = ocr_deskews.get(table.get("page_number"), 0.0)
                if rotation or deskew:
                    source_page = pdf_document[table["page_number"] - 1]
                    self._restore_table_coordinates(table, source_page.rect, rotation, deskew)
            self._link_continued_tables(tables, pdf_document)
        except Exception as e:
            logger.error("Error extracting PDF content: %s", str(e))
            raise
        finally:
            pdf_document.close()

        metadata["_ocr_render_scales"] = ocr_render_scales
        metadata["_ocr_details"] = ocr_details
        metadata["_ocr_diagnostics"] = ocr_diagnostics
        return "\n".join(extracted_text), metadata, tables, ocr_pages, page_headings, ocr_rotations, ocr_deskews

    @staticmethod
    def _extract_page_headings(page, excluded_bboxes=()) -> List[str]:
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
                bbox = fitz.Rect(line.get("bbox", [0, 0, 0, 0]))
                if any(bbox.intersects(fitz.Rect(table_bbox)) for table_bbox in excluded_bboxes):
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
            visually_prominent = size >= body_size * 1.5
            uppercase_title = (
                text == text.upper()
                and any(char.isalpha() for char in text)
                and len(text.split()) >= 2
                and not re.match(r"^\d{3}\b", text)
            )
            sentence_like = text.endswith((".", ";", ","))
            if (
                2 <= len(text) <= 140
                and not sentence_like
                and (numbered_heading or visually_prominent or uppercase_title)
                and not re.fullmatch(r"[\d\W]+", text)
            ):
                if not headings or headings[-1][1] != text:
                    headings.append((_, text, size, visually_prominent))

        merged = []
        for y, text, size, visually_prominent in headings:
            if (
                merged
                and visually_prominent
                and merged[-1][3]
                and abs(size - merged[-1][2]) <= max(size, merged[-1][2]) * 0.05
                and y - merged[-1][0] <= max(size, merged[-1][2]) * 1.2
            ):
                previous = merged[-1]
                merged[-1] = (y, f"{previous[1]} {text}", size, visually_prominent)
            else:
                merged.append((y, text, size, visually_prominent))
        return [heading for _, heading, _, _ in merged]

    @staticmethod
    def _extract_ocr_page_headings(
        text: str, *, allow_unstructured: bool = True,
    ) -> List[str]:
        """Recover clear structural headings without promoting numbered prose."""
        headings = []
        for line in text.splitlines():
            line = " ".join(line.split()).strip("\t ")
            if not line or len(line) > 140:
                continue
            structural = any(
                _HEADING_PATTERNS[name].match(line)
                for name in ("chapter", "article")
            )
            numbered = _HEADING_PATTERNS["subsection"].match(line)
            if numbered:
                remainder = line[numbered.end():].lstrip()
                structural = bool(remainder and remainder[0].isupper())
            words = line.split()
            plain_heading = (
                allow_unstructured
                and 2 <= len(line) <= 72
                and 2 <= len(words) <= 9
                and not any(char.isdigit() or char in ".,;:!?/|()[]{}" for char in line)
                and not line.isupper()
                and line[0].isupper()
            )
            if structural or plain_heading:
                if line not in headings:
                    headings.append(line)
        return headings

    @staticmethod
    def _extract_table_title(page, table: Dict[str, Any], ocr_words=None) -> Optional[str]:
        """Find an explicit table/report caption immediately above its detected bounds."""
        bbox = table.get("metadata", {}).get("bbox")
        if not bbox:
            return None
        table_top = fitz.Rect(bbox).y0
        caption_terms = (
            "bảng", "báo cáo", "balance sheet", "financial position",
            "income statement", "statement of", "results of operations",
        )
        candidates = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                text = " ".join("".join(
                    span.get("text", "") for span in line.get("spans", [])
                ).split())
                if not text or len(text) > 140:
                    continue
                line_rect = fitz.Rect(line.get("bbox", [0, 0, 0, 0]))
                gap = table_top - line_rect.y1
                if 0 <= gap <= 100 and any(term in text.casefold() for term in caption_terms):
                    candidates.append((gap, text))
        native_title = min(candidates, default=(None, None), key=lambda candidate: candidate[0])[1]
        if native_title or not ocr_words:
            return native_title

        header_bbox = table.get("metadata", {}).get("ocr_column_header_bbox")
        if not header_bbox:
            return None
        header_top = fitz.Rect(header_bbox).y0
        lines: Dict[Tuple[int, int], List[Tuple[float, float, float, float, str]]] = {}
        for word in ocr_words:
            lines.setdefault((word[5], word[6]), []).append(word)
        ocr_candidates = []
        for words in lines.values():
            words.sort(key=lambda word: word[0])
            text = " ".join(str(word[4]).strip() for word in words).strip()
            if not 2 <= len(text) <= 120 or text.endswith((".", ";", ",")):
                continue
            line_bottom = max(word[3] for word in words)
            gap = header_top - line_bottom
            if 0 < gap <= 120:
                ocr_candidates.append((gap, text))
        return min(ocr_candidates, default=(None, None), key=lambda item: item[0])[1]

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
    def _embedded_image_regions(page):
        """Return a small set of large raster regions on otherwise text-rich pages."""
        regions = []
        seen = set()
        page_area = max(page.rect.get_area(), 1)
        for image in page.get_image_info():
            rect = fitz.Rect(image.get("bbox", (0, 0, 0, 0))).intersect(page.rect)
            key = tuple(round(value, 1) for value in rect)
            if (
                key in seen
                or rect.width < 96
                or rect.height < 48
                or rect.get_area() / page_area < 0.10
            ):
                continue
            seen.add(key)
            regions.append(rect)
        # ponytail: OCR only the two largest embedded images per text-rich page;
        # expand after a labeled fixture shows that smaller images carry needed text.
        return sorted(regions, key=lambda rect: rect.get_area(), reverse=True)[:2]

    @staticmethod
    def _ocr_words_to_text(words) -> str:
        """Rebuild reading lines from the word boxes already returned by Tesseract TSV."""
        lines = defaultdict(list)
        for word in words:
            lines[(word[5], word[6])].append(word)
        return "\n".join(
            " ".join(item[4] for item in sorted(line, key=lambda item: (item[0], item[7])))
            for _, line in sorted(lines.items())
        )

    @staticmethod
    def _exclude_table_words(words, tables):
        """Remove OCR words inside extracted table and column-header boxes."""
        boxes = []
        for table in tables:
            metadata = table.get("metadata") or {}
            boxes.extend(
                box for box in (metadata.get("bbox"), metadata.get("ocr_column_header_bbox"))
                if isinstance(box, (list, tuple)) and len(box) == 4
            )
        if not boxes:
            return list(words)
        return [
            word for word in words
            if not any(
                box[0] <= (word[0] + word[2]) / 2 <= box[2]
                and box[1] <= (word[1] + word[3]) / 2 <= box[3]
                for box in boxes
            )
        ]

    @staticmethod
    def _remove_ocr_duplicates(native_text: str, ocr_text: str) -> str:
        """Drop OCR lines and sentences already represented by native PDF text."""
        def fragments(text: str) -> list[tuple[str, str]]:
            result = []
            for line in text.splitlines() or [text]:
                for fragment in re.split(r"(?<=[.!?])\s+", " ".join(line.split())):
                    normalized = "".join(
                        character for character in unicodedata.normalize("NFD", fragment.casefold())
                        if unicodedata.category(character) != "Mn" and character.isalnum()
                    )
                    if normalized:
                        result.append((fragment, normalized))
            return result

        native_fragments = fragments(native_text)
        native_exact = {normalized for _, normalized in native_fragments if len(normalized) >= 8}
        if not native_fragments:
            return ocr_text

        kept = []
        for sentence, normalized in fragments(ocr_text):
            duplicate = normalized in native_exact or (len(normalized) >= 30 and any(
                min(len(normalized), len(native)) / max(len(normalized), len(native)) >= 0.65
                and SequenceMatcher(None, normalized, native, autojunk=False).ratio() >= 0.82
                for _, native in native_fragments
            ))
            if not duplicate:
                kept.append(sentence)
        return " ".join(kept)

    @staticmethod
    def _has_meaningful_ocr_additions(native_text: str, ocr_text: str) -> bool:
        """Ignore OCR noise when little of the OCR token stream is new to native text."""
        pattern = re.compile(r"(?u)\b(?:\d{2,}(?:[.,]\d+)*|[^\W\d_][\w-]{2,})\b")
        native_tokens = set(pattern.findall(native_text.casefold()))
        ocr_tokens = pattern.findall(ocr_text.casefold())
        new_tokens = [token for token in ocr_tokens if token not in native_tokens]
        return len(set(new_tokens)) >= 3 and len(new_tokens) / max(len(ocr_tokens), 1) >= 0.08

    @staticmethod
    def _looks_like_numeric_table(text: str) -> bool:
        """Detect aligned rows even when Tesseract emits each cell on its own line."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        numeric_cell = re.compile(r"(?:[-+]?\d[\d.,]*|[-–—])")
        multi_value_rows = sum(len(numeric_cell.findall(line)) >= 2 for line in lines)
        split_cell_rows = sum(bool(numeric_cell.fullmatch(line)) for line in lines)
        return multi_value_rows >= 3 or split_cell_rows >= 8

    def _ocr_table_metadata(
        self, orientation_correction_degrees: int = 0,
        deskew_correction_degrees: float = 0.0,
        mean_word_confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        metadata = {
            "engine": "tesseract",
            "language": self.config.get("ocr_language", "vie+eng"),
            "table_psm": self.config["tesseract_table_psm"],
            "render_scale": self.config["ocr_table_render_scale"],
        }
        if orientation_correction_degrees:
            metadata["orientation_correction_degrees"] = orientation_correction_degrees
        if deskew_correction_degrees:
            metadata["deskew_correction_degrees"] = deskew_correction_degrees
        if mean_word_confidence is not None:
            metadata["mean_word_confidence"] = mean_word_confidence
        return metadata

    def _detect_ocr_rotation(self, pixmap) -> int:
        """Return a confident Tesseract OSD quarter-turn correction, if any."""
        if not self.config.get("ocr_orientation_detection", True) or not self.ocr_available:
            return 0
        try:
            result = subprocess.run(
                ["tesseract", "stdin", "stdout", "-l", "osd", "--psm", "0"],
                input=pixmap.tobytes("png"), capture_output=True, check=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            logger.debug("Tesseract orientation detection unavailable: %s", error)
            return 0

        output = result.stdout.decode("utf-8", errors="replace")
        rotation = re.search(r"^Rotate:\s*(\d+)\s*$", output, re.MULTILINE)
        confidence = re.search(r"^Orientation confidence:\s*([\d.]+)\s*$", output, re.MULTILINE)
        if not rotation or not confidence:
            return 0
        degrees = int(rotation.group(1))
        if degrees not in {90, 180, 270} or float(confidence.group(1)) < 2.5:
            return 0
        return degrees

    def _estimate_ocr_skew(self, pixmap) -> float:
        """Estimate small page skew from horizontal text-line projections."""
        from PIL import Image

        try:
            with Image.open(BytesIO(pixmap.tobytes("png"))) as source:
                image = source.convert("L")
                image.thumbnail((420, 600), Image.Resampling.LANCZOS)

            def projection_score(angle: float) -> float:
                rotated = image.rotate(
                    angle, resample=Image.Resampling.BILINEAR,
                    expand=False, fillcolor=255,
                )
                pixels = np.asarray(rotated, dtype=np.uint8)
                row_ink = np.count_nonzero(pixels < 190, axis=1).astype(np.float64)
                return float(np.square(row_ink - row_ink.mean()).sum())

            baseline = projection_score(0.0)
            if baseline <= 0:
                return 0.0
            coarse = max(
                ((projection_score(float(angle)), float(angle))
                 for angle in np.arange(-6.0, 6.01, 0.5)),
                key=lambda item: item[0],
            )[1]
            best_score, correction = max(
                ((projection_score(float(angle)), float(angle))
                 for angle in np.arange(coarse - 0.5, coarse + 0.501, 0.1)),
                key=lambda item: item[0],
            )
            if abs(correction) < 0.5 or best_score < baseline * 1.1:
                return 0.0
            return round(correction, 1)
        except (OSError, ValueError):
            return 0.0

    @staticmethod
    def _rotate_ocr_pixmap_by_angle(pixmap, correction_degrees: float):
        """Apply a small counterclockwise correction without changing raster bounds."""
        from PIL import Image

        with Image.open(BytesIO(pixmap.tobytes("png"))) as image:
            corrected = image.rotate(
                correction_degrees, resample=Image.Resampling.BICUBIC,
                expand=False, fillcolor=(255, 255, 255),
            ).convert("RGB")
            output = BytesIO()
            corrected.save(output, format="PNG")
        return fitz.Pixmap(output.getvalue())

    @staticmethod
    def _rotate_ocr_pixmap(pixmap, clockwise_degrees: int):
        """Rotate a rendered page to the orientation reported by Tesseract OSD."""
        from PIL import Image

        with Image.open(BytesIO(pixmap.tobytes("png"))) as image:
            upright = image.rotate(-clockwise_degrees, expand=True).convert("RGB")
            output = BytesIO()
            upright.save(output, format="PNG")
        return fitz.Pixmap(output.getvalue())

    def _recover_sparse_landscape_orientation(self, page, pixmap, ocr_text: str):
        """Try sideways candidates only when OSD and upright OCR yield little text."""
        if (
            not self.config.get("ocr_orientation_detection", True)
            or not self.ocr_available
            or pixmap.width <= pixmap.height
            or sum(character.isalnum() for character in ocr_text) >= 40
        ):
            return 0, pixmap, ocr_text
        from PIL import Image, ImageStat

        try:
            with Image.open(BytesIO(pixmap.tobytes("png"))) as image:
                thumbnail = image.convert("L")
                thumbnail.thumbnail((48, 48))
                if ImageStat.Stat(thumbnail).stddev[0] <= 1.5:
                    return 0, pixmap, ocr_text
        except (OSError, ValueError) as error:
            logger.debug("Could not inspect sparse OCR page for rotation: %s", error)
            return 0, pixmap, ocr_text

        def score(text):
            return (
                int(self._looks_like_numeric_table(text)),
                sum(character.isalpha() for character in text),
                sum(character.isdigit() for character in text),
            )

        best_score = score(ocr_text)
        best = (0, pixmap, ocr_text)
        for degrees in (90, 270):
            try:
                candidate_pixmap = self._rotate_ocr_pixmap(pixmap, degrees)
            except (OSError, ValueError) as error:
                logger.debug("Could not try %d-degree OCR rotation: %s", degrees, error)
                continue
            candidate_text = self._ocr_page(page, candidate_pixmap, timeout=30).strip()
            candidate_score = score(candidate_text)
            if candidate_score > best_score and (
                self._looks_like_numeric_table(candidate_text)
                or sum(character.isalpha() for character in candidate_text) >= 24
            ):
                best_score = candidate_score
                best = (degrees, candidate_pixmap, candidate_text)
        return best

    @staticmethod
    def _oriented_page_rect(page_rect, clockwise_degrees: int):
        if clockwise_degrees in {90, 270}:
            return fitz.Rect(0, 0, page_rect.height, page_rect.width)
        return fitz.Rect(0, 0, page_rect.width, page_rect.height)

    @staticmethod
    def _restore_table_coordinates(
        table: Dict[str, Any], page_rect, clockwise_degrees: int,
        deskew_correction_degrees: float = 0.0,
    ) -> None:
        """Map OCR boxes from the corrected raster back to the source PDF page."""
        metadata = table.get("metadata", {})
        oriented_rect = PDFProcessor._oriented_page_rect(page_rect, clockwise_degrees)

        def restore(box):
            if not box or len(box) != 4:
                return box
            x0, y0, x1, y1 = map(float, box)
            if deskew_correction_degrees:
                angle = math.radians(deskew_correction_degrees)
                cosine, sine = math.cos(angle), math.sin(angle)
                center_x = oriented_rect.x0 + oriented_rect.width / 2
                center_y = oriented_rect.y0 + oriented_rect.height / 2
                points = []
                for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
                    dx, dy = x - center_x, y - center_y
                    points.append((
                        center_x + cosine * dx - sine * dy,
                        center_y + sine * dx + cosine * dy,
                    ))
                x0 = max(oriented_rect.x0, min(point[0] for point in points))
                x1 = min(oriented_rect.x1, max(point[0] for point in points))
                y0 = max(oriented_rect.y0, min(point[1] for point in points))
                y1 = min(oriented_rect.y1, max(point[1] for point in points))
            if clockwise_degrees == 90:
                points = ((page_rect.width - y, x) for x in (x0, x1) for y in (y0, y1))
            elif clockwise_degrees == 180:
                points = ((page_rect.width - x, page_rect.height - y) for x in (x0, x1) for y in (y0, y1))
            elif clockwise_degrees == 270:
                points = ((y, page_rect.height - x) for x in (x0, x1) for y in (y0, y1))
            else:
                return box
            xs, ys = zip(*points)
            return [
                max(page_rect.x0, min(page_rect.x1, page_rect.x0 + min(xs))),
                max(page_rect.y0, min(page_rect.y1, page_rect.y0 + min(ys))),
                max(page_rect.x0, min(page_rect.x1, page_rect.x0 + max(xs))),
                max(page_rect.y0, min(page_rect.y1, page_rect.y0 + max(ys))),
            ]

        metadata["bbox"] = restore(metadata.get("bbox"))
        if metadata.get("ocr_column_header_bbox"):
            metadata["ocr_column_header_bbox"] = restore(metadata["ocr_column_header_bbox"])
        for row in metadata.get("row_cell_bboxes", []):
            for column, box in row.items():
                if box:
                    row[column] = restore(box)

    @staticmethod
    def _link_continued_tables(tables: List[Dict[str, Any]], pdf_document) -> None:
        """Link unambiguous page-edge table segments without merging their provenance."""
        by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for table in tables:
            by_page[int(table.get("page_number") or 0)].append(table)

        for page_number in sorted(by_page):
            previous_tables = by_page.get(page_number - 1, [])
            current_tables = by_page[page_number]
            if not previous_tables:
                continue
            previous_rect = pdf_document[page_number - 2].rect
            current_rect = pdf_document[page_number - 1].rect
            matches = []
            for previous in previous_tables:
                previous_columns = tuple(
                    " ".join(str(column).casefold().split())
                    for column in previous.get("columns", [])
                )
                previous_bbox = (previous.get("metadata") or {}).get("bbox")
                if not previous_columns or not previous_bbox or previous_bbox[3] < previous_rect.y0 + previous_rect.height * 0.75:
                    continue
                previous_title = str((previous.get("context") or {}).get("table_title") or "").strip().casefold()
                for current in current_tables:
                    current_columns = tuple(
                        " ".join(str(column).casefold().split())
                        for column in current.get("columns", [])
                    )
                    current_bbox = (current.get("metadata") or {}).get("bbox")
                    if current_columns != previous_columns or not current_bbox:
                        continue
                    if current_bbox[1] > current_rect.y0 + current_rect.height * 0.25:
                        continue
                    current_title = str((current.get("context") or {}).get("table_title") or "").strip().casefold()
                    if previous_title and current_title and previous_title != current_title:
                        continue
                    matches.append((previous, current))

            if len(matches) != 1:
                continue
            previous, current = matches[0]
            previous_metadata = previous.setdefault("metadata", {})
            current_metadata = current.setdefault("metadata", {})
            group_id = previous_metadata.get("continuation_group_id") or (
                f"page:{page_number - 1}:table:{previous.get('table_index', 0)}"
            )
            previous_metadata.update({
                "continuation_group_id": group_id,
                "continued_to_page": page_number,
            })
            current_metadata.update({
                "continuation_group_id": group_id,
                "continued_from_page": page_number - 1,
            })
            previous_context = previous.setdefault("context", {})
            current_context = current.setdefault("context", {})
            inherited_title = previous_context.get("table_title") or current_context.get("table_title")
            if inherited_title:
                previous_context.setdefault("table_title", inherited_title)
                current_context.setdefault("table_title", inherited_title)


    @staticmethod
    def _extract_page_tables(page, page_number: int, ocr_words=None, ocr_metadata=None, ocr_page_rect=None):
        return PDFTableExtractor._extract_page_tables(
            page, page_number, ocr_words, ocr_metadata, ocr_page_rect,
        )

    @staticmethod
    def _tables_from_aligned_words(words, page_rect, page_number: int, ocr_metadata=None):
        return PDFTableExtractor._tables_from_aligned_words(words, page_rect, page_number, ocr_metadata)

    @staticmethod
    def _ocr_period_header(value: str) -> Optional[str]:
        return PDFTableExtractor._ocr_period_header(value)

    @staticmethod
    def _split_aligned_text_table(table, page, page_number: int, first_index: int, words=None):
        return PDFTableExtractor._split_aligned_text_table(table, page, page_number, first_index, words)

    def _ocr_page(self, page, pixmap=None, *, timeout: int = 90) -> str:
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
                ["tesseract", "stdin", "stdout", "-l", self.config.get("ocr_language", "vie+eng"), "--psm", str(self.config["tesseract_psm"]), *self._tesseract_cli_config_args()],
                input=pixmap.tobytes("png"), capture_output=True, check=True, timeout=timeout,
            ).stdout.decode("utf-8", errors="replace").strip()
        except (OSError, subprocess.SubprocessError) as e:
            logger.error("OCR error: %s", str(e))
            return ""

    def _ocr_page_words(
        self, page, pixmap=None, *, page_rect=None,
    ) -> List[Tuple[float, float, float, float, str, int, int, int, float]]:
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
                ["tesseract", "stdin", "stdout", "-l", self.config.get("ocr_language", "vie+eng"), "--psm", str(self.config["tesseract_table_psm"]), *self._tesseract_cli_config_args(), "tsv"],
                input=pixmap.tobytes("png"), capture_output=True,
                check=True, timeout=90,
            ).stdout.decode("utf-8", errors="replace")
            coordinate_rect = page_rect or page.rect
            scale_x = pixmap.width / coordinate_rect.width
            scale_y = pixmap.height / coordinate_rect.height
            words = []
            for row in csv.DictReader(output.splitlines(), delimiter="\t"):
                if row.get("level") != "5" or not row.get("text", "").strip():
                    continue
                left, top = int(row["left"]), int(row["top"])
                right = left + int(row["width"])
                bottom = top + int(row["height"])
                x0 = coordinate_rect.x0 + left / scale_x
                y0 = coordinate_rect.y0 + top / scale_y
                x1 = coordinate_rect.x0 + right / scale_x
                y1 = coordinate_rect.y0 + bottom / scale_y
                words.append((
                    x0, y0, x1, y1, row["text"],
                    int(row["block_num"]), int(row["line_num"]), int(row["word_num"]),
                    float(row.get("conf") or -1),
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
