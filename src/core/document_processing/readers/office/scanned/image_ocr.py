"""Resolve embedded Office images and turn their OCR text into parser chunks."""

from __future__ import annotations

import posixpath
import zipfile
from typing import Any
from xml.etree import ElementTree

from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.pipelines.helpers.office_image_ocr import process_embedded_image

_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_DRAWING = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def relationship_targets(archive: zipfile.ZipFile, source_part: str) -> dict[str, str]:
    """Map internal relationship IDs to safe package paths."""
    directory, filename = posixpath.split(source_part)
    rels_part = posixpath.join(directory, "_rels", f"{filename}.rels")
    if rels_part not in archive.namelist():
        return {}

    root = ElementTree.fromstring(archive.read(rels_part))
    names = set(archive.namelist())
    targets = {}
    for relation in root.findall(f"{_REL}Relationship"):
        if relation.get("TargetMode") == "External":
            continue
        target = relation.get("Target", "")
        part = posixpath.normpath(
            target.lstrip("/") if target.startswith("/")
            else posixpath.join(directory, target)
        )
        if part == ".." or part.startswith("../") or part not in names:
            continue
        targets[relation.get("Id", "")] = part
    return targets


def embedded_image_parts(element: ElementTree.Element, targets: dict[str, str]) -> list[str]:
    """Return image package paths referenced by DrawingML blips in document order."""
    return [
        targets[relationship_id]
        for blip in element.iter(f"{_DRAWING}blip")
        if (relationship_id := blip.get(_REL_ID)) in targets
    ]


def ocr_embedded_image(
    archive: zipfile.ZipFile,
    image_part: str,
    config: dict[str, Any],
    chunking: ChunkingConfig,
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """Parse a single embedded image with the selected pipeline."""
    return process_embedded_image(archive, image_part, config, chunking, metadata)
