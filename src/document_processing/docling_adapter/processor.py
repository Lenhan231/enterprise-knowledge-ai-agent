"""Docling conversion entry point for supported document formats."""

from __future__ import annotations

import os
import tempfile
from io import BytesIO
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .chart_recognition import recognize_chart_regions
from .converters import get_converter
from .result_mapper import associate_chart_title_regions, map_result
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

    def preload(self) -> None:
        """Initialize the scanned, native, and embedded-image routes before startup."""
        from docling.datamodel.base_models import InputFormat

        for do_ocr, embedded, page_images in (
            (True, False, False), (False, False, False), (False, True, True),
        ):
            converter = get_converter(self._pipeline_options(do_ocr, embedded, page_images))
            converter.initialize_pipeline(InputFormat.PDF)

    def process(
        self, source: bytes | str | Path, file_path: str | None, document: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption
            from docling.datamodel.document import PictureItem, TableItem
            from .layout_model import PPDocLayoutModel
        except ImportError as error:
            raise RuntimeError(
                "Docling is unavailable; install it with `uv sync --extra docling`."
            ) from error

        source_format = str(document.get("metadata", {}).get("format", "PDF")).lower()
        input_path = Path(file_path) if file_path else None
        if input_path is not None and input_path.is_file():
            payload = None
        else:
            payload = source if isinstance(source, bytes) else Path(source).read_bytes()

        requested_ocr = bool(self.config.get("docling_ocr", True))
        # PDFs always use OCR and discard backend text cells. The UI toggle controls
        # OCR for Office embedded pictures and standalone images only.
        do_ocr = source_format == "pdf" or requested_ocr
        scan_embedded_images = requested_ocr and source_format in _OFFICE_FORMATS
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
            "docling_layout_model": "PaddleOCR PP-DocLayoutV3",
            "docling_layout_score_threshold": float(
                self.config.get("docling_layout_score_threshold", 0.25)
            ),
        }
        options = self._pipeline_options(
            do_ocr,
            scan_embedded_images,
            bool(self.config.get("docling_page_images", False)),
            source_format=source_format,
        )
        converter = get_converter(options)

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

        chart_regions = [
            region
            for pipeline in converter.initialized_pipelines.values()
            for region in getattr(getattr(pipeline, "layout_model", None), "chart_regions", [])
            if isinstance(getattr(pipeline, "layout_model", None), PPDocLayoutModel)
        ]
        layout_detections = [
            detection
            for pipeline in converter.initialized_pipelines.values()
            for detection in getattr(getattr(pipeline, "layout_model", None), "layout_detections", [])
            if isinstance(getattr(pipeline, "layout_model", None), PPDocLayoutModel)
        ]
        page_orientation_corrections = {
            page_number: correction
            for pipeline in converter.initialized_pipelines.values()
            for page_number, correction in getattr(
                getattr(pipeline, "layout_model", None),
                "page_orientation_corrections",
                {},
            ).items()
        }
        page_sizes = {
            int(page_number): (float(page.size.width), float(page.size.height))
            for page_number, page in result.document.pages.items()
        }
        associate_chart_title_regions(chart_regions, layout_detections, page_sizes)
        embedded_image_results = process_embedded_images(
            result=result,
            source_format=source_format,
            formats_to_scan=_OFFICE_FORMATS,
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
        chart_recognition_results = recognize_chart_regions(
            result.document,
            processor_config,
            chart_regions,
            page_source=(input_path if input_path is not None and input_path.is_file() else payload),
            source_format=source_format,
            page_orientation_corrections=page_orientation_corrections,
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
            chart_regions=chart_regions,
            chart_recognition_results=chart_recognition_results,
            layout_detections=layout_detections,
        )
        mapped["page_sizes"] = {
            str(page_number): {"width": width, "height": height}
            for page_number, (width, height) in page_sizes.items()
        }
        if source_format == "pdf":
            mapped["metadata"].update({
                "pdf_processing_route": "full_page_ocr",
                "ocr_enabled": do_ocr,
                "embedded_image_ocr_enabled": False,
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

    def _pipeline_options(
        self,
        do_ocr: bool,
        scan_embedded_images: bool,
        generate_page_images: bool,
        *,
        source_format: str = "pdf",
    ) -> Any:
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.pipeline_options import (
            OcrAutoOptions,
            OcrMode,
            PdfPipelineOptions,
            TableFormerMode,
            TableStructureOptions,
            TesseractCliOcrOptions,
        )
        from .layout_model import PPDocLayoutOptions, register_pp_doclayout

        device = AcceleratorDevice.CUDA if self.config.get("docling_device") == "cuda" else AcceleratorDevice.CPU
        ocr_engine = str(
            self.config.get(
                "docling_ocr_engine",
                os.environ.get("DOCUMENT_PROCESSING_OCR_ENGINE", "tesseract"),
            )
        ).lower()
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
            ocr_options = VietOcrOptions(
                mode=OcrMode.FULL_PAGE if source_format == "pdf" and do_ocr else OcrMode.DEFAULT
            )
        elif ocr_engine == "tesseract":
            ocr_options = TesseractCliOcrOptions(
                lang=str(self.config.get("docling_ocr_language", self.config.get("ocr_language", "vie"))).split("+"),
                psm=6,
                mode=OcrMode.FULL_PAGE if source_format == "pdf" and do_ocr else OcrMode.DEFAULT,
            )
        else:
            raise ValueError(f"Unsupported Docling OCR engine: {ocr_engine}")

        register_pp_doclayout()
        return PdfPipelineOptions(
            accelerator_options=AcceleratorOptions(
                device=device,
                num_threads=int(self.config.get("docling_num_threads", 2)),
            ),
            do_ocr=do_ocr,
            do_table_structure=bool(self.config.get("docling_table_structure", True)),
            generate_page_images=generate_page_images,
            images_scale=1.0,
            layout_options=PPDocLayoutOptions(
                score_threshold=float(self.config.get("docling_layout_score_threshold", 0.25))
            ),
            table_structure_options=TableStructureOptions(
                mode=TableFormerMode.ACCURATE,
                do_cell_matching=True,
            ),
            ocr_options=ocr_options,
        )
