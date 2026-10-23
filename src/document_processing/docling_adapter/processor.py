"""Docling conversion entry point for supported document formats."""

from __future__ import annotations

import tempfile
from io import BytesIO
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
            from docling.datamodel.pipeline_options import (
                LayoutObjectDetectionOptions,
                PdfPipelineOptions,
                TableFormerMode,
                TableStructureOptions,
                TesseractCliOcrOptions,
            )
            from docling.datamodel.stage_model_specs import ObjectDetectionModelSpec
            from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption
            from docling.datamodel.document import TableItem
        except ImportError as error:
            raise RuntimeError("Docling is unavailable; install it with `uv sync --extra docling`") from error

        device = AcceleratorDevice.CUDA if self.config.get("docling_device") == "cuda" else AcceleratorDevice.CPU
        do_ocr = bool(self.config.get("docling_ocr", True))
        options = PdfPipelineOptions(
            accelerator_options=AcceleratorOptions(
                device=device,
                num_threads=int(self.config.get("docling_num_threads", 2)),
            ),
            do_ocr=do_ocr,
            do_table_structure=bool(self.config.get("docling_table_structure", True)),
            generate_page_images=bool(self.config.get("docling_page_images", False)),
            images_scale=1.0,
            layout_options=LayoutObjectDetectionOptions(
                model_spec=ObjectDetectionModelSpec(
                    name="layout_heron",
                    repo_id="docling-project/docling-layout-heron",
                )
            ),
            table_structure_options=TableStructureOptions(
                mode=TableFormerMode.ACCURATE,
                do_cell_matching=True,
            ),
            ocr_options=(
                TesseractCliOcrOptions(
                    lang=str(self.config.get("docling_ocr_language", self.config.get("ocr_language", "vie"))).split("+"),
                    psm=6,
                )
                if do_ocr else None
            ),
        )
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
            }
        )

        source_format = str(document.get("metadata", {}).get("format", "PDF")).lower()
        source_suffix = f".{source_format}" if source_format else ".pdf"
        input_path = Path(file_path) if file_path else None
        source_bytes: bytes | None = None
        try:
            if input_path is not None and input_path.is_file():
                result = converter.convert(input_path)
                if source_format == "docx":
                    source_bytes = input_path.read_bytes()
            else:
                payload = source if isinstance(source, bytes) else Path(source).read_bytes()
                if source_format == "docx":
                    source_bytes = payload
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

        mapped = map_result(
            result,
            self.config,
            TableItem,
            do_ocr,
            docling_version,
            source_format,
            source_bytes,
        )
        if self.config.get("docling_page_images", False):
            page_previews = {}
            for page_number, page in result.document.pages.items():
                image = getattr(page, "image", None)
                pil_image = getattr(image, "pil_image", None)
                if pil_image is not None:
                    buffer = BytesIO()
                    pil_image.save(buffer, format="PNG")
                    page_previews[str(page_number)] = buffer.getvalue()
            mapped["page_previews"] = page_previews
        return mapped
