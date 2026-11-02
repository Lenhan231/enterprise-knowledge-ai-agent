"""Tesseract OSD helpers for scanned page and OCR region images."""

from __future__ import annotations

import re
import subprocess
import tempfile

from PIL import Image

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
