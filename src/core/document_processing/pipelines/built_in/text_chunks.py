"""Turn extracted PDF pages into provenance-aware parser chunks."""

from __future__ import annotations

import re
from typing import Any, Dict

from core.document_processing.chunking.text.chunk_builder import build_text_chunk
from core.document_processing.chunking.text.router import split_ranges
from core.document_processing.headings import section_metadata


class PDFTextChunker:
    """Build page-local text chunks with heading and OCR provenance."""

    def __init__(self, config, chunking):
        self.config = config
        self.chunking = chunking

    def process(self, extraction, document: Dict[str, Any]) -> list[Dict[str, Any]]:
        (
            pdf_text, pdf_metadata, _tables, ocr_pages, page_headings,
            ocr_rotations, ocr_deskews,
        ) = extraction
        ocr_render_scales = pdf_metadata.pop("_ocr_render_scales", {})
        ocr_details = pdf_metadata.pop("_ocr_details", {})
        ocr_diagnostics = pdf_metadata.pop("_ocr_diagnostics", {})

        metadata = document.get("metadata", {}).copy()
        for key in ("uploaded_by", "title", "author", "subject", "keywords"):
            metadata.pop(key, None)
        metadata.update(pdf_metadata)

        chunks = []
        current_section_title = None
        current_heading_level = None
        page_sections = re.compile(r"--- Page (\d+) ---").split(pdf_text)
        for page_index in range(1, len(page_sections), 2):
            page_number = int(page_sections[page_index])
            page_text = " ".join(page_sections[page_index + 1].split())
            heading_positions = []
            search_from = 0
            for heading, level in page_headings.get(page_number, []):
                heading = " ".join(heading.split())
                position = page_text.find(heading, search_from)
                if position >= 0:
                    heading_positions.append((position, heading, level))
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
                if not text:
                    continue
                while heading_index < len(heading_positions) and heading_positions[heading_index][0] < end:
                    current_section_title = heading_positions[heading_index][1]
                    current_heading_level = heading_positions[heading_index][2]
                    heading_index += 1
                chunks.append(build_text_chunk(
                    text,
                    {
                        **metadata,
                        "page_number": page_number,
                        "text_extraction_method": ocr_pages.get(page_number, "pymupdf.get_text"),
                        "layout_type": "text",
                        **section_metadata(current_section_title, current_heading_level),
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
                    self.chunking,
                    index=len(chunks),
                ))
                if page_number in ocr_diagnostics:
                    diagnostics_attached = True

        return chunks
