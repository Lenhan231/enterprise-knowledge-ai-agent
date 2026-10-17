"""Parse Excel worksheets, formulas, and tabular data from Office XML."""

from __future__ import annotations

import re
import zipfile
from typing import Any
from xml.etree import ElementTree

from core.document_processing.chunking.chunk_builder import build_text_chunks
from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.headings import section_metadata
from ...scanned.image_ocr import relationship_targets
from ..scanned.processor import XlsxScannedProcessor

_X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_R = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class XlsxProcessor:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.chunking = ChunkingConfig.from_config(config or {})

    def process(self, archive: zipfile.ZipFile, metadata: dict) -> dict:
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
              "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rels = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_root.findall(f"{_PKG_R}Relationship")}
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in item.iter(f"{_X}t")) for item in shared_root.findall("m:si", ns)]
        chunks, tables = [], []
        scanned = XlsxScannedProcessor(self.config, self.chunking)
        for sheet_index, sheet in enumerate(workbook.findall("m:sheets/m:sheet", ns), 1):
            target = rels[sheet.attrib[f"{_R}id"]].lstrip("/")
            path = target if target.startswith("xl/") else "xl/" + target
            root = ElementTree.fromstring(archive.read(path))
            chunks.extend(scanned.process_sheet(
                archive,
                root,
                path,
                {
                    **metadata,
                    "sheet_name": sheet.attrib["name"],
                    **section_metadata(sheet.attrib["name"], 1),
                    "page_number": sheet_index,
                },
            ))
            rows = []
            formulas = []
            for row in root.findall("m:sheetData/m:row", ns):
                cells = []
                for cell in row.findall("m:c", ns):
                    value_node = cell.find("m:v", ns)
                    value = value_node.text if value_node is not None else ""
                    if cell.attrib.get("t") == "s" and value:
                        value = shared[int(value)]
                    elif cell.attrib.get("t") == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iter(f"{_X}t"))
                    formula_node = cell.find("m:f", ns)
                    if formula_node is not None:
                        formulas.append({
                            "cell": cell.attrib.get("r"),
                            "formula": f"={formula_node.text}" if formula_node.text else None,
                            "formula_type": formula_node.attrib.get("t"),
                            "formula_ref": formula_node.attrib.get("ref"),
                            "cached_value": value,
                        })
                    cells.append((cell.attrib.get("r", ""), value))
                if cells:
                    rows.append(cells)
            if not rows:
                continue
            headers = [value or ref for ref, value in rows[0]]
            records = []
            for row in rows[1:]:
                values = {re.sub(r"\d+$", "", ref): value for ref, value in row}
                records.append({header: values.get(re.sub(r"\d+$", "", ref), "")
                                for (ref, _), header in zip(rows[0], headers)})
            table_index = len(tables)
            table_metadata = {"sheet_name": sheet.attrib["name"], "parser": "python-stdlib-xlsx-xml"}
            if formulas:
                table_metadata["formulas"] = formulas
            tables.append({"page_number": sheet_index, "table_index": table_index, "columns": headers,
                           "rows": records, "metadata": table_metadata})
            lines = [" | ".join(headers)]
            for record in records:
                lines.append(" | ".join(str(record.get(header, "")) for header in headers))
            if formulas:
                lines.append("Formulas (cached values may be stale):")
                lines.extend(
                    f"{formula['cell']}: {formula['formula'] or '[shared formula without inline expression]'}"
                    + (f" [cached value: {formula['cached_value']}]" if formula["cached_value"] != "" else "")
                    for formula in formulas
                )
            chunks.extend(build_text_chunks(
                "\n".join(lines),
                {
                    **metadata,
                    "sheet_name": sheet.attrib["name"],
                    **section_metadata(sheet.attrib["name"], 1),
                    "page_number": sheet_index,
                },
                self.chunking,
            ))
        return {"chunks": chunks, "tables": tables}
