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
import unicodedata
from difflib import SequenceMatcher
from collections import Counter, defaultdict
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
        self.config.setdefault("ocr_language", "vie+eng")
        self.config.setdefault("ocr_render_scale", float(os.getenv("DOCUMENT_OCR_RENDER_SCALE", "1.5")))
        self.config.setdefault("ocr_table_render_scale", float(os.getenv("DOCUMENT_OCR_TABLE_RENDER_SCALE", "2.5")))
        for setting in ("ocr_render_scale", "ocr_table_render_scale"):
            if float(self.config[setting]) not in {1.5, 2.5, 3.5}:
                raise ValueError(f"{setting} must be one of 1.5, 2.5, or 3.5")
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
                            **({
                                "ocr": {
                                    "engine": "tesseract",
                                    "language": self.config["ocr_language"],
                                    "page_psm": self.config["tesseract_psm"],
                                    "render_scale": self.config["ocr_render_scale"],
                                },
                            } if page_number in ocr_pages else {}),
                        },
                    })
        chunks = self._replace_flat_table_chunks(chunks, tables)
        return self._caption_pdf_images({"chunks": chunks, "tables": tables}, pdf_source, document)

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
            fragments = self._structured_table_fragments(
                table, int(self.config.get("chunk_size", 800)),
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
    def _structured_table_fragments(table: Dict[str, Any], max_chars: int) -> List[Dict[str, str]]:
        columns = [str(column or f"column_{index + 1}").strip() for index, column in enumerate(table.get("columns", []))]
        rows = table.get("rows", [])
        if not columns and rows:
            columns = list(dict.fromkeys(str(key) for row in rows for key in row))
        if not columns:
            return []

        column_line = "Columns: " + " | ".join(columns)
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
        current_length = len(column_line)
        for line, cells in row_lines:
            if current and current_length + len(line) + 1 > max_chars:
                groups.append(current)
                current = []
                current_length = len(column_line)
            current.append((line, cells))
            current_length += len(line) + 1
        if current:
            groups.append(current)

        return [
            {
                "text": column_line + "\n" + "\n".join(line for line, _ in group),
                "match_text": " ".join([
                    *columns, *(value for _, cells in group for value in cells),
                ]),
            }
            for group in groups
        ]

    @staticmethod
    def _logical_table_fragments(
        table: Dict[str, Any], *, table_title: str, unit: str,
        column_labels: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Serialize account-code row groups while retaining each group's structured rows."""
        source_columns = [str(column) for column in table.get("columns", [])]
        rows = table.get("rows", [])
        columns = [column_labels.get(column, column) for column in source_columns]
        groups: List[List[Dict[str, Any]]] = []
        roots: List[Dict[str, Any]] = []
        current: List[Dict[str, Any]] = []

        def flush() -> None:
            if current:
                groups.append(current.copy())
                current.clear()

        for row in rows:
            label = str(row.get("label") or "").strip()
            code_match = re.match(r"^(\d{3})\b", label)
            if not code_match:
                # Repeated OCR column headers (for example "Mã Thuyết huyết 2011")
                # are not account rows and must not leak into retrieval text.
                continue
            code = int(code_match.group(1))
            if code % 100 == 0:
                flush()
                roots = [row]
            elif code % 10 == 0:
                flush()
                current.append(row)
            else:
                current.append(row)
        flush()

        fragments = []
        for index, group in enumerate(groups):
            structured_rows = [*roots, *group]
            lines = [
                f"Bảng: {table_title}", f"Đơn vị: {unit}",
                "Cột: " + " | ".join(columns),
            ]
            lines.extend(
                " | ".join(
                    f"{column_labels.get(source_column, source_column)}: "
                    f"{str(row.get(source_column) or '').strip()}"
                    for source_column in source_columns
                )
                for row in structured_rows
            )
            fragments.append({
                "retrieval_text": "\n".join(lines),
                "structured_data": {
                    "columns": columns,
                    "rows": [
                        {
                            column_labels.get(source_column, source_column): row.get(source_column)
                            for source_column in source_columns
                        }
                        for row in structured_rows
                    ],
                },
                "metadata": {
                    "page_number": table.get("page_number"),
                    "table_index": table.get("table_index"),
                    "table_chunk_index": index,
                    "table_chunk_count": len(groups),
                    "table_extraction_method": table.get("metadata", {}).get(
                        "table_extraction_method"
                    ),
                },
            })
        return fragments

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
                            page_text = f"{page_text}\n{self._remove_ocr_duplicates(native_text, ocr_text)}"
                            ocr_pages[page_num + 1] = "pymupdf+tesseract"

                extracted_text.append(f"\n--- Page {page_num + 1} ---\n{page_text}")

                if self.config.get("extract_tables", False):
                    tables.extend(self._extract_page_tables(
                        page, page_num + 1, ocr_table_words.get(page_num + 1),
                        ocr_metadata=self._ocr_table_metadata(),
                    ))

                table_bboxes = [
                    table["metadata"]["bbox"] for table in tables
                    if table.get("page_number") == page_num + 1
                    and table.get("metadata", {}).get("bbox")
                ]
                if ocr_text:
                    has_ocr_table = any(
                        table.get("page_number") == page_num + 1 for table in tables
                    )
                    ocr_headings = self._extract_ocr_page_headings(
                        ocr_text, allow_unstructured=not has_ocr_table,
                    )
                headings = self._extract_page_headings(page, table_bboxes)
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

                if self.config.get("extract_images", False) and file_path:
                    self._extract_images(page, page_num, file_path)
        except Exception as e:
            logger.error("Error extracting PDF content: %s", str(e))
            raise
        finally:
            pdf_document.close()

        return "\n".join(extracted_text), metadata, tables, ocr_pages, page_headings

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
            visually_prominent = size >= body_size * 1.2
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
                if not headings or headings[-1] != text:
                    headings.append(text)
        return headings

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
    def _remove_ocr_duplicates(native_text: str, ocr_text: str) -> str:
        """Drop OCR sentences already represented by native PDF text."""
        def normalized_sentences(text: str) -> list[str]:
            compact = " ".join(text.split())
            return [
                "".join(
                    character for character in unicodedata.normalize("NFD", sentence.casefold())
                    if unicodedata.category(character) != "Mn" and character.isalnum()
                )
                for sentence in re.split(r"(?<=[.!?])\s+", compact)
                if len(sentence.strip()) >= 30
            ]

        native_sentences = normalized_sentences(native_text)
        if not native_sentences:
            return ocr_text

        kept = []
        for sentence in re.split(r"(?<=[.!?])\s+", " ".join(ocr_text.split())):
            normalized = "".join(
                character for character in unicodedata.normalize("NFD", sentence.casefold())
                if unicodedata.category(character) != "Mn" and character.isalnum()
            )
            duplicate = len(normalized) >= 30 and any(
                min(len(normalized), len(native)) / max(len(normalized), len(native)) >= 0.65
                and SequenceMatcher(None, normalized, native, autojunk=False).ratio() >= 0.82
                for native in native_sentences
            )
            if not duplicate:
                kept.append(sentence)
        return " ".join(kept)

    @staticmethod
    def _looks_like_numeric_table(text: str) -> bool:
        """Detect aligned rows even when Tesseract emits each cell on its own line."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        numeric_cell = re.compile(r"(?:[-+]?\d[\d.,]*|[-–—])")
        multi_value_rows = sum(len(numeric_cell.findall(line)) >= 2 for line in lines)
        split_cell_rows = sum(bool(numeric_cell.fullmatch(line)) for line in lines)
        return multi_value_rows >= 3 or split_cell_rows >= 8

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
