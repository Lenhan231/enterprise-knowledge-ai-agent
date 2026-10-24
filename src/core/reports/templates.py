"""Parse and populate bounded Markdown and DOCX report templates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph


MAX_TEMPLATE_BYTES = 10 * 1024 * 1024
MAX_DOCX_EXPANDED_BYTES = 20 * 1024 * 1024
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?$")


@dataclass(frozen=True)
class ReportTemplate:
    format: str
    content: str | bytes
    headings: tuple[str, ...]
    table_headers: tuple[tuple[str, ...], ...]


def parse_report_template(filename: str, content: bytes) -> ReportTemplate:
    if len(content) > MAX_TEMPLATE_BYTES:
        raise ValueError("Template exceeds the 10 MiB upload limit")
    extension = filename.rsplit(".", 1)[-1].casefold() if "." in filename else ""
    if extension == "md":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("Markdown templates must be UTF-8") from error
        headings = tuple(match.group(2).strip() for line in text.splitlines()
                         if (match := _HEADING.match(line)))
        tables = _markdown_table_headers(text)
        if not headings:
            raise ValueError("Template must contain at least one heading")
        if len(headings) != len(set(headings)):
            raise ValueError("Template headings must be unique")
        return ReportTemplate("markdown", text, headings, tables)
    if extension != "docx":
        raise ValueError("Template must be a DOCX or Markdown file")
    _validate_docx_package(content)
    try:
        document = Document(BytesIO(content))
    except Exception as error:
        raise ValueError("DOCX template could not be read") from error
    headings = tuple(paragraph.text.strip() for paragraph in document.paragraphs
                     if paragraph.style.name.startswith("Heading") and paragraph.text.strip())
    if not headings:
        raise ValueError("Template must contain at least one heading")
    if len(headings) != len(set(headings)):
        raise ValueError("Template headings must be unique")
    table_headers = tuple(tuple(cell.text.strip() for cell in table.rows[0].cells)
                          for table in document.tables if table.rows)
    return ReportTemplate("docx", content, headings, table_headers)


def render_report_template(template: ReportTemplate, sections: dict[str, str],
                           tables: list[list[list[str]]]) -> str | bytes:
    if set(sections) != set(template.headings) or any(
        not isinstance(value, str) or not value.strip() for value in sections.values()
    ):
        raise ValueError("Report must provide non-empty content for every template heading")
    if len(tables) != len(template.table_headers):
        raise ValueError("Report table count must match the template")
    for headers, rows in zip(template.table_headers, tables):
        if any(not isinstance(row, list) or len(row) != len(headers) for row in rows):
            raise ValueError("Report table rows must match the template column count")
        if any(not isinstance(cell, str) for row in rows for cell in row):
            raise ValueError("Report table cells must be text")
    if template.format == "markdown":
        return _render_markdown(template, sections, tables)
    return _render_docx(template, sections, tables)


def _markdown_table_headers(text: str) -> tuple[tuple[str, ...], ...]:
    lines = text.splitlines()
    headers = []
    for index, line in enumerate(lines[:-1]):
        if line.strip().startswith("|") and _TABLE_SEPARATOR.match(lines[index + 1].strip()):
            headers.append(tuple(cell.strip() for cell in line.strip().strip("|").split("|")))
    return tuple(headers)


def _render_markdown(template: ReportTemplate, sections: dict[str, str],
                     tables: list[list[list[str]]]) -> str:
    source_lines = str(template.content).splitlines()
    output = []
    index = 0
    table_index = 0
    while index < len(source_lines):
        line = source_lines[index]
        heading = _HEADING.match(line)
        output.append(line)
        if heading:
            body = sections[heading.group(2).strip()]
            output.extend(("", body.strip(), ""))
            index += 1
            continue
        if (index + 1 < len(source_lines) and line.strip().startswith("|")
                and _TABLE_SEPARATOR.match(source_lines[index + 1].strip())):
            headers = template.table_headers[table_index]
            rows = tables[table_index]
            output.append(source_lines[index + 1])
            output.extend("| " + " | ".join(row) + " |" for row in rows)
            table_index += 1
            index += 2
            while index < len(source_lines) and source_lines[index].strip().startswith("|"):
                index += 1
            continue
        index += 1
    return "\n".join(output).strip() + "\n"


def _render_docx(template: ReportTemplate, sections: dict[str, str],
                 tables: list[list[list[str]]]) -> bytes:
    document = Document(BytesIO(template.content))
    headings = [paragraph for paragraph in document.paragraphs
                if paragraph.style.name.startswith("Heading") and paragraph.text.strip()]
    for paragraph in reversed(headings):
        previous = paragraph._p
        for text in reversed([part.strip() for part in sections[paragraph.text.strip()].splitlines() if part.strip()]):
            element = OxmlElement("w:p")
            previous.addnext(element)
            Paragraph(element, paragraph._parent).add_run(text)
            previous = element
    for table, rows in zip(document.tables, tables):
        while len(table.rows) > 1:
            table._tbl.remove(table.rows[-1]._tr)
        for values in rows:
            cells = table.add_row().cells
            for cell, value in zip(cells, values):
                cell.text = value
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _validate_docx_package(content: bytes) -> None:
    if not content.startswith(b"PK"):
        raise ValueError("DOCX file content is invalid")
    try:
        with ZipFile(BytesIO(content)) as package:
            if package.testzip() is not None:
                raise ValueError("DOCX file content is invalid")
            expanded_size = 0
            for item in package.infolist():
                path = PurePosixPath(item.filename)
                if path.is_absolute() or ".." in path.parts or "vbaProject.bin" in item.filename:
                    raise ValueError("DOCX package contains unsupported content")
                expanded_size += item.file_size
                if expanded_size > MAX_DOCX_EXPANDED_BYTES:
                    raise ValueError("DOCX expands beyond the 20 MiB processing limit")
    except BadZipFile as error:
        raise ValueError("DOCX file content is invalid") from error
