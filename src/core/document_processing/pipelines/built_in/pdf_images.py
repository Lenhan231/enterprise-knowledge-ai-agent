"""PDF image extraction and optional image-caption generation."""

from __future__ import annotations

import logging
import os
from typing import Any

import fitz

logger = logging.getLogger(__name__)


def extract_pdf_images(page, page_num: int, file_path: str) -> None:
    """Write embedded page images to the existing per-document image folder."""
    try:
        pdf_name = os.path.splitext(os.path.basename(file_path))[0]
        image_dir = f"{pdf_name}_images"
        os.makedirs(image_dir, exist_ok=True)
        for img_index, img_info in enumerate(page.get_images(full=True)):
            base_image = page.parent.extract_image(img_info[0])
            if not base_image:
                continue
            image_path = os.path.join(
                image_dir, f"page{page_num + 1}_img{img_index + 1}.{base_image['ext']}"
            )
            with open(image_path, "wb") as image_file:
                image_file.write(base_image["image"])
            logger.debug("Extracted image: %s", image_path)
    except Exception as error:
        logger.error("Error extracting images from page %d: %s", page_num + 1, error)


def caption_pdf_images(
    config: dict[str, Any], result: dict[str, Any], source: Any,
    document: dict[str, Any],
) -> dict[str, Any]:
    """Add bounded, explicitly labeled captions for selected PDF images."""
    if not config.get("vision_captioning", False):
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
        selected = candidates[:max(0, int(config.get("vision_caption_max_images", 3)))]
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
                result["elements"].append({
                    "text": f"AI-generated image caption (unverified): {caption}",
                    "metadata": {
                        **metadata,
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
