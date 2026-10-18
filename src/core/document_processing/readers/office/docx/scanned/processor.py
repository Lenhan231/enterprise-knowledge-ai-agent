"""OCR scanned pictures embedded in Word paragraphs and tables."""

from __future__ import annotations

import zipfile
from typing import Any
from xml.etree import ElementTree

from core.document_processing.readers.office.scanned.image_ocr import (
    embedded_image_parts,
    ocr_embedded_image,
)


class DocxScannedProcessor:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def process_element(
        self,
        archive: zipfile.ZipFile,
        element: ElementTree.Element,
        relationships: dict[str, str],
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        elements = []
        for image_index, image_part in enumerate(embedded_image_parts(element, relationships)):
            elements.extend(ocr_embedded_image(
                archive, image_part, self.config,
                {**metadata, "image_index": image_index},
            ))
        return elements
