"""Parse PowerPoint slide text and tables from Office XML."""

from __future__ import annotations

import re
import zipfile
from typing import Any
from xml.etree import ElementTree

from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.chunking.router import build_chunks
from core.document_processing.headings import section_metadata
from ...scanned.image_ocr import relationship_targets
from ..scanned.processor import PptxScannedProcessor

_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


class PptxProcessor:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.chunking = ChunkingConfig.from_config(config or {})

    def process(self, archive: zipfile.ZipFile, metadata: dict) -> dict:
        names = sorted((n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                       key=lambda n: int(re.search(r"slide(\d+)", n).group(1)))
        chunks, tables = [], []
        scanned = PptxScannedProcessor(self.config, self.chunking)
        for page_number, name in enumerate(names, 1):
            root = ElementTree.fromstring(archive.read(name))
            relationships = relationship_targets(archive, name)
            table_text_nodes = {
                id(node) for table_node in root.iter(f"{_A}tbl")
                for node in table_node.iter(f"{_A}t")
            }
            text = " ".join(
                node.text or "" for node in root.iter(f"{_A}t")
                if id(node) not in table_text_nodes
            )
            slide_title = None
            for shape in root.iter(f"{_P}sp"):
                placeholder = shape.find(f"{_P}nvSpPr/{_P}nvPr/{_P}ph")
                if placeholder is not None and placeholder.get("type") in {"title", "ctrTitle"}:
                    title = " ".join(node.text or "" for node in shape.iter(f"{_A}t")).strip()
                    if title:
                        slide_title = title
                        break
            chunks.extend(build_chunks(text, self.chunking, kind="text", metadata={
                **metadata,
                "slide_number": page_number,
                **section_metadata(slide_title, 1 if slide_title else None),
            }))
            chunks.extend(scanned.process_slide(
                archive,
                root,
                relationships,
                {
                    **metadata,
                    **section_metadata(slide_title, 1 if slide_title else None),
                    "slide_number": page_number,
                },
            ))
            for table_index, table in enumerate(root.iter(f"{_A}tbl")):
                rows = [
                    ["".join(node.text or "" for node in cell.iter(f"{_A}t")) for cell in row.findall(f"{_A}tc")]
                    for row in table.findall(f"{_A}tr")
                ]
                if not rows or not any(value for row in rows for value in row):
                    continue
                width = max(map(len, rows))
                headers = [
                    value.strip() or f"column_{index + 1}"
                    for index, value in enumerate(rows[0] + [""] * (width - len(rows[0])))
                ]
                records = [
                    dict(zip(headers, row + [None] * (width - len(row))))
                    for row in rows[1:]
                ]
                table_data = {
                    "table_index": table_index,
                    "columns": headers,
                    "rows": records,
                    "metadata": {
                        "slide_number": page_number,
                        "table_index": table_index,
                        "parser": "python-stdlib-pptx-xml",
                    },
                }
                tables.append(table_data)
                chunks.extend(build_chunks(table_data, self.chunking, kind="table", metadata={
                    **metadata,
                    "slide_number": page_number,
                    "table_index": table_index,
                    **section_metadata(slide_title, 1 if slide_title else None),
                }))
        return {"chunks": chunks, "tables": tables}
