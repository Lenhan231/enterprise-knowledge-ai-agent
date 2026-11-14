"""Shared RapidOCR text-line detection and quadrilateral cropping."""

from __future__ import annotations

import cv2
import numpy as np


def _detect_repeated_left_strip(image: np.ndarray) -> list[float] | None:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    height, width = gray.shape[:2]
    if width < 20 or height < 20:
        return None
    offset = max(0, int(width * 0.004))
    region = gray[:, offset:int(width * 0.08)]
    if region.size == 0:
        return None
    candidates = []
    for threshold in (210, 230, 250):
        count, _, stats, _ = cv2.connectedComponentsWithStats((region < threshold).astype(np.uint8), 8)
        components = [
            (x, y, box_width, box_height)
            for x, y, box_width, box_height, area in stats[1:count]
            if box_width >= max(2, int(width * 0.008))
            and box_width <= int(width * 0.08)
            and box_height >= max(2, int(height * 0.002))
            and box_height <= int(height * 0.06)
            and area >= max(5, int(width * height * 0.000003))
        ]
        if len(components) < 8:
            continue
        top = min(y for _, y, _, _ in components)
        bottom = max(y + box_height for _, y, _, box_height in components)
        if bottom - top < 0.65 * height:
            continue
        lefts = np.asarray([offset + x for x, _, _, _ in components])
        rights = np.asarray([offset + x + box_width for x, _, box_width, _ in components])
        candidates.append((len(components), [
            float(np.quantile(lefts, 0.10) / width), float(top / height),
            float(np.quantile(rights, 0.75) / width), float(bottom / height),
        ]))
    return max(candidates, key=lambda candidate: candidate[0])[1] if candidates else None


def detect_repeated_edge_strips(image: np.ndarray) -> list[list[float]]:
    """Find tall repeated marks along any page edge; return normalized boxes."""
    height, width = image.shape[:2]
    views = (
        (image, 0),
        (cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE), 90),
        (cv2.rotate(image, cv2.ROTATE_180), 180),
        (cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE), 270),
    )
    boxes = []
    for view, inverse_rotation in views:
        box = _detect_repeated_left_strip(view)
        if box is None:
            continue
        left, top, right, bottom = box
        if inverse_rotation == 90:
            box = [top, 1 - right, bottom, 1 - left]
        elif inverse_rotation == 180:
            box = [1 - right, 1 - bottom, 1 - left, 1 - top]
        elif inverse_rotation == 270:
            box = [1 - bottom, left, 1 - top, right]
        if not any(_box_iou(box, seen) >= 0.5 for seen in boxes):
            boxes.append(box)
    return boxes


def _box_iou(first: list[float], second: list[float]) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area = lambda box: max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
    union = area(first) + area(second) - intersection
    return intersection / union if union else 0.0


def overlaps_region(box: list[float], region: list[float], threshold: float = 0.5) -> bool:
    left, top = max(box[0], region[0]), max(box[1], region[1])
    right, bottom = min(box[2], region[2]), min(box[3], region[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area = max(1e-9, box[2] - box[0]) * max(1e-9, box[3] - box[1])
    return intersection / area >= threshold


def create_line_detector(*, cpu_threads: int = 2):
    import logging
    import torch
    from rapidocr import EngineType, RapidOCR

    if torch.cuda.is_available():
        logging.getLogger(__name__).info(
            "RapidOCR line detection using PyTorch CUDA backend."
        )
        return RapidOCR(params={
            "Det.engine_type": EngineType.TORCH,
            "EngineConfig.torch.use_cuda": True,
            "EngineConfig.torch.cuda_ep_cfg.device_id": 0,
        })
    logging.getLogger(__name__).info(
        "RapidOCR line detection using CPU backend with max-edge resize and %s intra-op threads.",
        max(1, int(cpu_threads)),
    )
    # Layout crops are already rendered at OCR scale. Upscaling their short edge
    # to 736px makes a one-line region unnecessarily large for detection.
    return RapidOCR(params={
        "Det.limit_type": "max",
        "EngineConfig.onnxruntime.intra_op_num_threads": max(1, int(cpu_threads)),
    })


def detect_line_boxes(detector, image: np.ndarray):
    result = detector(image, use_det=True, use_cls=False, use_rec=False)
    return getattr(result, "boxes", None)


def merge_line_fragments(boxes) -> list[tuple[np.ndarray, bool]]:
    """Join horizontally adjacent detections that share the same text baseline."""
    if boxes is None or len(boxes) == 0:
        return []

    bounds = []
    for box in boxes:
        points = np.asarray(box, dtype=np.float32)
        bounds.append((points[:, 0].min(), points[:, 1].min(), points[:, 0].max(), points[:, 1].max()))

    groups = [{index} for index in range(len(bounds))]
    for left_index, first in enumerate(bounds):
        first_height = max(1.0, first[3] - first[1])
        for right_index in range(left_index + 1, len(bounds)):
            second = bounds[right_index]
            second_height = max(1.0, second[3] - second[1])
            overlap = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
            if overlap / min(first_height, second_height) < 0.55:
                continue
            gap = max(0.0, max(first[0], second[0]) - min(first[2], second[2]))
            if gap > max(first_height, second_height):
                continue
            first_group = next(group for group in groups if left_index in group)
            second_group = next(group for group in groups if right_index in group)
            if first_group is not second_group:
                first_group.update(second_group)
                groups.remove(second_group)

    merged = []
    for group in groups:
        points = np.concatenate([np.asarray(boxes[index], dtype=np.float32) for index in group])
        left, top = points.min(axis=0)
        right, bottom = points.max(axis=0)
        quad = np.array([[left, top], [right, top], [right, bottom], [left, bottom]], dtype=np.float32)
        merged.append((quad, len(group) > 1))
    return sorted(merged, key=lambda item: (item[0][:, 1].min(), item[0][:, 0].min()))


def crop_line(image: np.ndarray, points: np.ndarray, padding: int = 0) -> np.ndarray:
    quad = np.asarray(points, dtype=np.float32)
    top_left, top_right, bottom_right, bottom_left = quad
    width = max(int(np.linalg.norm(top_right - top_left)), int(np.linalg.norm(bottom_right - bottom_left)), 1)
    height = max(int(np.linalg.norm(bottom_left - top_left)), int(np.linalg.norm(bottom_right - top_right)), 1)
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    crop = cv2.warpPerspective(
        image,
        cv2.getPerspectiveTransform(quad, target),
        (width, height),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return cv2.copyMakeBorder(
        crop, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=(255, 255, 255)
    ) if padding else crop
