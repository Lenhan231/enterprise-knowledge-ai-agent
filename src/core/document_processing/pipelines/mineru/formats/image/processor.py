"""Convert a raster image to PDF and run MinerU's OCR path."""

from __future__ import annotations

from typing import Any

import fitz

from ..pdf.processor import process as process_pdf


def process(runtime: Any, content: bytes, source_format: str, document: dict[str, Any]) -> dict[str, Any]:
    image = fitz.open(stream=content, filetype=source_format)
    try:
        pdf_bytes = image.convert_to_pdf()
    finally:
        image.close()
    return process_pdf(runtime, pdf_bytes, document, force_ocr=True, page_range="")
