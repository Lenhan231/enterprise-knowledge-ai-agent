"""Docling conversion entry point for supported document formats."""

from __future__ import annotations

import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .result_mapper import map_result


class DoclingProcessor:
    """Convert a source document, then delegate output normalization."""

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

        source_format = str(document.get("metadata", {}).get("format", "PDF")).lower()
        source_suffix = f".{source_format}" if source_format else ".pdf"
        input_path = Path(file_path) if file_path else None
        try:
            if input_path is not None and input_path.is_file():
                result = converter.convert(input_path)
            else:
                payload = source if isinstance(source, bytes) else Path(source).read_bytes()
                with tempfile.NamedTemporaryFile(suffix=source_suffix) as temporary:
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

        return map_result(
            result,
            self.config,
            TableItem,
            do_ocr,
            docling_version,
            source_format,
        )
