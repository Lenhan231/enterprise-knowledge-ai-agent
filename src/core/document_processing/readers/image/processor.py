"""OCR and optional vision captioning for standalone image uploads."""

from __future__ import annotations

import logging
from typing import Any

import fitz

from core.document_processing.headings import section_metadata
from core.document_processing.pipelines.built_in.scanned.ocr.image_ocr import (
    looks_like_numeric_table,
    recognize_image_text,
    recognize_image_words,
)
from core.document_processing.pipelines.built_in.scanned.table_recovery import ScannedTableExtractor

logger = logging.getLogger(__name__)


class ScannedImageProcessor:
    """Process standalone scanned images into OCR blocks and tables."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.vision_captioning = bool(self.config.get("vision_captioning", False))

    def process(self, suffix: str, content: bytes, metadata: dict[str, Any]) -> dict[str, list[dict]]:
        text = self._ocr(content)
        tables = []
        if looks_like_numeric_table(text):
            table_render_scale = self.config.get("ocr_table_render_scale", 2.5)
            table_ocr_config = {
                "ocr_language": self.config.get("ocr_language", "vie+eng"),
                "tesseract_table_psm": self.config.get("tesseract_table_psm", 6),
                "ocr_render_scale": table_render_scale,
                "ocr_table_render_scale": table_render_scale,
            }
            image = fitz.open(stream=content, filetype=suffix[1:])
            try:
                page = image[0]
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(table_render_scale, table_render_scale),
                    alpha=False,
                )
                words = recognize_image_words(
                    pixmap.tobytes("png"), table_ocr_config,
                    page_segmentation_mode=table_ocr_config["tesseract_table_psm"],
                    image_size=(pixmap.width, pixmap.height),
                    coordinate_rect=tuple(page.rect),
                )
                tables = ScannedTableExtractor._tables_from_aligned_words(
                    words, page.rect, 1,
                    ocr_metadata={
                        "engine": "tesseract",
                        "language": table_ocr_config["ocr_language"],
                        "table_psm": table_ocr_config["tesseract_table_psm"],
                        "render_scale": table_render_scale,
                    },
                )
            finally:
                image.close()
        elements = [{
            "text": text,
            "metadata": {
                **metadata,
                "text_extraction_method": "tesseract",
                **section_metadata(None, None),
            },
        }]
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
                elements.append({
                    "text": f"AI-generated image caption (unverified): {caption}",
                    "metadata": {
                        **metadata,
                        "text_extraction_method": "groq_vision_caption",
                        "element_type": "figure_caption",
                        "layout_type": "figure_caption",
                        **section_metadata(None, None),
                        "caption_model": model_name,
                        "is_model_generated": True,
                    },
                })
            except Exception as error:
                logger.warning(
                    "Vision caption failed for uploaded image %s (%s)",
                    metadata["filename"], type(error).__name__,
                )
        for table_index, table in enumerate(tables):
            elements.append({
                "element_type": "table", "table_ref": table_index,
                "metadata": {**(table.get("metadata") or {}), "table_index": table.get("table_index", table_index)},
            })
        return {"elements": elements, "tables": tables}

    def _ocr(self, content: bytes) -> str:
        return recognize_image_text(
            content, self.config,
            page_segmentation_mode=self.config.get("tesseract_psm", 11),
            include_config=False,
        )

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
