"""Docling adapter that maps layout-aware PDF output to shared parser chunks."""

from __future__ import annotations

import math
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any


class DoclingProcessor:
    """Convert a PDF with Docling and retain page/layout/table provenance."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def process(
        self, source: bytes | str | Path, file_path: str | None, document: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.document import TableItem
        except ImportError as error:
            raise RuntimeError("Docling is unavailable; install it with `uv sync --extra docling`") from error

        device = AcceleratorDevice.CUDA if self.config.get("docling_device") == "cuda" else AcceleratorDevice.CPU
        do_ocr = bool(self.config.get("docling_ocr", True))
        options = PdfPipelineOptions(
            accelerator_options=AcceleratorOptions(
                device=device,
                num_threads=int(self.config.get("docling_num_threads", 4)),
            ),
            do_ocr=do_ocr,
            do_table_structure=bool(self.config.get("docling_table_structure", True)),
            ocr_options=(
                RapidOcrOptions(
                    lang=[self.config.get("docling_ocr_language", "vi")],
                    backend="onnxruntime",
                )
                if do_ocr else None
            ),
        )
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )

        pdf_path = Path(file_path) if file_path else None
        try:
            if pdf_path is not None and pdf_path.is_file():
                result = converter.convert(pdf_path)
            else:
                payload = source if isinstance(source, bytes) else Path(source).read_bytes()
                with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
                    temporary.write(payload)
                    temporary.flush()
                    result = converter.convert(temporary.name)
        except Exception as error:
            raise RuntimeError(f"Docling conversion failed: {type(error).__name__}: {error}") from error

        if "FAILURE" in str(result.status).upper():
            raise RuntimeError(f"Docling conversion failed: {result.status}")

        try:
            docling_version = version("docling")
        except PackageNotFoundError:
            docling_version = None

        chunks: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        section_path: list[str] = []
        table_number_by_page: dict[int, int] = {}

        for item, _level in result.document.iterate_items():
            label = getattr(item.label, "value", str(item.label)).lower()
            text = str(getattr(item, "text", "") or "").strip()
            provenance = next(iter(getattr(item, "prov", []) or []), None)
            if provenance is None:
                continue
            page_number = int(provenance.page_no)
            bbox = self._bbox(provenance.bbox)
            base_metadata = {
                "page_number": page_number,
                "bbox": bbox,
                "bbox_coordinate_system": "docling_page_coordinate",
                "parser": "docling",
                "docling_label": label,
                "docling_version": docling_version,
                "text_extraction_method": "docling.rapidocr" if do_ocr else "docling.native",
            }

            if isinstance(item, TableItem) and self.config.get("docling_table_structure", True):
                data = item.data
                row_count, column_count = int(data.num_rows), int(data.num_cols)
                grid = [[""] * column_count for _ in range(row_count)]
                header_rows: set[int] = set()
                for cell in data.table_cells:
                    row = int(cell.start_row_offset_idx)
                    column = int(cell.start_col_offset_idx)
                    if 0 <= row < row_count and 0 <= column < column_count:
                        grid[row][column] = self._cell(cell.text)
                        if cell.column_header:
                            header_rows.add(row)
                has_header = bool(header_rows and 0 in header_rows)
                if has_header:
                    columns = [value or f"column_{index + 1}" for index, value in enumerate(grid[0])]
                    value_rows = grid[1:]
                else:
                    columns = [f"column_{index + 1}" for index in range(column_count)]
                    value_rows = grid
                rows = [dict(zip(columns, values)) for values in value_rows]
                if not columns or not rows:
                    continue
                table_index = table_number_by_page.get(page_number, 0)
                table_number_by_page[page_number] = table_index + 1
                tables.append({
                    "page_number": page_number,
                    "table_index": table_index,
                    "columns": columns,
                    "rows": rows,
                    "context": {},
                    "metadata": {
                        **base_metadata,
                        "element_type": "table",
                        "layout_type": "table",
                        "table_structure_model": "Docling TableFormer",
                    },
                })
                table_text = " | ".join(columns) + "\n" + "\n".join(
                    " | ".join(str(row.get(column) or "") for column in columns)
                    for row in rows
                )
                chunks.append({
                    "text": table_text,
                    "metadata": {
                        **base_metadata,
                        "element_type": "table",
                        "layout_type": "table",
                        "table_index": table_index,
                    },
                })
                continue

            if label in {"page_header", "page_footer", "picture", "chart"} or not text:
                continue
            if label in {"title", "section_header"}:
                section_path = [text] if label == "title" else (section_path[:1] + [text])
            element_type = {
                "title": "title",
                "section_header": "title",
                "list_item": "list_item",
                "formula": "formula",
                "caption": "figure_caption",
                "footnote": "footnote",
            }.get(label, "paragraph")
            chunks.append({
                "text": text,
                "metadata": {
                    **base_metadata,
                    "element_type": element_type,
                    "layout_type": label,
                    "section_path": list(section_path),
                    "section_title": section_path[-1] if section_path else None,
                    "heading_level": min(len(section_path), 2) or None,
                },
            })

        return {
            "chunks": chunks,
            "tables": tables,
            "metadata": {"docling_version": docling_version},
        }

    @staticmethod
    def _bbox(box: Any) -> list[float] | None:
        if box is None:
            return None
        left, top, right, bottom = (float(box.l), float(box.t), float(box.r), float(box.b))
        if str(getattr(box, "coord_origin", "")).upper().endswith("BOTTOMLEFT"):
            return [left, bottom, right, top]
        return [left, top, right, bottom]

    @staticmethod
    def _cell(value: Any) -> str:
        if value is None:
            return ""
        try:
            if math.isnan(float(value)):
                return ""
        except (TypeError, ValueError):
            pass
        return str(value).strip()
