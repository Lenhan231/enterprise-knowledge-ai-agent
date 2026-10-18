"""Run embedded Office images through the selected visual parser."""

from __future__ import annotations

import logging
import zipfile
from typing import Any

from core.document_processing.pipelines.built_in.scanned.ocr.image_ocr import recognize_image_text

logger = logging.getLogger(__name__)


def process_embedded_image(
    archive: zipfile.ZipFile,
    image_part: str,
    config: dict[str, Any],
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """Parse an Office image into content blocks with source location."""
    engine = config.get("parser_engine", "built_in")
    image_bytes = archive.read(image_part)
    source_metadata = {**metadata, "source_part": image_part}

    try:
        if engine == "pp-structurev3":
            from core.document_processing.pipelines.pp_structurev3.processor import (
                PPStructureV3Processor,
            )

            suffix = "." + image_part.rsplit(".", 1)[-1].lower()
            result = PPStructureV3Processor(config).process_image(
                image_bytes, suffix, {"content": image_bytes, "metadata": source_metadata},
            )
            elements = result.get("elements", [])
            for element in elements:
                chunk_metadata = element.setdefault("metadata", {})
                chunk_metadata.pop("page_number", None)
                chunk_metadata.update(source_metadata)
                chunk_metadata.setdefault("element_type", "image")
                chunk_metadata.setdefault("layout_type", chunk_metadata["element_type"])
                chunk_metadata.setdefault("parser", "paddleocr.PP-StructureV3")
                chunk_metadata.setdefault("text_extraction_method", "paddleocr.PP-StructureV3")
                if chunk_metadata["element_type"] == "table":
                    table_ref = element.pop("table_ref", None)
                    if isinstance(table_ref, int) and 0 <= table_ref < len(result.get("tables", [])):
                        table = dict(result["tables"][table_ref])
                        table_metadata = dict(table.get("metadata") or {})
                        table_metadata.pop("page_number", None)
                        table_metadata.update(source_metadata)
                        table["metadata"] = table_metadata
                        table.pop("page_number", None)
                        element["table_data"] = table
            return elements

        if engine != "built_in":
            # Docling and MinerU parse Office packages as a whole; this helper is
            # only reached by native Office readers in Built-in and PP routes.
            raise ValueError(f"Unsupported embedded-image parser: {engine}")

        text = recognize_image_text(
            image_bytes,
            config,
            page_segmentation_mode=config.get("tesseract_psm", 11),
            include_config=False,
        ).strip()
    except Exception as error:
        logger.warning(
            "Could not parse embedded Office image %s with %s (%s)",
            image_part, engine, type(error).__name__,
        )
        return []

    if not text:
        return []
    return [{
        "text": text,
        "metadata": {
            **source_metadata,
            "element_type": "image",
            "layout_type": "image",
            "text_extraction_method": "tesseract_embedded_image",
            "parser": "tesseract",
        },
    }]
