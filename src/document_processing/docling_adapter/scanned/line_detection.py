"""Shared RapidOCR text-line detection and quadrilateral cropping."""

from __future__ import annotations

import cv2
import numpy as np


def create_line_detector():
    from rapidocr import RapidOCR

    return RapidOCR()


def detect_line_boxes(detector, image: np.ndarray):
    result = detector(image, use_det=True, use_cls=False, use_rec=False)
    return getattr(result, "boxes", None)


def crop_line(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    quad = np.asarray(points, dtype=np.float32)
    top_left, top_right, bottom_right, bottom_left = quad
    width = max(int(np.linalg.norm(top_right - top_left)), int(np.linalg.norm(bottom_right - bottom_left)), 1)
    height = max(int(np.linalg.norm(bottom_left - top_left)), int(np.linalg.norm(bottom_right - top_right)), 1)
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    return cv2.warpPerspective(image, cv2.getPerspectiveTransform(quad, target), (width, height))
