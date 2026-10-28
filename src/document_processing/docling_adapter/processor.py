"""Docling conversion entry point for supported document formats."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from io import BytesIO
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .result_mapper import map_result

_log = logging.getLogger(__name__)
_OFFICE_FORMATS = {
    "docx", "docm", "dotx", "dotm",
    "xlsx", "xlsm", "xltx", "xltm",
    "pptx", "pptm", "potx", "potm", "ppsx", "ppsm",
}


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
            from docling.datamodel.document import PictureItem, TableItem
        except ImportError as error:
            raise RuntimeError("Docling is unavailable; install it with `uv sync --extra docling`") from error

        device = AcceleratorDevice.CUDA if self.config.get("docling_device") == "cuda" else AcceleratorDevice.CPU
        do_ocr = bool(self.config.get("docling_ocr", True))
        ocr_engine = str(
            self.config.get(
                "docling_ocr_engine",
                os.environ.get("DOCUMENT_PROCESSING_OCR_ENGINE", "tesseract"),
            )
        ).lower()
        processor_config = {**self.config, "docling_ocr_engine": ocr_engine}
        if not do_ocr:
            ocr_options = None
        elif ocr_engine == "vietocr":
            try:
                from docling_vietocr import VietOcrOptions, register_vietocr
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
            ocr_options=ocr_options,
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

        embedded_image_results: dict[int, dict[str, Any]] = {}
        if do_ocr and source_format in _OFFICE_FORMATS:
            picture_items = []
            unique_images: dict[bytes, Any] = {}
            image_index = 0
            for item, _level in result.document.iterate_items():
                if not isinstance(item, PictureItem):
                    continue
                image = item.get_image(result.document)
                if image is None:
                    continue
                normalized_image = image.convert("RGB")
                image_key = hashlib.sha256(
                    f"{normalized_image.size}".encode() + normalized_image.tobytes()
                ).digest()
                if image_key in unique_images:
                    normalized_image.close()
                else:
                    unique_images[image_key] = normalized_image
                picture_items.append((item, image_index, image_key))
                image_index += 1
            unique_items = list(unique_images.items())
            image_outputs: dict[bytes, dict[str, Any]] = {}
            embedded_options = options.model_copy(update={"generate_page_images": False})
            embedded_converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=embedded_options),
                }
            )
            for batch_start in range(0, len(unique_items), 8):
                batch = unique_items[batch_start:batch_start + 8]
                try:
                    images = [entry[1] for entry in batch]
                    with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
                        images[0].save(
                            temporary,
                            format="PDF",
                            save_all=True,
                            append_images=images[1:],
                            resolution=72,
                        )
                        temporary.flush()
                        image_result = embedded_converter.convert(temporary.name)
                    if "FAILURE" in str(image_result.status).upper():
                        raise RuntimeError(str(image_result.status))
                    image_output = map_result(
                        image_result,
                        processor_config,
                        TableItem,
                        do_ocr,
                        docling_version,
                        "pdf",
                        preserve_chart_items=True,
                    )
                    for page_index, (image_key, _image) in enumerate(batch, 1):
                        image_outputs[image_key] = {
                            "output": {
                                "elements": [
                                    element for element in image_output["elements"]
                                    if (element.get("metadata") or {}).get("page_number") == page_index
                                ],
                                "tables": [
                                    table for table in image_output["tables"]
                                    if table.get("page_number", (table.get("metadata") or {}).get("page_number")) == page_index
                                ],
                            },
                        }
                except Exception as error:
                    _log.warning(
                        "Could not OCR embedded images %s-%s in %s: %s",
                        batch_start,
                        batch_start + len(batch) - 1,
                        source_format,
                        error,
                    )
                finally:
                    for _image_key, image in batch:
                        image.close()
            for item, current_index, image_key in picture_items:
                if image_key in image_outputs:
                    embedded_image_results[id(item)] = {
                        "image_index": current_index,
                        **image_outputs[image_key],
                    }

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
