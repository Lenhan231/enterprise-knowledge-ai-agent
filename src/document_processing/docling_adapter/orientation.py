"""Tesseract OSD helpers for scanned page and OCR region images."""

from __future__ import annotations

import re
import subprocess
import tempfile

from PIL import Image

from docling_core.types.doc import BoundingBox, CoordOrigin
from docling.models.stages.ocr.tesseract_utils import parse_tesseract_orientation


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
