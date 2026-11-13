"""Docling conversion entry point for supported document formats."""

from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import os
import tempfile
import time
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

logger = logging.getLogger(__name__)


@contextmanager
def _timed_component(component: str, **context: Any):
    started = time.perf_counter()
    try:
        yield
    finally:
        logger.info(
            "DOCUMENT_PROCESS_COMPONENT %s",
            json.dumps(
                {"component": component, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), **context},
                separators=(",", ":"),
            ),
        )


def _summarize_docling_timings(timings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    summary = {}
    for name, item in timings.items():
        durations = [float(value) for value in getattr(item, "times", [])]
        if not durations:
            continue
        scope = getattr(item, "scope", "")
        summary[name] = {
            "scope": str(getattr(scope, "value", scope)),
            "count": int(getattr(item, "count", len(durations))),
            "total_ms": round(sum(durations) * 1000, 2),
            "intervals_ms": [round(value * 1000, 2) for value in durations],
        }
    return summary


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

        from .orientation import preload_paddle_page_orientation_model

        with _timed_component("ocr_orientation_model_preload"):
            preload_paddle_page_orientation_model()

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

        metadata = document.get("metadata", {})
        source_format = str(metadata.get("format", "PDF")).lower()
        invoice_id = metadata.get("invoice_id")
        input_path = Path(file_path) if file_path else None
        with _timed_component("source_read", invoice_id=invoice_id, source_format=source_format):
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
        with _timed_component("converter_setup", invoice_id=invoice_id, source_format=source_format):
            options = self._pipeline_options(
                do_ocr,
                scan_embedded_images,
                bool(self.config.get("docling_page_images", False)),
                source_format=source_format,
            )
            converter = get_converter(options)
            for pipeline in converter.initialized_pipelines.values():
                ocr_model = getattr(pipeline, "ocr_model", None)
                if ocr_model is not None:
                    getattr(ocr_model, "routing_diagnostics", []).clear()
                    getattr(ocr_model, "orientation_diagnostics", []).clear()
                    getattr(ocr_model, "_orientation_counts", {}).clear()
                    ocr_model.current_reference_id = invoice_id
                layout_model = getattr(pipeline, "layout_model", None)
                if layout_model is not None:
                    layout_model.current_reference_id = invoice_id

        source_suffix = f".{source_format}" if source_format else ".pdf"
        source_bytes: bytes | None = None
        try:
            from docling.datamodel.settings import DebugSettings, scoped

            with _timed_component("docling_convert", invoice_id=invoice_id, source_format=source_format):
                with scoped(debug=DebugSettings(profile_pipeline_timings=True)):
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

        profile = _summarize_docling_timings(getattr(result, "timings", {}))
        if profile:
            logger.info(
                "DOCLING_PIPELINE_PROFILE %s",
                json.dumps({"invoice_id": invoice_id, "source_format": source_format, "components": profile}, separators=(",", ":")),
            )

        if "FAILURE" in str(result.status).upper():
            raise RuntimeError(f"Docling conversion failed: {result.status}")
        ocr_routing_diagnostics = [
            diagnostic
            for pipeline in converter.initialized_pipelines.values()
            for diagnostic in getattr(
                getattr(pipeline, "ocr_model", None), "routing_diagnostics", []
            )
        ]
        ocr_orientation_diagnostics = [
            diagnostic
            for pipeline in converter.initialized_pipelines.values()
            for diagnostic in getattr(
                getattr(pipeline, "ocr_model", None), "orientation_diagnostics", []
            )
        ]
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
        with _timed_component("embedded_image_processing", invoice_id=invoice_id, source_format=source_format):
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
        with _timed_component("chart_recognition", invoice_id=invoice_id, source_format=source_format):
            chart_recognition_results = recognize_chart_regions(
                result.document,
                processor_config,
                chart_regions,
                page_source=(input_path if input_path is not None and input_path.is_file() else payload),
                source_format=source_format,
                page_orientation_corrections=page_orientation_corrections,
            )

        with _timed_component("result_mapping", invoice_id=invoice_id, source_format=source_format):
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
        mapped["page_orientation_corrections"] = {
            str(page_number): int(correction)
            for page_number, correction in page_orientation_corrections.items()
        }
        if ocr_routing_diagnostics:
            mapped["metadata"]["ocr_routing_diagnostics"] = ocr_routing_diagnostics
        if ocr_orientation_diagnostics:
            mapped["metadata"]["ocr_orientation_diagnostics"] = ocr_orientation_diagnostics
        if source_format == "pdf":
            mapped["metadata"].update({
                "pdf_processing_route": "layout_region_ocr" if ocr_engine == "vietocr" else "full_page_ocr",
                "ocr_enabled": do_ocr,
                "embedded_image_ocr_enabled": False,
            })
        elif source_format in _OFFICE_FORMATS:
            mapped["metadata"]["embedded_image_ocr_enabled"] = scan_embedded_images
        if self.config.get("docling_page_images", False):
            with _timed_component("page_preview_encoding", invoice_id=invoice_id, source_format=source_format):
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
                num_threads=int(self.config.get(
                    "docling_num_threads", 2 if device == AcceleratorDevice.CPU else 4,
                )),
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
