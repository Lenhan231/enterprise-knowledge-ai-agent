"""Optional MinerU Basic adapter for isolated PDF parsing runs."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import fitz

from core.document_processing.headings import HEADING_PATTERNS, heading_level, section_metadata
from core.document_processing.pipelines.table_parser import parse_html_table
from core.document_processing.processors.text.digital_born.processor import TextProcessor


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


def _html_table(content: str) -> tuple[list[str], list[dict[str, str]]] | None:
    grid = parse_html_table(content)
    if len(grid) < 2:
        return None
    columns = [value or f"column_{index + 1}" for index, value in enumerate(grid[0])]
    rows = [
        dict(zip(columns, row + [""] * max(0, len(columns) - len(row))))
        for row in grid[1:]
    ]
    return columns, rows


class MineruProcessor:
    """Run local MinerU Basic and map its structured JSON into parser output."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def process(self, source: bytes | str | Path, file_path: str | None, document: dict[str, Any]) -> dict[str, Any]:
        cli = os.getenv("MINERU_LOCAL_CLI", "mineru-kit")
        executable = shutil.which(cli) if not Path(cli).is_absolute() else cli
        if not executable or not Path(executable).is_file():
            raise RuntimeError(
                "Local MinerU is unavailable; install MinerU in an isolated environment "
                "and set MINERU_LOCAL_CLI to its mineru-kit executable"
            )

        pdf_bytes = source if isinstance(source, bytes) else Path(source).read_bytes()
        with tempfile.TemporaryDirectory(prefix="upload-test-mineru-") as temporary_dir:
            work_dir = Path(temporary_dir)
            input_pdf = work_dir / "input.pdf"
            output_dir = work_dir / "output"
            input_pdf.write_bytes(pdf_bytes)
            command = [
                executable, "parse", str(input_pdf), "--output", str(output_dir),
                "--pages", self.config.get("mineru_page_range") or "all",
                "--tier", "basic", "--format", "middle_json",
                "--ocr-mode", "ocr" if self.config.get("mineru_force_ocr") else "auto",
                "--disable-image-analysis",
            ]
            environment = os.environ.copy()
            environment["MINERU_MODEL_SOURCE"] = "local"
            mineru_home = os.getenv("MINERU_LOCAL_HOME")
            if mineru_home:
                environment["HOME"] = mineru_home
            try:
                completed = subprocess.run(
                    command, capture_output=True, text=True, timeout=1200,
                    check=False, env=environment,
                )
            except subprocess.TimeoutExpired as error:
                raise RuntimeError("Local MinerU timed out after 20 minutes") from error
            except OSError as error:
                raise RuntimeError(f"Could not start local MinerU: {type(error).__name__}") from error

            if completed.returncode:
                detail = (completed.stderr or completed.stdout or "").strip()[-1200:]
                raise RuntimeError(f"Local MinerU failed (exit {completed.returncode}): {detail}")
            outputs = list(output_dir.rglob("*.json")) if output_dir.exists() else []
            if len(outputs) != 1:
                raise RuntimeError(f"Local MinerU produced {len(outputs)} parsed JSON files; expected one")
            try:
                payload = json.loads(outputs[0].read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError("Local MinerU produced invalid Middle JSON") from error

        version = (payload.get("metadata") or {}).get("producer", {}).get("version")
        return self._to_parser_result(payload, source, document, version)

    @staticmethod
    def _block_text(value: Any) -> str:
        """Flatten MinerU Middle content nodes while preserving table markup."""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(text for item in value if (text := MineruProcessor._block_text(item)))
        if isinstance(value, dict):
            return MineruProcessor._block_text(value.get("content", ""))
        return ""

    @staticmethod
    def _selected_pages(page_count: int, page_range: str) -> list[int] | None:
        if not page_range:
            return None
        selected: list[int] = []
        for part in page_range.split(","):
            bounds = [int(value) for value in part.split("-")]
            selected.extend(range(bounds[0], bounds[-1] + 1))
        if any(page < 1 or page > page_count for page in selected):
            raise RuntimeError("MinerU page range is outside the uploaded PDF")
        return selected

    def _to_parser_result(self, payload: dict[str, Any], source: bytes | str | Path,
                          document: dict[str, Any], version: str | None) -> dict[str, Any]:
        pdf = fitz.open(stream=source, filetype="pdf") if isinstance(source, bytes) else fitz.open(source)
        tables: list[dict[str, Any]] = []
        chunks: list[dict[str, Any]] = []
        current_section_title = None
        current_heading_level = None
        text_processor = TextProcessor(self.config)
        page_count = len(pdf)
        selected_pages = self._selected_pages(page_count, self.config.get("mineru_page_range", ""))
        try:
            for page_data in payload.get("pages", []):
                page_idx = int(page_data.get("page_idx", 0))
                page_number = selected_pages[page_idx] if selected_pages and page_idx < len(selected_pages) else page_idx + 1
                if not 1 <= page_number <= page_count:
                    continue
                page_rect = pdf[page_number - 1].rect
                for block in page_data.get("blocks", []):
                    kind = str(block.get("type", "text")).lower()
                    text = " ".join(self._block_text(block.get("content")).split())
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
                        (name for name, pattern in HEADING_PATTERNS.items() if pattern.match(text)),
                        None,
                    )
                    if heading_kind:
                        element_type = "title"
                    if element_type == "title":
                        current_section_title = text
                        current_heading_level = heading_level(text) or 1
                    for chunk in text_processor.process({"text": text, "metadata": {}}):
                        chunk["metadata"].update({
                            "page_number": page_number,
                            "element_type": element_type,
                            "layout_type": element_type,
                            **section_metadata(current_section_title, current_heading_level),
                            "bbox": point_bbox,
                            "bbox_coordinate_system": "pdf_point",
                            "text_extraction_method": "mineru.local.basic",
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
                "layout_parser": "mineru.local",
                "mineru_version": version,
                "mineru_runtime": "local",
            },
        }
