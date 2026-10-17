"""Extract page text, headings, and structured tables from PDFs."""

from __future__ import annotations

import logging
import os
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple

import fitz

from core.document_processing.headings import HEADING_PATTERNS, heading_level
from .table_extractor import PDFTableExtractor
from .digital_born.native_text import extract_native_page_text

logger = logging.getLogger(__name__)


class PDFTextExtractor:
    """Own the single-pass PDF text, OCR, heading, and table extraction flow."""

    _extract_page_tables = staticmethod(PDFTableExtractor._extract_page_tables)

    def __init__(self, config, page_numbers, ocr, tables, *, ocr_page, ocr_page_words, extract_images):
        self.config = config
        self.page_numbers = page_numbers
        self.ocr = ocr
        self.ocr_available = ocr.ocr_available
        self.tables = tables
        self._ocr_page = ocr_page
        self._ocr_page_words = ocr_page_words
        self._image_extractor = extract_images

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

    def _extract_pdf(
        self, source: Any, file_path: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]], Dict[int, str], Dict[int, List[Tuple[str, int]]], Dict[int, int], Dict[int, float]]:
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
        page_headings: Dict[int, List[Tuple[str, int]]] = {}
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
                page_text = extract_native_page_text(
                    page, preserve_layout=self.config.get("preserve_layout", True),
                )
                native_text = page_text.strip()
                ocr_headings = []
                ocr_text = ""
                page_needs_ocr = self.ocr._needs_ocr(page, native_text)
                if self.ocr_available and self.config.get("ocr_fallback", False) and page_needs_ocr:
                    ocr_pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(self.config["ocr_render_scale"], self.config["ocr_render_scale"]),
                        alpha=False,
                    )
                    ocr_rotation = self.ocr._detect_ocr_rotation(ocr_pixmap)
                    if ocr_rotation:
                        try:
                            ocr_pixmap = self.ocr._rotate_ocr_pixmap(ocr_pixmap, ocr_rotation)
                        except (OSError, ValueError) as error:
                            logger.warning("Could not rotate OCR image for page %d: %s", page_num + 1, error)
                            ocr_rotation = 0
                        if ocr_rotation:
                            ocr_page_rects[page_num + 1] = self.ocr._oriented_page_rect(page.rect, ocr_rotation)
                            ocr_rotations[page_num + 1] = ocr_rotation
                    ocr_text = self._ocr_page(page, ocr_pixmap).strip()
                    if not ocr_rotation:
                        ocr_rotation, ocr_pixmap, ocr_text = self.ocr._recover_sparse_landscape_orientation(
                            page, ocr_pixmap, ocr_text,
                        )
                        if ocr_rotation:
                            ocr_page_rects[page_num + 1] = self.ocr._oriented_page_rect(page.rect, ocr_rotation)
                            ocr_rotations[page_num + 1] = ocr_rotation
                    table_pixmap_source = ocr_pixmap
                    if self.config.get("ocr_deskew", True) and ocr_text:
                        deskew = self.ocr._estimate_ocr_skew(ocr_pixmap)
                        if deskew:
                            try:
                                deskewed_pixmap = self.ocr._rotate_ocr_pixmap_by_angle(ocr_pixmap, deskew)
                                ocr_pixmap = deskewed_pixmap
                                ocr_text = self._ocr_page(page, ocr_pixmap).strip()
                                ocr_deskews[page_num + 1] = deskew
                            except (OSError, ValueError) as error:
                                logger.debug("Could not deskew OCR image for page %d: %s", page_num + 1, error)
                    if ocr_text:
                        if self.config.get("extract_tables", False) and self.ocr._looks_like_numeric_table(ocr_text):
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
                                table_pixmap = self.ocr._rotate_ocr_pixmap(table_pixmap, ocr_rotation)
                            table_deskew = ocr_deskews.get(page_num + 1, 0.0)
                            if table_deskew:
                                table_pixmap = self.ocr._rotate_ocr_pixmap_by_angle(table_pixmap, table_deskew)
                            ocr_table_words[page_num + 1] = self._ocr_page_words(
                                page, table_pixmap, page_rect=ocr_page_rects.get(page_num + 1),
                            )
                        if len(native_text) < 50:
                            page_text = ocr_text
                            ocr_pages[page_num + 1] = "tesseract"
                        else:
                            additions = self.ocr._remove_ocr_duplicates(native_text, ocr_text)
                            if additions and self.ocr._has_meaningful_ocr_additions(native_text, ocr_text):
                                page_text = f"{page_text}\n{additions}"
                                ocr_pages[page_num + 1] = "pymupdf+tesseract"
                            else:
                                ocr_text = ""
                elif self.ocr_available and self.config.get("ocr_fallback", False):
                    image_scale = self.config["ocr_table_render_scale"]
                    image_texts = []
                    image_words = []
                    for image_rect in self.ocr._embedded_image_regions(page):
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
                        image_texts.append(self.ocr._ocr_words_to_text(words))
                    image_text = "\n".join(text for text in image_texts if text).strip()
                    if image_text:
                        additions = self.ocr._remove_ocr_duplicates(native_text, image_text)
                        if additions and self.ocr._has_meaningful_ocr_additions(native_text, image_text):
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
                        ocr_metadata=self.ocr._ocr_table_metadata(
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
                        prose_words = self.ocr._exclude_table_words(table_words, page_tables)
                        prose_text = self.ocr._ocr_words_to_text(prose_words).strip()
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
                        table_title = self.tables._extract_table_title(
                            page, table, ocr_table_words.get(page_num + 1),
                        )
                        if table_title:
                            table.setdefault("context", {})["table_title"] = table_title

                extracted_text.append(f"\n--- Page {page_num + 1} ---\n{page_text}")

                if self.config.get("extract_images", False) and file_path:
                    self._image_extractor(page, page_num, file_path)

            for table in tables:
                rotation = ocr_rotations.get(table.get("page_number"), 0)
                deskew = ocr_deskews.get(table.get("page_number"), 0.0)
                if rotation or deskew:
                    source_page = pdf_document[table["page_number"] - 1]
                    self.tables._restore_table_coordinates(table, source_page.rect, rotation, deskew)
            self.tables._link_continued_tables(tables, pdf_document)
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
    def _extract_page_headings(page, excluded_bboxes=()) -> List[Tuple[str, int]]:
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
            numbered_heading = any(pattern.match(text) for pattern in HEADING_PATTERNS.values())
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
        return [
            (heading, heading_level(heading) or 1)
            for _, heading, _, _ in merged
        ]

    @staticmethod
    def _extract_ocr_page_headings(
        text: str, *, allow_unstructured: bool = True,
    ) -> List[Tuple[str, int]]:
        """Recover clear structural headings without promoting numbered prose."""
        headings = []
        for line in text.splitlines():
            line = " ".join(line.split()).strip("\t ")
            if not line or len(line) > 140:
                continue
            structural = any(
                HEADING_PATTERNS[name].match(line)
                for name in ("chapter", "article")
            )
            numbered = HEADING_PATTERNS["subsection"].match(line)
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
                heading = (line, heading_level(line) or 1)
                if heading not in headings:
                    headings.append(heading)
        return headings
