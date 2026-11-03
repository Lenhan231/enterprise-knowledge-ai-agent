"""Experimental Docling OCR model using RapidOCR detection and VietOCR recognition."""

from __future__ import annotations

from collections.abc import Iterable
import logging
import re
import unicodedata
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
from docling.models.stages.ocr.tesseract_utils import tesseract_box_to_bounding_rectangle
from docling.utils.profiling import TimeRecorder
from .line_detection import create_line_detector, crop_line, detect_line_boxes
from ..orientation import detect_paddle_orientation, rotate_for_reading

_TEXT_TYPE_REPO = "VItaldob/text-type-classifier-resnet18"
_TEXT_TYPE_REVISION = "5709c2519a11bcea9974975f988b69fa3a835139"
_HANDWRITING_REPO = "DungHugging/vietocr-handwritten-finetune"
_HANDWRITING_REVISION = "0827b42e17cb0e1c1bbda5aac11f7cc5c816e0ca"
_LOGGER = logging.getLogger(__name__)


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
        import yaml
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor

        config_dir = Path(__file__).with_name("vietocr_config")
        config = Cfg.load_config_from_file(config_dir / "base.yml")
        with (config_dir / "vgg-seq2seq.yml").open(encoding="utf-8") as config_file:
            config.update(yaml.safe_load(config_file))
        config["device"] = "cuda:0" if torch.cuda.is_available() else "cpu"
        config["cnn"]["pretrained"] = False
        config["dataset"]["image_max_width"] = 512
        config["predictor"]["beamsearch"] = False
        self.recognizer = Predictor(config)
        self._torch = torch
        self.handwriting_classifier = None
        self.handwriting_recognizer = None
        self.classifier_transform = None
        try:
            self._load_handwriting_router(torch, Predictor, Cfg, config["device"])
        except Exception:
            _LOGGER.exception(
                "Could not load handwriting routing models; using the default VietOCR recognizer"
            )
        self.detector = create_line_detector()
        self.orientation_diagnostics: list[dict] = []
        self._orientation_counts: dict[str | None, int] = {}
        self.current_reference_id: str | None = None

    def _load_handwriting_router(self, torch, predictor_type, config_type, device: str) -> None:
        from huggingface_hub import hf_hub_download
        from torchvision import models, transforms

        classifier_path = hf_hub_download(
            _TEXT_TYPE_REPO,
            "resnet18_text_classifier_final.pth",
            revision=_TEXT_TYPE_REVISION,
        )
        handwriting_path = hf_hub_download(
            _HANDWRITING_REPO,
            "transformerocr.pth",
            revision=_HANDWRITING_REVISION,
        )

        classifier = models.resnet18(weights=None)
        classifier.fc = torch.nn.Linear(classifier.fc.in_features, 2)
        classifier.load_state_dict(
            torch.load(classifier_path, map_location="cpu", weights_only=True)
        )
        classifier.to(device).eval()
        self.handwriting_classifier = classifier
        self.classifier_transform = transforms.Compose([
            transforms.Resize((128, 512)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

        handwriting_config = config_type.load_config_from_name("vgg_transformer")
        handwriting_config["weights"] = handwriting_path
        handwriting_config["device"] = device
        handwriting_config["cnn"]["pretrained"] = False
        handwriting_config["dataset"]["image_max_width"] = 512
        handwriting_config["predictor"]["beamsearch"] = False
        self.handwriting_recognizer = predictor_type(handwriting_config)

    def _recognize_line(self, line: np.ndarray) -> tuple[str, str]:
        image = Image.fromarray(cv2.cvtColor(line, cv2.COLOR_BGR2RGB))
        if self.handwriting_classifier is None or self.handwriting_recognizer is None:
            return str(self.recognizer.predict(image) or "").strip(), "default"

        try:
            tensor = self.classifier_transform(image).unsqueeze(0).to(
                next(self.handwriting_classifier.parameters()).device
            )
            with self._torch.inference_mode():
                prediction = int(self.handwriting_classifier(tensor).argmax(dim=1).item())
            if prediction == 0:
                recognizer, route = self.handwriting_recognizer, "handwritten"
            else:
                recognizer, route = self.recognizer, "printed"
            return str(recognizer.predict(image) or "").strip(), route
        except Exception:
            _LOGGER.exception("Handwriting routing failed; falling back to default VietOCR")
            return str(self.recognizer.predict(image) or "").strip(), "fallback"

    @staticmethod
    def _detect_orientation(image: Image.Image) -> tuple[int, int | None, float | None]:
        """Classify region orientation before RapidOCR line detection."""
        return detect_paddle_orientation(image)

    @staticmethod
    def _cell_bbox(cell: TextCell) -> tuple[float, float, float, float]:
        rect = cell.rect
        xs = (rect.r_x0, rect.r_x1, rect.r_x2, rect.r_x3)
        ys = (rect.r_y0, rect.r_y1, rect.r_y2, rect.r_y3)
        return min(xs), min(ys), max(xs), max(ys)

    @classmethod
    def _deduplicate_overlapping_cells(
        cls,
        cells: list[TextCell],
        region_indices: list[int],
        iou_threshold: float = 0.6,
    ) -> list[TextCell]:
        """Drop exact repeated OCR lines from overlapping Docling text regions."""
        kept: list[TextCell] = []
        kept_regions: list[int] = []
        for cell, region_index in zip(cells, region_indices):
            text = re.sub(r"\s+", " ", unicodedata.normalize("NFC", cell.text).casefold()).strip()
            box = cls._cell_bbox(cell)
            duplicate = False
            for previous, previous_region in zip(kept, kept_regions):
                if region_index == previous_region or text != re.sub(
                    r"\s+", " ", unicodedata.normalize("NFC", previous.text).casefold()
                ).strip():
                    continue
                previous_box = cls._cell_bbox(previous)
                left, top = max(box[0], previous_box[0]), max(box[1], previous_box[1])
                right, bottom = min(box[2], previous_box[2]), min(box[3], previous_box[3])
                intersection = max(0.0, right - left) * max(0.0, bottom - top)
                area = lambda value: max(0.0, value[2] - value[0]) * max(0.0, value[3] - value[1])
                union = area(box) + area(previous_box) - intersection
                if union and intersection / union >= iou_threshold:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(cell)
                kept_regions.append(region_index)
        return kept

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
                layout = page.predictions.layout
                ocr_rects = (
                    [cluster.bbox for cluster in layout.clusters]
                    if layout is not None and layout.clusters
                    else self.get_ocr_rects(page)
                )
                print(
                    "OCR regions before line detection:",
                    self.current_reference_id,
                    [
                        [round(rect.l, 1), round(rect.t, 1), round(rect.r, 1), round(rect.b, 1)]
                        for rect in ocr_rects
                    ],
                    flush=True,
                )
                cells: list[TextCell] = []
                cell_region_indices: list[int] = []
                routing_counts = {"printed": 0, "handwritten": 0, "fallback": 0, "default": 0}
                for ocr_rect in ocr_rects:
                    if ocr_rect.area() == 0:
                        continue
                    crop = page._backend.get_page_image(
                        scale=self.scale, cropbox=ocr_rect
                    )
                    doc_orientation, osd_orientation, osd_confidence = self._detect_orientation(crop)
                    # Quarter-turn predictions on horizontal crops can be wrong even at high confidence.
                    if osd_confidence < 0.7 or (doc_orientation in (90, 270) and crop.width >= crop.height):
                        doc_orientation = 0
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
                        crop = rotate_for_reading(crop, doc_orientation)
                    image_size = crop.size
                    image = cv2.cvtColor(np.asarray(crop), cv2.COLOR_RGB2BGR)
                    detection_image = image
                    boxes = detect_line_boxes(self.detector, detection_image)
                    vertical_padding = 0
                    if boxes is None or len(boxes) == 0:
                        vertical_padding = max(10, int(round(image.shape[0] * 0.4)))
                        detection_image = cv2.copyMakeBorder(
                            image,
                            vertical_padding,
                            vertical_padding,
                            0,
                            0,
                            cv2.BORDER_CONSTANT,
                            value=(255, 255, 255),
                        )
                        boxes = detect_line_boxes(self.detector, detection_image)
                    if boxes is None or len(boxes) == 0:
                        continue

                    for index, quad in enumerate(boxes):
                        quad = np.asarray(quad, dtype=np.float32)
                        line = crop_line(detection_image, quad)
                        text, route = self._recognize_line(line)
                        routing_counts[route] += 1
                        if not text:
                            continue
                        page_quad = quad.copy()
                        page_quad[:, 1] -= vertical_padding
                        page_quad[:, 0] = np.clip(page_quad[:, 0], 0, image_size[0] - 1)
                        page_quad[:, 1] = np.clip(page_quad[:, 1], 0, image_size[1] - 1)
                        left, top = page_quad.min(axis=0)
                        right, bottom = page_quad.max(axis=0)
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
                        cell_region_indices.append(region_index)
                if self.handwriting_classifier is not None:
                    print(
                        "OCR line routing:", self.current_reference_id, routing_counts,
                        flush=True,
                    )
                cells = self._deduplicate_overlapping_cells(cells, cell_region_indices)
                self.post_process_cells(cells, page, conv_res)
            yield page


def register_vietocr() -> None:
    for allow_external_plugins in (False, True):
        factory = get_ocr_factory(allow_external_plugins=allow_external_plugins)
        if VietOcrOptions not in factory.classes:
            factory.register(VietOcrModel, "document-pipeline-experiment", __name__)
