"""Parse DOCX paragraphs, headings, formulas, and tables from Office XML."""

from __future__ import annotations

import re
import zipfile
from typing import Any
from xml.etree import ElementTree

from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.chunking.router import build_chunks
from core.document_processing.headings import section_metadata
from ...scanned.image_ocr import relationship_targets
from ..scanned.processor import DocxScannedProcessor

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"


class DocxProcessor:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.chunking = ChunkingConfig.from_config(config or {})

    def process(self, archive: zipfile.ZipFile, metadata: dict) -> dict:
        document_part = "word/document.xml"
        root = ElementTree.fromstring(archive.read(document_part))
        relationships = relationship_targets(archive, document_part)
        chunks = []
        tables = []
        scanned = DocxScannedProcessor(self.config, self.chunking)
        current_section_title = None
        current_heading_level = None
        pending_text: list[str] = []
        pending_metadata: dict[str, Any] | None = None
        pending_formulas: list[str] = []
        pending_end_index: int | None = None

        def flush_text() -> None:
            nonlocal pending_metadata, pending_formulas, pending_end_index
            if not pending_text or pending_metadata is None:
                return
            chunk_metadata = dict(pending_metadata)
            chunk_metadata["paragraph_end_index"] = pending_end_index
            if pending_formulas:
                chunk_metadata["contains_formula"] = True
                chunk_metadata["formula_text"] = "\n".join(pending_formulas)
            chunks.extend(build_chunks(
                "\n".join(pending_text), self.chunking, kind="text", metadata=chunk_metadata,
            ))
            pending_text.clear()
            pending_metadata = None
            pending_formulas = []
            pending_end_index = None

        body = root.find(f"{_W}body")
        for index, element in enumerate(body if body is not None else []):
            if element.tag == f"{_W}p":
                math_nodes = [node for node in element.iter() if node.tag == f"{_M}oMath"]
                text_nodes = [node for node in element.iter() if node.tag in {f"{_W}t", f"{_M}t"}]
                text = "".join(node.text or "" for node in text_nodes)
                paragraph_properties = element.find(f"{_W}pPr")
                style = paragraph_properties.find(f"{_W}pStyle") if paragraph_properties is not None else None
                style_name = style.get(f"{_W}val", "") if style is not None else ""
                heading_match = re.fullmatch(r"Heading([1-9])", style_name, re.IGNORECASE)
                if heading_match:
                    flush_text()
                    current_section_title = text.strip()
                    current_heading_level = int(heading_match.group(1))
                paragraph_metadata = {
                    **metadata,
                    "paragraph_index": index,
                    **section_metadata(current_section_title, current_heading_level),
                }
                if text.strip():
                    if pending_metadata is None:
                        pending_metadata = paragraph_metadata
                    pending_text.append(text)
                    pending_end_index = index
                    pending_formulas.extend(
                        "".join(node.text or "" for node in math.iter(f"{_M}t"))
                        for math in math_nodes
                    )
                image_chunks = scanned.process_element(archive, element, relationships, paragraph_metadata)
                if image_chunks:
                    flush_text()
                    chunks.extend(image_chunks)
            elif element.tag == f"{_W}tbl":
                flush_text()
                for paragraph_index, paragraph in enumerate(element.iter(f"{_W}p")):
                    chunks.extend(scanned.process_element(
                        archive,
                        paragraph,
                        relationships,
                        {
                            **metadata,
                            "paragraph_index": paragraph_index,
                            **section_metadata(current_section_title, current_heading_level),
                            "table_index": len(tables),
                        },
                    ))
                rows = [
                    ["".join(node.text or "" for node in cell.iter(f"{_W}t"))
                     for cell in row.findall(f"{_W}tc")]
                    for row in element.findall(f"{_W}tr")
                ]
                if not rows or not any(value for row in rows for value in row):
                    continue
                width = max(map(len, rows))
                columns = [
                    value.strip() or f"column_{column_index + 1}"
                    for column_index, value in enumerate(rows[0] + [""] * (width - len(rows[0])))
                ]
                records = [
                    dict(zip(columns, row + [""] * (width - len(row))))
                    for row in rows[1:]
                ]
                table_index = len(tables)
                table = {
                    "table_index": table_index,
                    "columns": columns,
                    "rows": records,
                    "metadata": {
                        "parser": "python-stdlib-docx-xml",
                        "paragraph_index": index,
                    },
                }
                tables.append(table)
                chunks.extend(build_chunks(table, self.chunking, kind="table", metadata={
                    **metadata,
                    "paragraph_index": index,
                    "table_index": table_index,
                    **section_metadata(current_section_title, current_heading_level),
                }))
        flush_text()
        return {"chunks": chunks, "tables": tables}
