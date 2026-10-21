"""OCR scanned pictures embedded in Excel worksheets."""

from __future__ import annotations

import zipfile
from typing import Any
from xml.etree import ElementTree

from core.document_processing.readers.office.scanned.image_ocr import (
    embedded_image_parts,
    ocr_embedded_image,
    relationship_targets,
)

_X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_XDR = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"


class XlsxScannedProcessor:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def process_sheet(
        self,
        archive: zipfile.ZipFile,
        sheet_root: ElementTree.Element,
        sheet_path: str,
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        drawing = sheet_root.find(f".//{_X}drawing")
        if drawing is None:
            return []
        sheet_relationships = relationship_targets(archive, sheet_path)
        drawing_part = sheet_relationships.get(drawing.get(f"{_R}id", ""))
        if not drawing_part:
            return []
        drawing_root = ElementTree.fromstring(archive.read(drawing_part))
        drawing_relationships = relationship_targets(archive, drawing_part)
        elements = []
        for image_index, anchor in enumerate(drawing_root):
            picture = anchor.find(f"{_XDR}pic")
            if picture is None:
                continue
            position = anchor.find(f"{_XDR}from")
            row_node = position.find(f"{_XDR}row") if position is not None else None
            column_node = position.find(f"{_XDR}col") if position is not None else None
            image_context = {**metadata, "image_index": image_index}
            if row_node is not None and row_node.text is not None:
                image_context["image_anchor_row"] = int(row_node.text) + 1
            if column_node is not None and column_node.text is not None:
                image_context["image_anchor_column"] = int(column_node.text) + 1
            for image_part in embedded_image_parts(picture, drawing_relationships):
                elements.extend(ocr_embedded_image(
                    archive, image_part, self.config, image_context,
                ))
        return elements
