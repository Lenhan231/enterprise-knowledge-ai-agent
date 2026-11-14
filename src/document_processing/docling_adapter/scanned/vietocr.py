"""Experimental Docling OCR model using RapidOCR detection and VietOCR recognition."""

from __future__ import annotations

from collections.abc import Iterable
import json
import logging
import os
import re
import time
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
from .line_detection import create_line_detector, crop_line, detect_line_boxes, merge_line_fragments
from ..orientation import (
    detect_paddle_orientation,
    detect_paddle_textline_orientations,
    rotate_for_reading,
)

_LOGGER = logging.getLogger(__name__)
_TEXT_LAYOUT_LABELS = {
    "text", "title", "section_header", "caption", "footnote", "list_item",
    "page_header", "page_footer", "code", "key_value_region",
}
_VIETOCR_BATCH_SIZE = 16
_TEXTLINE_ORIENTATION_BATCH_SIZE = 16


def _configure_vietocr_cpu_threads(torch, accelerator_options: AcceleratorOptions) -> int | None:
    """Keep VietOCR's PyTorch CPU pool within the Docling pipeline budget."""
    device = str(getattr(accelerator_options.device, "value", accelerator_options.device)).lower()
    if device != "cpu":
        return None
    thread_count = max(1, int(accelerator_options.num_threads))
    torch.set_num_threads(thread_count)
    return thread_count


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

        cpu_threads = _configure_vietocr_cpu_threads(torch, accelerator_options)
        if cpu_threads is not None:
            _LOGGER.info("Set VietOCR PyTorch CPU threads=%s", cpu_threads)

        fine_tuned_weights = os.environ.get("DOCUMENT_PROCESSING_VIETOCR_WEIGHTS")
        model_repo = os.environ.get("DOCUMENT_PROCESSING_VIETOCR_REPO_ID", "").strip()
        model_filename = os.environ.get(
            "DOCUMENT_PROCESSING_VIETOCR_FILENAME",
            "vietocr/vgg-seq2seq-enterprise-print.pth",
        )
        model_revision = os.environ.get("DOCUMENT_PROCESSING_VIETOCR_REVISION", "main")
        config_name = os.environ.get("DOCUMENT_PROCESSING_VIETOCR_CONFIG", "vgg_seq2seq")
        if fine_tuned_weights:
            weights_path = Path(fine_tuned_weights)
            if not weights_path.is_file():
                raise FileNotFoundError(
                    "Configured fine-tuned VietOCR weights do not exist: "
                    f"{weights_path}"
                )
            config = Cfg.load_config_from_name(config_name)
            config["weights"] = str(weights_path)
        elif model_repo:
            from huggingface_hub import hf_hub_download

            weights_path = hf_hub_download(
                repo_id=model_repo,
                filename=model_filename,
                revision=model_revision,
            )
            config = Cfg.load_config_from_name(config_name)
            config["weights"] = weights_path
        else:
            config_dir = Path(__file__).with_name("vietocr_config")
            config = Cfg.load_config_from_file(config_dir / "base.yml")
            with (config_dir / "vgg-seq2seq.yml").open(encoding="utf-8") as config_file:
                config.update(yaml.safe_load(config_file))
        config["device"] = "cuda:0" if torch.cuda.is_available() else "cpu"
        config["cnn"]["pretrained"] = False
        config["dataset"]["image_max_width"] = 512
        config["predictor"]["beamsearch"] = False
        self.recognizer = Predictor(config)
        _LOGGER.info(
            "Loaded VietOCR config=%s repo=%s revision=%s device=%s",
            config_name,
            model_repo or "local/default",
            model_revision,
            config["device"],
        )
        self.detector = create_line_detector()
        self.orientation_diagnostics: list[dict] = []
        self.routing_diagnostics: list[dict] = []
        self._orientation_counts: dict[int, int] = {}
        self._last_recognition_batches = 0
        self.current_reference_id: str | None = None

    def _recognize_line(self, line: np.ndarray) -> tuple[str, str]:
        image = Image.fromarray(cv2.cvtColor(line, cv2.COLOR_BGR2RGB))
        return str(self.recognizer.predict(image) or "").strip(), "default"

    def _recognize_lines(self, lines: list[np.ndarray]) -> list[tuple[str, str]]:
        """Recognize bounded batches while preserving the detector's line order."""
        predict_batch = getattr(self.recognizer, "predict_batch", None)
        if not callable(predict_batch):
            self._last_recognition_batches = len(lines)
            return [self._recognize_line(line) for line in lines]

        results: list[tuple[str, str]] = []
        self._last_recognition_batches = 0
        for start in range(0, len(lines), _VIETOCR_BATCH_SIZE):
            images = [
                Image.fromarray(cv2.cvtColor(line, cv2.COLOR_BGR2RGB))
                for line in lines[start : start + _VIETOCR_BATCH_SIZE]
            ]
            predictions = predict_batch(images)
            if len(predictions) != len(images):
                raise ValueError("VietOCR batch result count does not match input count")
            results.extend((str(text or "").strip(), "default") for text in predictions)
            self._last_recognition_batches += 1
        return results

    @staticmethod
    def _save_crop_debug(line: np.ndarray, diagnostic: dict, text: str, layout_label: str) -> None:
        debug_dir = os.environ.get("DOCUMENT_PROCESSING_OCR_DEBUG_DIR")
        debug_file = os.environ.get("DOCUMENT_PROCESSING_OCR_DEBUG_FILE")
        if not debug_dir or not debug_file:
            return

        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(debug_file).stem)
        target = Path(debug_dir) / safe_name
        target.mkdir(parents=True, exist_ok=True)
        crop_name = (
            f"p{diagnostic['page_number']}_r{diagnostic['ocr_region_index_1based']}"
            f"_l{diagnostic['line_index_1based']}.png"
        )
        cv2.imwrite(str(target / crop_name), line)
        record = {
            **diagnostic,
            "source_file": debug_file,
            "layout_label": layout_label,
            "recognized_text": text,
            "crop_file": crop_name,
            "crop_size": [int(line.shape[1]), int(line.shape[0])],
        }
        with (target / "lines.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _detect_orientations(
        images: list[np.ndarray],
    ) -> list[tuple[int, int | None, float | None]]:
        """Classify line crops in bounded batches, preserving their order."""
        return detect_paddle_textline_orientations(
            images, batch_size=_TEXTLINE_ORIENTATION_BATCH_SIZE,
        )

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

            page_number = int(page.page_no)
            page_started = time.perf_counter()
            component_seconds = {
                "region_crop_orientation": 0.0,
                "line_detection_merge": 0.0,
                "line_crop_orientation": 0.0,
                "vietocr_recognition": 0.0,
                "line_geometry_postprocess": 0.0,
            }
            line_count = 0
            recognition_batches = 0
            orientation_batches = 0

            with TimeRecorder(conv_res, "ocr"):
                region_discovery_started = time.perf_counter()
                layout = page.predictions.layout
                if layout is not None and layout.clusters:
                    ocr_regions = [
                        (
                            cluster.bbox,
                            str(getattr(cluster.label, "value", cluster.label)).lower(),
                        )
                        for cluster in layout.clusters
                    ]
                else:
                    ocr_regions = [(rect, "page") for rect in self.get_ocr_rects(page)]
                component_seconds["region_discovery"] = time.perf_counter() - region_discovery_started
                print(
                    "OCR regions before line detection:",
                    page_number,
                    [
                        [round(rect.l, 1), round(rect.t, 1), round(rect.r, 1), round(rect.b, 1)]
                        for rect, _label in ocr_regions
                    ],
                    flush=True,
                )
                cells: list[TextCell] = []
                cell_region_indices: list[int] = []
                page_lines = []
                for ocr_rect, region_label in ocr_regions:
                    if ocr_rect.area() == 0:
                        continue
                    region_started = time.perf_counter()
                    crop = page._backend.get_page_image(
                        scale=self.scale, cropbox=ocr_rect
                    )
                    is_text_region = region_label in _TEXT_LAYOUT_LABELS
                    doc_orientation = 0
                    orientation_diagnostic = {
                        "scope": "layout_region",
                        "page_number": page_number,
                        "layout_label": region_label,
                        "bbox": [ocr_rect.l, ocr_rect.t, ocr_rect.r, ocr_rect.b],
                        "crop_size": list(crop.size),
                    }
                    if not is_text_region or crop.height > crop.width:
                        page_correction, page_orientation, page_confidence = detect_paddle_orientation(crop)
                        apply_page_orientation = page_confidence >= 0.7 and (
                            not is_text_region or page_orientation in (90, 270)
                        )
                        if apply_page_orientation:
                            doc_orientation = page_correction
                        orientation_diagnostic.update({
                            "doc_orientation_degrees": page_orientation,
                            "doc_orientation_confidence": page_confidence,
                            "doc_orientation_model": "PP-LCNet_x1_0_doc_ori",
                        })
                    orientation_diagnostic["correction_clockwise"] = doc_orientation
                    self.orientation_diagnostics.append(orientation_diagnostic)
                    _LOGGER.info(
                        "OCR_REGION_ORIENTATION %s",
                        json.dumps(orientation_diagnostic, separators=(",", ":")),
                    )
                    region_index = self._orientation_counts.get(page_number, 0) + 1
                    self._orientation_counts[page_number] = region_index
                    if doc_orientation:
                        crop = rotate_for_reading(crop, doc_orientation)
                    image_size = crop.size
                    image = cv2.cvtColor(np.asarray(crop), cv2.COLOR_RGB2BGR)
                    component_seconds["region_crop_orientation"] += time.perf_counter() - region_started
                    detection_image = image
                    detection_started = time.perf_counter()
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
                    if region_label == "table":
                        # Table cells have their own reading order and may share a
                        # baseline across column borders. Keep detector boxes
                        # separate so a row number cannot be joined to its description.
                        boxes = [
                            (np.asarray(box, dtype=np.float32), False)
                            for box in (boxes if boxes is not None else [])
                        ]
                    else:
                        boxes = merge_line_fragments(boxes)
                    if boxes is None or len(boxes) == 0:
                        component_seconds["line_detection_merge"] += time.perf_counter() - detection_started
                        continue
                    component_seconds["line_detection_merge"] += time.perf_counter() - detection_started

                    prepared_lines = []
                    for index, (quad, merged_fragments) in enumerate(boxes):
                        quad = np.asarray(quad, dtype=np.float32)
                        line = crop_line(
                            detection_image,
                            quad,
                            padding=2 if merged_fragments else 0,
                        )
                        prepared_lines.append((index, quad, merged_fragments, line))
                    line_count += len(prepared_lines)
                    page_lines.extend(
                        (prepared, ocr_rect, region_label, doc_orientation, region_index,
                         vertical_padding, image_size)
                        for prepared in prepared_lines
                    )

                line_orientation_started = time.perf_counter()
                orientation_inputs = [item[0][3] for item in page_lines]
                orientations = self._detect_orientations(orientation_inputs)
                orientation_batches = (
                    (len(orientation_inputs) + _TEXTLINE_ORIENTATION_BATCH_SIZE - 1)
                    // _TEXTLINE_ORIENTATION_BATCH_SIZE
                )
                for index, (item, orientation) in enumerate(zip(page_lines, orientations, strict=True)):
                    (
                        prepared, ocr_rect, region_label, doc_orientation,
                        region_index, vertical_padding, image_size,
                    ) = item
                    line_index, quad, merged_fragments, line = prepared
                    line_orientation_correction, line_orientation, line_confidence = orientation
                    if line_confidence < 0.7:
                        line_orientation_correction = 0
                    if line_orientation_correction == 180:
                        line = cv2.rotate(line, cv2.ROTATE_180)
                    page_lines[index] = (
                        (line_index, quad, merged_fragments, line,
                         line_orientation_correction, line_orientation, line_confidence),
                        ocr_rect, region_label, doc_orientation, region_index,
                        vertical_padding, image_size,
                    )
                component_seconds["line_crop_orientation"] += time.perf_counter() - line_orientation_started

                recognition_started = time.perf_counter()
                recognized_lines = self._recognize_lines(
                    [item[0][3] for item in page_lines]
                )
                component_seconds["vietocr_recognition"] += time.perf_counter() - recognition_started
                recognition_batches += self._last_recognition_batches
                geometry_started = time.perf_counter()
                for item, (text, route) in zip(page_lines, recognized_lines):
                    (prepared, ocr_rect, region_label, doc_orientation, region_index,
                     vertical_padding, image_size) = item
                    (index, quad, merged_fragments, line, line_orientation_correction,
                     line_orientation, line_confidence) = prepared
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
                    rect = tesseract_box_to_bounding_rectangle(
                        box,
                        original_offset=ocr_rect,
                        scale=self.scale,
                        orientation=doc_orientation,
                        im_size=image_size,
                    )
                    rect_x = [rect.r_x0, rect.r_x1, rect.r_x2, rect.r_x3]
                    rect_y = [rect.r_y0, rect.r_y1, rect.r_y2, rect.r_y3]
                    diagnostic = {
                        "page_number": page_number,
                        "ocr_region_index_1based": region_index,
                        "line_index_1based": index + 1,
                        "route": route,
                        "recognized_text_present": bool(text),
                        "merged_fragments": bool(merged_fragments),
                        "bbox": [
                            float(min(rect_x)), float(min(rect_y)),
                            float(max(rect_x)), float(max(rect_y)),
                        ],
                        "bbox_coordinate_system": "docling_page_coordinate",
                        "bbox_coordinate_origin": "TOPLEFT",
                    }
                    self._save_crop_debug(line, diagnostic, text, region_label)
                    self.routing_diagnostics.append(diagnostic)
                    _LOGGER.info("OCR_LINE_ROUTE %s", json.dumps(diagnostic, separators=(",", ":")))
                    line_orientation_diagnostic = {
                        "scope": "text_line",
                        "page_number": page_number,
                        "layout_label": region_label,
                        "ocr_region_index_1based": region_index,
                        "line_index_1based": index + 1,
                        "textline_orientation_degrees": line_orientation,
                        "textline_orientation_confidence": line_confidence,
                        "textline_orientation_model": "PP-LCNet_x0_25_textline_ori",
                        "correction_clockwise": line_orientation_correction,
                        "bbox": diagnostic["bbox"],
                        "bbox_coordinate_system": diagnostic["bbox_coordinate_system"],
                        "bbox_coordinate_origin": diagnostic["bbox_coordinate_origin"],
                    }
                    self.orientation_diagnostics.append(line_orientation_diagnostic)
                    _LOGGER.info(
                        "OCR_LINE_ORIENTATION %s",
                        json.dumps(line_orientation_diagnostic, separators=(",", ":")),
                    )
                    if not text:
                        continue
                    cells.append(
                        TextCell(
                            index=index,
                            text=text,
                            orig=text,
                            confidence=1.0,
                            from_ocr=True,
                            rect=rect,
                        )
                    )
                    cell_region_indices.append(region_index)
                component_seconds["line_geometry_postprocess"] += time.perf_counter() - geometry_started
                cells = self._deduplicate_overlapping_cells(cells, cell_region_indices)
                self.post_process_cells(cells, page, conv_res)
            component_ms = {
                key: round(value * 1000, 2)
                for key, value in component_seconds.items()
            }
            component_ms["ocr_wall"] = round((time.perf_counter() - page_started) * 1000, 2)
            _LOGGER.info(
                "OCR_COMPONENT_TIMING %s",
                json.dumps(
                    {
                        "invoice_id": self.current_reference_id,
                        "page_number": page_number,
                        "region_count": len(ocr_regions),
                        "line_count": line_count,
                        "orientation_batches": orientation_batches,
                        "recognition_batches": recognition_batches,
                        "timings_ms": component_ms,
                    },
                    separators=(",", ":"),
                ),
            )
            yield page


def register_vietocr() -> None:
    for allow_external_plugins in (False, True):
        factory = get_ocr_factory(allow_external_plugins=allow_external_plugins)
        if VietOcrOptions not in factory.classes:
            factory.register(VietOcrModel, "document-pipeline-experiment", __name__)
