"""OCR scanned pictures embedded in Word paragraphs and tables."""

from __future__ import annotations

import zipfile
from typing import Any
from xml.etree import ElementTree

from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.readers.office.scanned.image_ocr import (
    embedded_image_parts,
    ocr_embedded_image,
)


class DocxScannedProcessor:
    def __init__(self, config: dict[str, Any], chunking: ChunkingConfig):
        self.config = config
        self.chunking = chunking

    def process_element(
        self,
        archive: zipfile.ZipFile,
        element: ElementTree.Element,
        relationships: dict[str, str],
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        chunks = []
        for image_index, image_part in enumerate(embedded_image_parts(element, relationships)):
            chunks.extend(ocr_embedded_image(
                archive, image_part, self.config, self.chunking,
                {**metadata, "image_index": image_index},
            ))
        return chunks
