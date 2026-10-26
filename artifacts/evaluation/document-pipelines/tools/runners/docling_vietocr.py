"""Experimental Docling OCR model using RapidOCR detection and VietOCR recognition."""

from __future__ import annotations

from collections.abc import Iterable
import re
import subprocess
import tempfile
from pathlib import Path
from typing import ClassVar, Type

import cv2
import numpy as np
from PIL import Image
from pydantic import Field

from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import Page
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import OcrOptions
from docling_core.types.doc import BoundingBox, CoordOrigin
from docling_core.types.doc.page import TextCell
from docling.models.base_ocr_model import BaseOcrModel
from docling.models.factories import get_ocr_factory
from docling.models.stages.ocr.tesseract_utils import (
    parse_tesseract_orientation,
    tesseract_box_to_bounding_rectangle,
)
from docling.utils.profiling import TimeRecorder
from line_detection import create_line_detector, crop_line, detect_line_boxes


class VietOcrOptions(OcrOptions):
    kind: ClassVar[str] = "vietocr"
    lang: list[str] = Field(default_factory=list)


class VietOcrModel(BaseOcrModel):
    """Keep Docling's page regions and geometry while replacing text recognition."""

    def __init__(
        self,
        *,
        enabled: bool,
        artifacts_path: Path | None,
        options: VietOcrOptions,
        accelerator_options: AcceleratorOptions,
    ):
        super().__init__(
            enabled=enabled,
            artifacts_path=artifacts_path,
            options=options,
            accelerator_options=accelerator_options,
        )
        self.scale = options.scale
        import torch
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor

        config = Cfg.load_config_from_name("vgg_seq2seq")
        config["device"] = "cuda:0" if torch.cuda.is_available() else "cpu"
        config["dataset"]["image_max_width"] = 512
        config["predictor"]["beamsearch"] = False
        self.recognizer = Predictor(config)
        self.detector = create_line_detector()
        self.orientation_diagnostics: list[dict] = []
        self._orientation_counts: dict[str | None, int] = {}
        self.current_reference_id: str | None = None

    @staticmethod
    def _detect_orientation(image: Image.Image) -> tuple[int, int | None, float | None]:
        """Return correction angle and OSD evidence; uncertain crops stay unrotated."""
        with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
            image.save(image_file.name)
            try:
                output = subprocess.run(
                    ["tesseract", image_file.name, "stdout", "--psm", "0", "-l", "osd"],
                    capture_output=True,
                    check=True,
                    text=True,
                ).stdout
            except (OSError, subprocess.CalledProcessError):
                return 0, None, None
        orientation = re.search(r"Orientation in degrees:\s*(\d+)", output)
        confidence = re.search(r"Orientation confidence:\s*([\d.]+)", output)
        orientation_degrees = int(orientation.group(1)) if orientation else None
        correction = parse_tesseract_orientation(orientation.group(1)) if orientation else 0
        confidence_value = float(confidence.group(1)) if confidence else None
        return correction, orientation_degrees, confidence_value

    @classmethod
    def get_options_type(cls) -> Type[OcrOptions]:
        return VietOcrOptions

    def __call__(
        self, conv_res: ConversionResult, page_batch: Iterable[Page]
    ) -> Iterable[Page]:
        if not self.enabled:
            yield from page_batch
            return

        for page in page_batch:
            if page._backend is None or not page._backend.is_valid():
                yield page
                continue

            with TimeRecorder(conv_res, "ocr"):
                ocr_rects = self.get_ocr_rects(page)
                cells: list[TextCell] = []
                for ocr_rect in ocr_rects:
                    if ocr_rect.area() == 0:
                        continue
                    crop = page._backend.get_page_image(
                        scale=self.scale, cropbox=ocr_rect
                    )
                    doc_orientation, osd_orientation, osd_confidence = self._detect_orientation(crop)
                    region_index = self._orientation_counts.get(self.current_reference_id, 0) + 1
                    self._orientation_counts[self.current_reference_id] = region_index
                    self.orientation_diagnostics.append({
                        "reference_id": self.current_reference_id,
                        "ocr_region_index_1based": region_index,
                        "bbox": [ocr_rect.l, ocr_rect.t, ocr_rect.r, ocr_rect.b],
                        "crop_size": list(crop.size),
                        "osd_orientation_degrees": osd_orientation,
                        "correction_clockwise": doc_orientation,
                        "osd_confidence": osd_confidence,
                    })
                    if doc_orientation:
                        crop = crop.rotate(-doc_orientation, expand=True)
                    image_size = crop.size
                    image = cv2.cvtColor(np.asarray(crop), cv2.COLOR_RGB2BGR)
                    boxes = detect_line_boxes(self.detector, image)
                    if boxes is None:
                        continue

                    for index, quad in enumerate(boxes):
                        quad = np.asarray(quad, dtype=np.float32)
                        line = crop_line(image, quad)
                        text = str(
                            self.recognizer.predict(
                                Image.fromarray(cv2.cvtColor(line, cv2.COLOR_BGR2RGB))
                            )
                            or ""
                        ).strip()
                        if not text:
                            continue
                        left, top = quad.min(axis=0)
                        right, bottom = quad.max(axis=0)
                        box = BoundingBox(
                            l=float(left), t=float(top), r=float(right), b=float(bottom),
                            coord_origin=CoordOrigin.TOPLEFT,
                        )
                        cells.append(
                            TextCell(
                                index=index,
                                text=text,
                                orig=text,
                                confidence=1.0,
                                from_ocr=True,
                                rect=tesseract_box_to_bounding_rectangle(
                                    box,
                                    original_offset=ocr_rect,
                                    scale=self.scale,
                                    orientation=doc_orientation,
                                    im_size=image_size,
                                ),
                            )
                        )
                self.post_process_cells(cells, page, conv_res)
            yield page


def register_vietocr() -> None:
    for allow_external_plugins in (False, True):
        factory = get_ocr_factory(allow_external_plugins=allow_external_plugins)
        if VietOcrOptions not in factory.classes:
            factory.register(VietOcrModel, "document-pipeline-experiment", __name__)
