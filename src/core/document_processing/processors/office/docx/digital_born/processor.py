"""Parse DOCX paragraphs, headings, formulas, and tables from Office XML."""

from __future__ import annotations

import re
import zipfile
from typing import Any
from xml.etree import ElementTree

from core.document_processing.chunking.chunk_builder import build_text_chunks
from core.document_processing.chunking.config import ChunkingConfig
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
                    current_section_title = text.strip()
                    current_heading_level = int(heading_match.group(1))
                paragraph_metadata = {
                    **metadata,
                    "paragraph_index": index,
                    **section_metadata(current_section_title, current_heading_level),
                }
                if text.strip() and math_nodes:
                    paragraph_metadata["contains_formula"] = True
                    paragraph_metadata["formula_text"] = "".join(
                        node.text or "" for node in math_nodes[0].iter(f"{_M}t")
                    )
                if text.strip():
                    chunks.extend(build_text_chunks(text, paragraph_metadata, self.chunking))
                chunks.extend(scanned.process_element(
                    archive, element, relationships, paragraph_metadata,
                ))
            elif element.tag == f"{_W}tbl":
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
                tables.append({
                    "page_number": 1,
                    "table_index": table_index,
                    "columns": columns,
                    "rows": records,
                    "metadata": {"parser": "python-stdlib-docx-xml"},
                })
                table_text = "\n\n".join(
                    " | ".join(f"{column}: {record[column]}" for column in columns)
                    for record in records
                ) or " | ".join(columns)
                chunks.extend(build_text_chunks(table_text, {
                    **metadata,
                    "paragraph_index": index,
                    **section_metadata(current_section_title, current_heading_level),
                    "layout_type": "table",
                    "table_index": table_index,
                }, self.chunking))
        return {"chunks": chunks, "tables": tables}
