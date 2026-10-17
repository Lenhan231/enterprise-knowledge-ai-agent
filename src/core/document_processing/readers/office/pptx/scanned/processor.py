"""OCR scanned pictures embedded in PowerPoint slides."""

from __future__ import annotations

import zipfile
from typing import Any
from xml.etree import ElementTree

from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.readers.office.scanned.image_ocr import (
    embedded_image_parts,
    ocr_embedded_image,
)


class PptxScannedProcessor:
    def __init__(self, config: dict[str, Any], chunking: ChunkingConfig):
        self.config = config
        self.chunking = chunking

    def process_slide(
        self,
        archive: zipfile.ZipFile,
        slide: ElementTree.Element,
        relationships: dict[str, str],
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        chunks = []
        for image_index, image_part in enumerate(embedded_image_parts(slide, relationships)):
            chunks.extend(ocr_embedded_image(
                archive, image_part, self.config, self.chunking,
                {**metadata, "image_index": image_index},
            ))
        return chunks
