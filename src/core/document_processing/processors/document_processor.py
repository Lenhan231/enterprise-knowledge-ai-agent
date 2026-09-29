"""Dispatch uploaded Office, text, image, and PDF files into one parse result."""

from __future__ import annotations

import io
import logging
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .pdf_processor import PDFProcessor
from .text_processor import split_text

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
logger = logging.getLogger(__name__)


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
        self.paddle_formula_recognition = bool(self.config.get("paddle_formula_recognition", False))
        self.paddle_layout = bool(self.config.get("paddle_layout", False) or self.paddle_formula_recognition)
        self.vision_captioning = bool(self.config.get("vision_captioning", False))
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
                "paddle_layout": self.paddle_layout,
                "paddle_formula_recognition": self.paddle_formula_recognition,
                "vision_captioning": self.vision_captioning,
                "ocr_fallback": True,
                "ocr_language": "vie+eng",
                "tesseract_psm": self.config.get("tesseract_psm", 11),
                "tesseract_table_psm": self.config.get("tesseract_table_psm", 3),
                "ocr_render_scale": self.config.get("ocr_render_scale", 1.5),
                "ocr_table_render_scale": self.config.get("ocr_table_render_scale", 2.5),
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

                table_render_scale = self.config.get("ocr_table_render_scale", 2.5)
                layout = PDFProcessor({
                    "ocr_fallback": True,
                    "ocr_language": self.config.get("ocr_language", "vie+eng"),
                    "tesseract_table_psm": self.config.get("tesseract_table_psm", 6),
                    "ocr_render_scale": table_render_scale,
                    "ocr_table_render_scale": table_render_scale,
                })
                image = fitz.open(stream=content, filetype=suffix[1:])
                try:
                    page = image[0]
                    words = layout._ocr_page_words(page)
                    tables = PDFProcessor._tables_from_aligned_words(
                        words, page.rect, 1,
                        ocr_metadata=layout._ocr_table_metadata(),
                    )
                finally:
                    image.close()
            result = {
                "chunks": _split(text, {**common, "text_extraction_method": "tesseract"}, self.chunk_size, self.chunk_overlap, self.chunking_strategy),
                "tables": tables,
            }
            if self.vision_captioning:
                try:
                    image_bytes, mime_type = self._caption_image_input(content, suffix)
                    from core.llm.groq_provider import GroqProvider

                    provider = GroqProvider()
                    try:
                        caption = provider.caption_image(image_bytes, mime_type)
                        model_name = provider.vision_model_name
                    finally:
                        provider.close()
                    result["chunks"].extend(_split(f"AI-generated image caption (unverified): {caption}", {
                        **common,
                        "text_extraction_method": "groq_vision_caption",
                        "element_type": "figure_caption",
                        "layout_type": "figure_caption",
                        "caption_model": model_name,
                        "is_model_generated": True,
                    }, self.chunk_size, self.chunk_overlap, self.chunking_strategy))
                except Exception as error:
                    logger.warning(
                        "Vision caption failed for uploaded image %s (%s)",
                        common["filename"], type(error).__name__,
                    )
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
            ["tesseract", "stdin", "stdout", "-l", self.config.get("ocr_language", "vie+eng"), "--psm", str(self.config.get("tesseract_psm", 11))],
            input=content, capture_output=True, check=True, timeout=90,
        )
        return result.stdout.decode("utf-8", errors="replace").strip()

    @staticmethod
    def _caption_image_input(content: bytes, suffix: str) -> tuple[bytes, str]:
        if suffix in {".png", ".jpg", ".jpeg"}:
            return content, "image/png" if suffix == ".png" else "image/jpeg"
        if len(content) > 14 * 1024 * 1024:
            raise ValueError("TIFF is too large for the bounded vision caption request")
        import fitz

        image = fitz.open(stream=content, filetype=suffix[1:])
        try:
            page = image[0]
            scale = min(1.0, 2048 / max(page.rect.width, page.rect.height))
            return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png"), "image/png"
        finally:
            image.close()

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
                chunks.extend(_split(text, paragraph_metadata, self.chunk_size, self.chunk_overlap, self.chunking_strategy))
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
                }, self.chunk_size, self.chunk_overlap, self.chunking_strategy))
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
            }, self.chunk_size, self.chunk_overlap, self.chunking_strategy))
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
                self.chunk_size, self.chunk_overlap, self.chunking_strategy,
            ))
        return {"chunks": chunks, "tables": tables}
