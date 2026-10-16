"""Optional MinerU Basic adapter for isolated PDF parsing runs."""

from __future__ import annotations

import json
import os
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import fitz

from .layout_processor import _HEADING_PATTERNS
from ..text.processor import TextProcessor


def _markdown_table(markdown: str) -> tuple[list[str], list[dict[str, str]]] | None:
    lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    rows = [
        [cell.strip() for cell in line.strip("|").split("|")]
        for line in lines if "|" in line
    ]
    rows = [row for row in rows if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in row)]
    if len(rows) < 2:
        return None
    columns = rows[0]
    values = [row + [""] * max(0, len(columns) - len(row)) for row in rows[1:]]
    return columns, [dict(zip(columns, row[:len(columns)])) for row in values]


class _TableHTMLParser(HTMLParser):
    """Read MinerU's HTML table blocks into rows while preserving row spans."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[str, int, int]]] = []
        self.row: list[tuple[str, int, int]] | None = None
        self.cell: list[str] | None = None
        self.cell_rowspan = 1
        self.cell_colspan = 1
        self.table_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs)
        if tag == "table":
            self.table_depth += 1
        elif self.table_depth == 1 and tag == "tr":
            self.row = []
        elif self.table_depth == 1 and tag in {"td", "th"} and self.row is not None:
            self.cell = []
            self.cell_rowspan = max(1, int(attrs.get("rowspan") or 1))
            self.cell_colspan = max(1, int(attrs.get("colspan") or 1))
        elif self.cell is not None and tag == "br":
            self.cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self.table_depth == 1 and tag in {"td", "th"} and self.cell is not None:
            value = " ".join("".join(self.cell).split())
            self.row.append((value, self.cell_rowspan, self.cell_colspan))
            self.cell = None
        elif self.table_depth == 1 and tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.table_depth:
            self.table_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)


def _html_table(content: str) -> tuple[list[str], list[dict[str, str]]] | None:
    parser = _TableHTMLParser()
    parser.feed(content)
    if len(parser.rows) < 2:
        return None

    grid: list[list[str]] = []
    spans: dict[int, tuple[int, str]] = {}
    for row_index, cells in enumerate(parser.rows):
        row: list[str] = []
        for column, (end_row, value) in spans.items():
            if end_row > row_index:
                while len(row) <= column:
                    row.append("")
                row[column] = value

        column = 0
        for value, rowspan, colspan in cells:
            while column < len(row) and row[column]:
                column += 1
            for offset in range(colspan):
                target = column + offset
                while len(row) <= target:
                    row.append("")
                row[target] = value
                if rowspan > 1:
                    spans[target] = (row_index + rowspan, value)
            column += colspan
        grid.append(row)

    columns = [value or f"column_{index + 1}" for index, value in enumerate(grid[0])]
    rows = [
        dict(zip(columns, row + [""] * max(0, len(columns) - len(row))))
        for row in grid[1:]
    ]
    return columns, rows


class MineruProcessor:
    """Run MinerU's Basic tier and map its structured JSON into parser output."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def process(self, source: bytes | str | Path, file_path: str | None, document: dict[str, Any]) -> dict[str, Any]:
        try:
            from gradio_client import handle_file
        except ImportError as error:
            raise RuntimeError("Hugging Face MinerU API client is unavailable; install project dependencies") from error

        input_pdf = Path(file_path) if file_path else None
        if input_pdf is None or not input_pdf.is_file():
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
                temporary.write(source if isinstance(source, bytes) else Path(source).read_bytes())
                temporary.flush()
                return self._process_upload(handle_file(temporary.name), source, document)
        return self._process_upload(handle_file(str(input_pdf)), source, document)

    def _process_upload(self, upload: Any, source: bytes | str | Path,
                        document: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._call_api(upload, source, document)
        except RuntimeError as error:
            if "Unsupported warp settings" not in str(error):
                raise

        flattened_pdf = self._flatten_pdf(source)
        from gradio_client import handle_file

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
            temporary.write(flattened_pdf)
            temporary.flush()
            result = self._call_api(handle_file(temporary.name), source, document)
        result["metadata"]["mineru_preprocessing"] = "rasterized_retry_after_unsupported_warp"
        return result

    @staticmethod
    def _flatten_pdf(source: bytes | str | Path) -> bytes:
        pdf_bytes = source if isinstance(source, bytes) else Path(source).read_bytes()
        original = fitz.open(stream=pdf_bytes, filetype="pdf")
        flattened = fitz.open()
        try:
            for page in original:
                rect = page.rect
                scale = min(2.5, 1800 / rect.width, 2400 / rect.height)
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale),
                    colorspace=fitz.csGRAY,
                    alpha=False,
                )
                target = flattened.new_page(width=rect.width, height=rect.height)
                target.insert_image(
                    target.rect,
                    stream=pixmap.tobytes("jpeg", jpg_quality=90),
                )
            return flattened.tobytes(garbage=4, deflate=True)
        finally:
            original.close()
            flattened.close()

    def _call_api(self, upload: Any, source: bytes | str | Path, document: dict[str, Any]) -> dict[str, Any]:
        space = os.getenv("MINERU_HF_SPACE", "opendatalab/MinerU")
        token = (
            os.getenv("HF_TOKEN")
            or os.getenv("HUGGINGFACE_API_KEY")
            or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        )
        try:
            from gradio_client import Client

            result = Client(space, token=token, verbose=False).predict(
                file_path=upload,
                tier_position=1,
                raw_page_range="",
                force_ocr=False,
                api_name="/convert_handler",
            )
            if not isinstance(result, (list, tuple)) or len(result) < 8:
                raise RuntimeError("Hugging Face MinerU returned an unexpected response")
            raw_payload = result[7]
            if not raw_payload:
                status = re.sub(r"<[^>]+>", " ", unescape(str(result[0] or "")))
                status = " ".join(status.split())[:400]
                raise RuntimeError(
                    "Hugging Face MinerU returned no parsed result. "
                    f"{status or 'Check the Space status and Hugging Face API quota.'}"
                )
            try:
                payload = json.loads(raw_payload)
            except (TypeError, json.JSONDecodeError) as error:
                raise RuntimeError("Hugging Face MinerU returned invalid JSON") from error
            version = (payload.get("metadata") or {}).get("producer", {}).get("version")
        except RuntimeError:
            raise
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "Hugging Face MinerU returned an unreadable response. "
                "The Space may be out of quota; configure a valid Hugging Face token "
                "with HF_TOKEN or HUGGINGFACE_API_KEY and check the Space status."
            ) from error
        except Exception as error:
            raise RuntimeError(f"Hugging Face MinerU request failed: {type(error).__name__}") from error
        return self._to_parser_result(payload, source, document, version, space)

    def _to_parser_result(self, payload: dict[str, Any], source: bytes | str | Path,
                          document: dict[str, Any], version: str | None, space: str) -> dict[str, Any]:
        pdf = fitz.open(stream=source, filetype="pdf") if isinstance(source, bytes) else fitz.open(source)
        tables: list[dict[str, Any]] = []
        chunks: list[dict[str, Any]] = []
        text_processor = TextProcessor(self.config)
        page_count = len(pdf)
        try:
            for page_data in payload.get("pages", []):
                page_number = int(page_data.get("page_idx", 0)) + 1
                if not 1 <= page_number <= page_count:
                    continue
                page_rect = pdf[page_number - 1].rect
                for block in page_data.get("blocks", []):
                    kind = str(block.get("type", "text")).lower()
                    text = " ".join(str(block.get("content") or "").split())
                    if not text or kind in {"header", "footer", "page_number", "image", "chart"}:
                        continue
                    bbox = block.get("bbox")
                    point_bbox = None
                    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                        point_bbox = [
                            float(bbox[0]) * page_rect.width,
                            float(bbox[1]) * page_rect.height,
                            float(bbox[2]) * page_rect.width,
                            float(bbox[3]) * page_rect.height,
                        ]

                    element_type = "title" if kind in {"doc_title", "paragraph_title"} else kind
                    table_index = None
                    if kind == "table":
                        parsed_table = (
                            _html_table(text) if re.search(r"<table\b", text, re.IGNORECASE)
                            else _markdown_table(text)
                        )
                        if parsed_table:
                            columns, rows = parsed_table
                            table_index = sum(item["page_number"] == page_number for item in tables)
                            tables.append({
                                "page_number": page_number, "table_index": table_index,
                                "columns": columns, "rows": rows,
                                "metadata": {
                                    "element_type": "table", "layout_type": "table",
                                    "bbox": point_bbox, "bbox_coordinate_system": "pdf_point",
                                    "parser": "mineru", "mineru_tier": "basic",
                                    "table_extraction_method": (
                                        "mineru_html_table" if re.search(r"<table\b", text, re.IGNORECASE)
                                        else "mineru_markdown_table"
                                    ),
                                },
                            })
                            text = "Columns: " + " | ".join(columns) + "\n" + "\n".join(
                                f"Row {row_index}: " + " | ".join(
                                    f"{column}: {row.get(column, '')}" for column in columns
                                )
                                for row_index, row in enumerate(rows, start=1)
                            )
                        element_type = "table"
                    heading_kind = next(
                        (name for name, pattern in _HEADING_PATTERNS.items() if pattern.match(text)),
                        None,
                    )
                    if heading_kind:
                        element_type = "title"
                    for chunk in text_processor.process({"text": text, "metadata": {}}):
                        chunk["metadata"].update({
                            "page_number": page_number,
                            "element_type": element_type,
                            "layout_type": element_type,
                            "bbox": point_bbox,
                            "bbox_coordinate_system": "pdf_point",
                            "text_extraction_method": "mineru.basic",
                            "parser": "mineru", "mineru_tier": "basic",
                            "chunk_index": len(chunks),
                        })
                        if heading_kind:
                            chunk["metadata"]["heading_kind"] = heading_kind
                        if table_index is not None:
                            chunk["metadata"]["table_index"] = table_index
                        chunks.append(chunk)
        finally:
            pdf.close()
        return {
            "chunks": chunks,
            "tables": tables,
            "metadata": {
                "page_count": page_count,
                "layout_parser": "mineru.huggingface_space",
                "mineru_version": version,
                "mineru_space": space,
            },
        }
