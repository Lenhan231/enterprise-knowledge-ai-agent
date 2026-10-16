"""Bounded parsers for DOCX, PPTX and XLSX Office Open XML files."""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any
from xml.etree import ElementTree

from core.chunking.text_chunker import ChunkingConfig, split_document_text as _split

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_R = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_MAX_OFFICE_ARCHIVE_ENTRIES = 10_000
_MAX_OFFICE_MEMBER_BYTES = 100 * 1024 * 1024
_MAX_OFFICE_TOTAL_BYTES = 200 * 1024 * 1024
_MAX_OFFICE_COMPRESSION_RATIO = 200
def _validate_office_archive(archive: zipfile.ZipFile) -> None:
    """Reject Office packages whose declared expansion could exhaust app resources."""
    members = archive.infolist()
    if len(members) > _MAX_OFFICE_ARCHIVE_ENTRIES:
        raise ValueError("Office document contains too many archive entries")

    total_size = 0
    for member in members:
        if member.is_dir():
            continue
        if member.file_size > _MAX_OFFICE_MEMBER_BYTES:
            raise ValueError(f"Office archive member is too large: {member.filename}")
        total_size += member.file_size
        if total_size > _MAX_OFFICE_TOTAL_BYTES:
            raise ValueError("Office document expands beyond the 200 MiB processing limit")
        if member.file_size and member.compress_size == 0:
            raise ValueError(f"Office archive member has an invalid compressed size: {member.filename}")
        if member.compress_size and member.file_size / member.compress_size > _MAX_OFFICE_COMPRESSION_RATIO:
            raise ValueError(f"Office archive member has a suspicious compression ratio: {member.filename}")


class OfficeProcessor:
    """Extract text and structured tables from supported Office documents."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.chunking = ChunkingConfig.from_config(self.config)

    def process(self, suffix: str, content: bytes, metadata: dict[str, Any]) -> dict[str, list[dict]]:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                _validate_office_archive(archive)
                if suffix == ".docx":
                    return self._docx(archive, metadata)
                if suffix == ".pptx":
                    return self._pptx(archive, metadata)
                if suffix == ".xlsx":
                    return self._xlsx(archive, metadata)
                raise ValueError(f"Unsupported Office format: {suffix}")
        except (zipfile.BadZipFile, ElementTree.ParseError) as error:
            raise ValueError("Invalid Office archive or XML document") from error

    def _docx(self, archive: zipfile.ZipFile, metadata: dict) -> dict:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        chunks = []
        tables = []
        current_section_title = None
        body = root.find(f"{_W}body")
        for index, element in enumerate(body if body is not None else []):
            if element.tag == f"{_W}p":
                math_nodes = [node for node in element.iter() if node.tag == f"{_M}oMath"]
                text_nodes = [node for node in element.iter() if node.tag in {f"{_W}t", f"{_M}t"}]
                text = "".join(node.text or "" for node in text_nodes)
                if not text.strip():
                    continue
                paragraph_properties = element.find(f"{_W}pPr")
                style = paragraph_properties.find(f"{_W}pStyle") if paragraph_properties is not None else None
                style_name = style.get(f"{_W}val", "") if style is not None else ""
                if re.fullmatch(r"Heading[1-9]", style_name, re.IGNORECASE):
                    current_section_title = text.strip()
                paragraph_metadata = {
                    **metadata,
                    "paragraph_index": index,
                    "section_title": current_section_title,
                }
                if math_nodes:
                    paragraph_metadata["contains_formula"] = True
                    paragraph_metadata["formula_text"] = "".join(
                        node.text or "" for node in math_nodes[0].iter(f"{_M}t")
                    )
                chunks.extend(_split(text, paragraph_metadata, self.chunking.size, self.chunking.overlap, self.chunking.strategy))
            elif element.tag == f"{_W}tbl":
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
                chunks.extend(_split(table_text, {
                    **metadata,
                    "paragraph_index": index,
                    "section_title": current_section_title,
                    "layout_type": "table",
                    "table_index": table_index,
                }, self.chunking.size, self.chunking.overlap, self.chunking.strategy))
        return {"chunks": chunks, "tables": tables}

    def _pptx(self, archive: zipfile.ZipFile, metadata: dict) -> dict:
        names = sorted((n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                       key=lambda n: int(re.search(r"slide(\d+)", n).group(1)))
        chunks, tables = [], []
        for page_number, name in enumerate(names, 1):
            root = ElementTree.fromstring(archive.read(name))
            text = " ".join(node.text or "" for node in root.iter(f"{_A}t"))
            slide_title = None
            for shape in root.iter(f"{_P}sp"):
                placeholder = shape.find(f"{_P}nvSpPr/{_P}nvPr/{_P}ph")
                if placeholder is not None and placeholder.get("type") in {"title", "ctrTitle"}:
                    title = " ".join(node.text or "" for node in shape.iter(f"{_A}t")).strip()
                    if title:
                        slide_title = title
                        break
            chunks.extend(_split(text, {
                **metadata,
                "page_number": page_number,
                "section_title": slide_title,
            }, self.chunking.size, self.chunking.overlap, self.chunking.strategy))
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
                tables.append({
                    "page_number": page_number,
                    "table_index": table_index,
                    "columns": headers,
                    "rows": records,
                    "metadata": {
                        "slide_number": page_number,
                        "parser": "python-stdlib-pptx-xml",
                    },
                })
        return {"chunks": chunks, "tables": tables}

    def _xlsx(self, archive: zipfile.ZipFile, metadata: dict) -> dict:
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
        for sheet_index, sheet in enumerate(workbook.findall("m:sheets/m:sheet", ns), 1):
            target = rels[sheet.attrib[f"{_R}id"]].lstrip("/")
            path = target if target.startswith("xl/") else "xl/" + target
            root = ElementTree.fromstring(archive.read(path))
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
            chunks.extend(_split(
                "\n".join(lines),
                {
                    **metadata,
                    "sheet_name": sheet.attrib["name"],
                    "section_title": sheet.attrib["name"],
                    "page_number": sheet_index,
                },
                self.chunking.size, self.chunking.overlap, self.chunking.strategy,
            ))
        return {"chunks": chunks, "tables": tables}
