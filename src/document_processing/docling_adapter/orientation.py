"""Tesseract OSD helpers for scanned page and OCR region images."""

from __future__ import annotations

import re
import logging
import subprocess
import tempfile
from collections.abc import Sequence
from functools import lru_cache
from threading import Lock
from typing import Any

from PIL import Image

from docling_core.types.doc import BoundingBox, CoordOrigin
from docling.models.stages.ocr.tesseract_utils import parse_tesseract_orientation

_orientation_lock = Lock()
_log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _paddle_orientation_model():
    from paddleocr import DocImgOrientationClassification

    return DocImgOrientationClassification(model_name="PP-LCNet_x1_0_doc_ori", device="cpu")


@lru_cache(maxsize=1)
def _paddle_textline_orientation_model():
    from paddleocr import TextLineOrientationClassification

    return TextLineOrientationClassification(
        model_name="PP-LCNet_x0_25_textline_ori", device="cpu"
    )


def preload_paddle_page_orientation_model() -> None:
    """Load the lazy page-orientation classifier before the first document request."""
    _paddle_orientation_model()


def detect_paddle_orientation(image: Image.Image) -> tuple[int, int, float]:
    """Return clockwise correction, predicted orientation, and confidence."""
    import numpy as np

    image_bgr = np.asarray(image.convert("RGB"))[:, :, ::-1].copy()
    try:
        with _orientation_lock:
            result = next(iter(_paddle_orientation_model().predict(image_bgr, batch_size=1)))
    except Exception:
        _log.warning(
            "Paddle page orientation inference failed; continuing without rotation correction.",
            exc_info=True,
        )
        return 0, 0, 0.0
    payload = result.json
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)
    result = payload.get("res", payload)
    angle = int(result["label_names"][0])
    if angle not in (0, 90, 180, 270):
        raise ValueError(f"Unsupported orientation: {angle}")
    return (-angle) % 360, angle, float(result["scores"][0])


def detect_paddle_textline_orientation(image: Image.Image) -> tuple[int, int, float]:
    """Return clockwise correction, predicted text-line orientation, and confidence."""
    return detect_paddle_textline_orientations([image], batch_size=1)[0]


def detect_paddle_textline_orientations(
    images: Sequence[Any], *, batch_size: int = 16,
) -> list[tuple[int, int, float]]:
    """Classify PIL images or BGR arrays in bounded batches, preserving input order."""
    if not images:
        return []
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    import numpy as np

    predictions = []
    with _orientation_lock:
        model = _paddle_textline_orientation_model()
        for start in range(0, len(images), batch_size):
            image_bgrs = []
            for image in images[start : start + batch_size]:
                if isinstance(image, Image.Image):
                    image_bgrs.append(np.asarray(image.convert("RGB"))[:, :, ::-1].copy())
                else:
                    image_bgrs.append(np.asarray(image))
            predictions.extend(model.predict(
                image_bgrs,
                batch_size=batch_size,
            ))
    if len(predictions) != len(images):
        raise ValueError("Text-line orientation result count does not match input")

    results = []
    for prediction in predictions:
        payload = prediction.json
        if isinstance(payload, str):
            import json
            payload = json.loads(payload)
        result = payload.get("res", payload)
        label = result["label_names"][0]
        angle = int(str(label).split("_", maxsplit=1)[0])
        if angle not in (0, 180):
            raise ValueError(f"Unsupported text-line orientation: {label}")
        results.append(((-angle) % 360, angle, float(result["scores"][0])))
    return results


def detect_tesseract_orientation(image: Image.Image) -> tuple[int, int | None, float | None]:
    """Return clockwise correction, reported orientation, and OSD confidence."""
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


def rotate_for_reading(image: Image.Image, correction_clockwise: int) -> Image.Image:
    """Apply Tesseract's clockwise correction to a copy of the image."""
    return image.rotate(-correction_clockwise, expand=True) if correction_clockwise else image


def bbox_in_original_orientation(
    bbox: tuple[float, float, float, float],
    image_size: tuple[int, int],
    correction_clockwise: int,
) -> tuple[float, float, float, float]:
    """Map an axis-aligned bbox from the corrected image back to its source."""
    left, top, right, bottom = bbox
    width, height = image_size
    if correction_clockwise == 90:
        return top, height - right, bottom, height - left
    if correction_clockwise == 180:
        return width - right, height - bottom, width - left, height - top
    if correction_clockwise == 270:
        return width - bottom, left, width - top, right
    return bbox


class OrientedPageBackend:
    """Render one page in its OSD-corrected orientation for every pipeline stage."""

    def __init__(self, backend: object, correction_clockwise: int):
        self._backend = backend
        self._correction = correction_clockwise % 360
        self._source_size = backend.get_size()
        width, height = self._source_size.width, self._source_size.height
        if self._correction in (90, 270):
            width, height = height, width
        self._size = type(self._source_size)(width=width, height=height)

    def __getattr__(self, name: str):
        return getattr(self._backend, name)

    def get_size(self):
        return self._size

    def get_page_image(self, scale: float = 1, cropbox: BoundingBox | None = None):
        source_box = None
        if cropbox is not None:
            box = cropbox.to_top_left_origin(page_height=self._size.height)
            left, top, right, bottom = bbox_in_original_orientation(
                (box.l, box.t, box.r, box.b),
                (self._source_size.width, self._source_size.height),
                self._correction,
            )
            source_box = BoundingBox(
                l=left,
                t=top,
                r=right,
                b=bottom,
                coord_origin=CoordOrigin.TOPLEFT,
            )
        image = self._backend.get_page_image(scale=scale, cropbox=source_box)
        return rotate_for_reading(image, self._correction)
