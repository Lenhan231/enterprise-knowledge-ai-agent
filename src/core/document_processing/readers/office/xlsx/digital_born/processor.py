"""Parse Excel worksheets, formulas, and tabular data from Office XML."""

from __future__ import annotations

import re
import zipfile
from typing import Any
from xml.etree import ElementTree

from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.chunking.router import build_chunks
from core.document_processing.headings import section_metadata
from ...scanned.image_ocr import relationship_targets
from ..scanned.processor import XlsxScannedProcessor

_X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_R = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _column_index(cell_reference: str) -> int:
    """Return a zero-based Excel column index from a cell reference."""
    letters = re.match(r"[A-Z]+", cell_reference.upper())
    if not letters:
        return 0
    index = 0
    for letter in letters.group():
        index = index * 26 + ord(letter) - ord("A") + 1
    return index - 1


def _make_headers(header_cells: dict[int, str]) -> list[str]:
    """Build stable, unique headers while retaining blank spreadsheet columns."""
    if not header_cells:
        return []
    headers = []
    seen: dict[str, int] = {}
    for column in range(max(header_cells) + 1):
        name = str(header_cells.get(column, "")).strip() or f"column_{column + 1}"
        seen[name] = seen.get(name, 0) + 1
        headers.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return headers


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
                },
            ))
            rows: list[dict[int, str]] = []
            formulas = []
            for row in root.findall("m:sheetData/m:row", ns):
                cells: dict[int, str] = {}
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
                    cells[_column_index(cell.attrib.get("r", "A"))] = value
                if cells:
                    rows.append(cells)
            if not rows:
                continue

            # XLSX exports often put a merged title or notes above the actual
            # header. The header row is the first row with the most populated
            # cells; ties retain the earliest row.
            header_index = max(range(len(rows)), key=lambda index: len(rows[index]))
            headers = _make_headers(rows[header_index])
            header_columns = sorted(set().union(*(row.keys() for row in rows[header_index:])))
            # Keep the table rectangular even when later rows contain values in
            # columns whose header cell was blank.
            if header_columns and header_columns[-1] >= len(headers):
                headers = _make_headers({
                    **rows[header_index],
                    **{column: "" for column in header_columns if column not in rows[header_index]},
                })
            records = []
            for row in rows[header_index + 1:]:
                if any(value not in (None, "") for value in row.values()):
                    records.append({header: row.get(column, "") for column, header in enumerate(headers)})
            table_index = len(tables)
            table_metadata = {"sheet_name": sheet.attrib["name"], "parser": "python-stdlib-xlsx-xml"}
            if formulas:
                table_metadata["formula_count"] = len(formulas)
            table = {"table_index": table_index, "columns": headers,
                     "rows": records, "metadata": table_metadata}
            tables.append(table)
            table_chunk_metadata = {
                **metadata,
                "sheet_name": sheet.attrib["name"],
                "table_index": table_index,
                **section_metadata(sheet.attrib["name"], 1),
            }
            chunks.extend(build_chunks(table, self.chunking, kind="table", metadata=table_chunk_metadata))
        return {"chunks": chunks, "tables": tables}
