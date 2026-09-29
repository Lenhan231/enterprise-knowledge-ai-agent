"""OCR and optional vision captioning for standalone image uploads."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

import fitz

from .pdf_processor import PDFProcessor
from .text_processor import split_document_text as _split

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Process image uploads into OCR chunks and optional structured tables."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.chunk_size = int(self.config.get("chunk_size", 1100))
        self.chunk_overlap = int(self.config.get("chunk_overlap", 120))
        self.chunking_strategy = self.config.get("chunking_strategy", "sentence")
        self.vision_captioning = bool(self.config.get("vision_captioning", False))

    def process(self, suffix: str, content: bytes, metadata: dict[str, Any]) -> dict[str, list[dict]]:
        text = self._ocr(content)
        tables = []
        if PDFProcessor._looks_like_numeric_table(text):
            table_render_scale = self.config.get("ocr_table_render_scale", 2.5)
            layout = PDFProcessor({
                "ocr_fallback": True,
                "ocr_language": self.config.get("ocr_language", "vie+eng"),
                "tesseract_table_psm": self.config.get("tesseract_table_psm", 6),
                "ocr_render_scale": table_render_scale,
                "ocr_table_render_scale": table_render_scale,
            })
            image = fitz.open(stream=content, filetype=suffix[1:])
            try:
                page = image[0]
                words = layout._ocr_page_words(page)
                tables = PDFProcessor._tables_from_aligned_words(
                    words, page.rect, 1, ocr_metadata=layout._ocr_table_metadata(),
                )
            finally:
                image.close()
        chunks = _split(text, {**metadata, "text_extraction_method": "tesseract"}, self.chunk_size, self.chunk_overlap, self.chunking_strategy)
        if self.vision_captioning:
            try:
                image_bytes, mime_type = self._caption_image_input(content, suffix)
                from core.llm.groq_provider import GroqProvider

                provider = GroqProvider()
                try:
                    caption = provider.caption_image(image_bytes, mime_type)
                    model_name = provider.vision_model_name
                finally:
                    provider.close()
                chunks.extend(_split(f"AI-generated image caption (unverified): {caption}", {
                    **metadata,
                    "text_extraction_method": "groq_vision_caption",
                    "element_type": "figure_caption",
                    "layout_type": "figure_caption",
                    "caption_model": model_name,
                    "is_model_generated": True,
                }, self.chunk_size, self.chunk_overlap, self.chunking_strategy))
            except Exception as error:
                logger.warning(
                    "Vision caption failed for uploaded image %s (%s)",
                    metadata["filename"], type(error).__name__,
                )
        return {"chunks": chunks, "tables": tables}

    def _ocr(self, content: bytes) -> str:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", self.config.get("ocr_language", "vie+eng"), "--psm", str(self.config.get("tesseract_psm", 11))],
            input=content, capture_output=True, check=True, timeout=90,
        )
        return result.stdout.decode("utf-8", errors="replace").strip()

    @staticmethod
    def _caption_image_input(content: bytes, suffix: str) -> tuple[bytes, str]:
        if suffix in {".png", ".jpg", ".jpeg"}:
            return content, "image/png" if suffix == ".png" else "image/jpeg"
        if len(content) > 14 * 1024 * 1024:
            raise ValueError("TIFF is too large for the bounded vision caption request")
        import fitz

        image = fitz.open(stream=content, filetype=suffix[1:])
        try:
            page = image[0]
            scale = min(1.0, 2048 / max(page.rect.width, page.rect.height))
            return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png"), "image/png"
        finally:
            image.close()
