"""Docling conversion entry point for supported document formats."""

from __future__ import annotations

import os
import tempfile
from io import BytesIO
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .digital_born.pdf import has_embedded_raster_images, has_native_text_on_every_page
from .result_mapper import map_result
from .scanned.embedded_images import process_embedded_images

_OFFICE_FORMATS = {
    "docx", "docm", "dotx", "dotm",
    "xlsx", "xlsm", "xltx", "xltm",
    "pptx", "pptm", "potx", "potm", "ppsx", "ppsm",
}


class DoclingProcessor:
    """Route native document conversion and scanned embedded images."""

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
                OcrAutoOptions,
                PdfPipelineOptions,
                TableFormerMode,
                TableStructureOptions,
                TesseractCliOcrOptions,
            )
            from docling.datamodel.stage_model_specs import ObjectDetectionModelSpec
            from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption
            from docling.datamodel.document import PictureItem, TableItem
        except ImportError as error:
            raise RuntimeError("Docling is unavailable; install it with `uv sync --extra docling`") from error

        device = AcceleratorDevice.CUDA if self.config.get("docling_device") == "cuda" else AcceleratorDevice.CPU
        source_format = str(document.get("metadata", {}).get("format", "PDF")).lower()
        input_path = Path(file_path) if file_path else None
        if input_path is not None and input_path.is_file():
            payload = None
            pdf_source: bytes | Path = input_path
        else:
            payload = source if isinstance(source, bytes) else Path(source).read_bytes()
            pdf_source = payload

        requested_ocr = bool(self.config.get("docling_ocr", True))
        pdf_is_digital_born = (
            source_format == "pdf" and has_native_text_on_every_page(pdf_source)
        )
        scan_pdf_embedded_images = (
            requested_ocr
            and pdf_is_digital_born
            and has_embedded_raster_images(pdf_source)
        )
        scan_embedded_images = requested_ocr and (
            source_format in _OFFICE_FORMATS or scan_pdf_embedded_images
        )
        do_ocr = requested_ocr and not pdf_is_digital_born
        ocr_engine = str(
            self.config.get(
                "docling_ocr_engine",
                os.environ.get("DOCUMENT_PROCESSING_OCR_ENGINE", "tesseract"),
            )
        ).lower()
        processor_config = {
            **self.config,
            "docling_ocr": do_ocr,
            "docling_ocr_engine": ocr_engine,
        }
        if not do_ocr and not scan_embedded_images:
            ocr_options = OcrAutoOptions()
        elif ocr_engine == "vietocr":
            try:
                from .scanned.vietocr import VietOcrOptions, register_vietocr
            except ImportError as error:
                raise RuntimeError(
                    "VietOCR is unavailable. Install its OCR plugin and dependencies, or select Tesseract."
                ) from error
            register_vietocr()
            ocr_options = VietOcrOptions()
        elif ocr_engine == "tesseract":
            ocr_options = TesseractCliOcrOptions(
                lang=str(self.config.get("docling_ocr_language", self.config.get("ocr_language", "vie"))).split("+"),
                psm=6,
            )
        else:
            raise ValueError(f"Unsupported Docling OCR engine: {ocr_engine}")
        options = PdfPipelineOptions(
            accelerator_options=AcceleratorOptions(
                device=device,
                num_threads=int(self.config.get("docling_num_threads", 2)),
            ),
            do_ocr=do_ocr,
            do_table_structure=bool(self.config.get("docling_table_structure", True)),
            generate_page_images=(
                bool(self.config.get("docling_page_images", False))
                or scan_pdf_embedded_images
            ),
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
            ocr_options=ocr_options,
        )
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
            }
        )

        source_suffix = f".{source_format}" if source_format else ".pdf"
        source_bytes: bytes | None = None
        try:
            if input_path is not None and input_path.is_file():
                result = converter.convert(input_path)
                if source_format == "docx":
                    source_bytes = input_path.read_bytes()
            else:
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

        embedded_image_results = process_embedded_images(
            result=result,
            source_format=source_format,
            formats_to_scan=_OFFICE_FORMATS | ({"pdf"} if scan_pdf_embedded_images else set()),
            picture_item_type=PictureItem,
            pipeline_options=options,
            input_format=InputFormat,
            pdf_format_option=PdfFormatOption,
            document_converter=DocumentConverter,
            processor_config=processor_config,
            table_item_type=TableItem,
            ocr_enabled=scan_embedded_images,
            docling_version=docling_version,
        )

        mapped = map_result(
            result,
            processor_config,
            TableItem,
            do_ocr,
            docling_version,
            source_format,
            source_bytes,
            embedded_image_results,
        )
        if source_format == "pdf":
            mapped["metadata"].update({
                "pdf_processing_route": "digital_born" if pdf_is_digital_born else "scanned",
                "ocr_enabled": do_ocr,
                "embedded_image_ocr_enabled": scan_pdf_embedded_images,
            })
        elif source_format in _OFFICE_FORMATS:
            mapped["metadata"]["embedded_image_ocr_enabled"] = scan_embedded_images
        if self.config.get("docling_page_images", False):
            page_previews = {}
            page_sizes = {}
            for page_number, page in result.document.pages.items():
                image = getattr(page, "image", None)
                pil_image = getattr(image, "pil_image", None)
                if pil_image is not None:
                    buffer = BytesIO()
                    pil_image.save(buffer, format="PNG")
                    page_previews[str(page_number)] = buffer.getvalue()
                size = getattr(page, "size", None)
                if size is not None:
                    page_sizes[str(page_number)] = {
                        "width": float(size.width),
                        "height": float(size.height),
                    }
            mapped["page_previews"] = page_previews
            mapped["page_sizes"] = page_sizes
        return mapped
