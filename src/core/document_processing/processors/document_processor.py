"""Dispatch uploaded Office, text, image, and PDF files into one parse result."""

from __future__ import annotations

import io
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .pdf_processor import PDFProcessor
from .text_processor import split_text

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
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


def _split(
    text: str,
    metadata: dict[str, Any],
    size: int = 1100,
    overlap: int = 120,
    strategy: str = "sentence",
) -> list[dict]:
    chunks = split_text(text, size=size, overlap=overlap, strategy=strategy)
    return [{
        "text": value,
        "metadata": {
            **metadata,
            "chunk_index": index,
            "chunk_strategy": "sentence" if strategy == "semantic" else strategy,
            "chunk_size_chars": size,
            "chunk_overlap_chars": overlap if strategy == "fixed" else 0,
        },
    } for index, value in enumerate(chunks)]


class DocumentProcessor:
    """Parse a source file; original bytes and persistence belong to app/storage layers."""

    SUPPORTED = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.chunking_strategy = self.config.get("chunking_strategy", "sentence")
        if self.chunking_strategy not in {"fixed", "sentence", "semantic"}:
            raise ValueError("chunking_strategy must be 'fixed' or 'sentence'")
        self.chunk_size = int(self.config.get("chunk_size", 1100))
        self.chunk_overlap = int(self.config.get("chunk_overlap", 120))
        if self.chunk_size <= 0 or self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk size must be positive and overlap smaller than size")

    def process(self, filename: str, content: bytes, metadata: dict[str, Any]) -> dict[str, list[dict]]:
        suffix = Path(filename).suffix.lower()
        if suffix not in self.SUPPORTED:
            raise ValueError(f"Unsupported document format: {suffix or 'unknown'}")
        common = {**metadata, "filename": Path(filename).name, "format": suffix[1:].upper()}
        if suffix == ".pdf":
            result = PDFProcessor({
                "paddle_layout": False,
                "ocr_fallback": True,
                "ocr_language": "vie+eng",
                "extract_tables": True,
                "chunking_strategy": self.chunking_strategy,
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
            }).process({"content": content, "metadata": common})
        elif suffix in {".txt", ".md"}:
            result = {"chunks": _split(content.decode("utf-8-sig"), common, self.chunk_size, self.chunk_overlap, self.chunking_strategy), "tables": []}
        elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            text = self._ocr(content)
            tables = []
            if PDFProcessor._looks_like_numeric_table(text):
                import fitz

                layout = PDFProcessor({"ocr_fallback": True, "ocr_language": self.config.get("ocr_language", "vie+eng")})
                image = fitz.open(stream=content, filetype=suffix[1:])
                try:
                    page = image[0]
                    words = layout._ocr_page_words(page)
                    tables = PDFProcessor._tables_from_aligned_words(words, page.rect, 1)
                finally:
                    image.close()
            result = {
                "chunks": _split(text, {**common, "text_extraction_method": "tesseract"}, self.chunk_size, self.chunk_overlap, self.chunking_strategy),
                "tables": tables,
            }
        else:
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    _validate_office_archive(archive)
                    if suffix == ".docx":
                        result = self._docx(archive, common)
                    elif suffix == ".pptx":
                        result = self._pptx(archive, common)
                    else:
                        result = self._xlsx(archive, common)
            except (zipfile.BadZipFile, ElementTree.ParseError) as error:
                raise ValueError("Invalid Office archive or XML document") from error
        for index, chunk in enumerate(result["chunks"]):
            chunk["metadata"].update({key: value for key, value in common.items() if key not in chunk["metadata"]})
            chunk["metadata"]["chunk_index"] = index
        for table in result["tables"]:
            table.setdefault("metadata", {}).update({key: value for key, value in common.items() if key not in table["metadata"]})
        return result

    def _ocr(self, content: bytes) -> str:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", self.config.get("ocr_language", "vie+eng"), "--psm", "3"],
            input=content, capture_output=True, check=True, timeout=90,
        )
        return result.stdout.decode("utf-8", errors="replace").strip()

    def _docx(self, archive: zipfile.ZipFile, metadata: dict) -> dict:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        chunks = []
        for index, paragraph in enumerate(root.iter(f"{_W}p")):
            text = "".join(node.text or "" for node in paragraph.iter(f"{_W}t"))
            if text.strip():
                chunks.extend(_split(text, {**metadata, "paragraph_index": index}, self.chunk_size, self.chunk_overlap, self.chunking_strategy))
        tables = []
        for table_index, table in enumerate(root.iter(f"{_W}tbl")):
            rows = []
            for row in table.findall(f"{_W}tr"):
                rows.append(["".join(node.text or "" for node in cell.iter(f"{_W}t")) for cell in row.findall(f"{_W}tc")])
            if rows:
                columns = rows[0]
                tables.append({"page_number": 1, "table_index": table_index, "columns": columns,
                               "rows": [dict(zip(columns, row + [None] * (len(columns) - len(row)))) for row in rows[1:]],
                               "metadata": {"parser": "python-stdlib-docx-xml"}})
        return {"chunks": chunks, "tables": tables}

    def _pptx(self, archive: zipfile.ZipFile, metadata: dict) -> dict:
        names = sorted((n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                       key=lambda n: int(re.search(r"slide(\d+)", n).group(1)))
        chunks, tables = [], []
        for page_number, name in enumerate(names, 1):
            root = ElementTree.fromstring(archive.read(name))
            text = " ".join(node.text or "" for node in root.iter(f"{_A}t"))
            chunks.extend(_split(text, {**metadata, "page_number": page_number}, self.chunk_size, self.chunk_overlap, self.chunking_strategy))
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
                {**metadata, "sheet_name": sheet.attrib["name"], "page_number": sheet_index},
                self.chunk_size, self.chunk_overlap, self.chunking_strategy,
            ))
        return {"chunks": chunks, "tables": tables}
