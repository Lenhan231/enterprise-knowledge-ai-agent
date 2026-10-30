"""Conservative OCR cleanup and table-cell dash recovery using source pixels."""

from __future__ import annotations

import re
import subprocess
import tempfile

import cv2
import numpy as np
from PIL import Image

from .line_detection import detect_repeated_edge_strips, overlaps_region


def _quality(text: str) -> float:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return 0.0
    tokens = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    visible = [char for char in normalized if not char.isspace()]
    alphanumeric = sum(char.isalnum() for char in visible) / max(1, len(visible))
    words = sum(len(token) >= 2 for token in tokens) / max(1, len(tokens))
    return 0.6 * alphanumeric + 0.4 * words


def _protected_token(text: str) -> bool:
    value = re.sub(r"\s+", "", text).upper()
    return bool(re.fullmatch(
        r"(?:B\d{1,3}-[A-Z]{2,5}|V\.?\d{1,2}|VND|VNĐ|NGÀNVNĐ|\d+(?:[.,/]\d+)*|[IVXLCDM]{1,5})",
        value,
    ))


class _AlternateRecognizer:
    def __init__(self, primary_engine: str):
        self.primary_engine = primary_engine
        self._vietocr = None

    def _vietocr_text(self, crop: np.ndarray) -> str:
        if self._vietocr is None:
            import torch
            from vietocr.tool.config import Cfg
            from vietocr.tool.predictor import Predictor

            config = Cfg.load_config_from_name("vgg_seq2seq")
            config["device"] = "cuda:0" if torch.cuda.is_available() else "cpu"
            config["dataset"]["image_max_width"] = 512
            config["predictor"]["beamsearch"] = False
            self._vietocr = Predictor(config)
        return str(self._vietocr.predict(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))) or "").strip()

    @staticmethod
    def _tesseract_text(crop: np.ndarray) -> str:
        with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
            if not cv2.imwrite(image_file.name, crop):
                return ""
            try:
                result = subprocess.run(
                    ["tesseract", image_file.name, "stdout", "-l", "vie+eng", "--psm", "7"],
                    capture_output=True, check=True, text=True,
                )
            except (OSError, subprocess.CalledProcessError):
                return ""
        return result.stdout.strip()

    def recognize(self, crop: np.ndarray) -> str:
        crops = [crop]
        if crop.shape[0] > crop.shape[1] * 1.4:
            crops = [
                cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE),
                cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE),
            ]
        recognizer = self._vietocr_text if self.primary_engine == "tesseract" else self._tesseract_text
        return max((recognizer(item) for item in crops), key=_quality, default="")


def _overlap_ratio(box: list[float], region: list[float]) -> float:
    left, top = max(box[0], region[0]), max(box[1], region[1])
    right, bottom = min(box[2], region[2]), min(box[3], region[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area = max(1e-9, box[2] - box[0]) * max(1e-9, box[3] - box[1])
    return intersection / area


def _is_seal_or_signature(box: list[float], image: np.ndarray) -> bool:
    x0, y0, x1, y1 = box
    height, width = image.shape[:2]
    crop = image[max(0, int(y0 * height)):min(height, int(y1 * height)),
                 max(0, int(x0 * width)):min(width, int(x1 * width))]
    area_ratio = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if crop.size:
        red = (crop[:, :, 2] > 90) & (crop[:, :, 2] > crop[:, :, 1] * 1.3) & (crop[:, :, 2] > crop[:, :, 0] * 1.2)
        if float(red.mean()) >= 0.02 and y0 >= 0.5:
            return True
    return area_ratio <= 0.005 and y0 >= 0.65


def clean_ocr_elements(
    elements: list[dict],
    tables: list[dict],
    page_images: dict[int, np.ndarray],
    page_sizes: dict[int, tuple[float, float]],
    primary_engine: str,
) -> tuple[list[dict], list[dict]]:
    """Remove only clear OCR artifacts; keep ambiguous text and report actions."""
    diagnostics: list[dict] = []
    alternate = _AlternateRecognizer(primary_engine)
    figures_by_page: dict[int, list[tuple[list[float], str]]] = {}
    tables_by_page: dict[int, list[list[float]]] = {}
    for element in elements:
        metadata = element.get("metadata") or {}
        box = metadata.get("bbox")
        page = metadata.get("page_number")
        label = element.get("element_type") or metadata.get("element_type")
        if box and page is not None and label in {"figure", "seal"}:
            figures_by_page.setdefault(int(page), []).append(([float(value) for value in box], label))
    for table in tables:
        metadata = table.get("metadata") or {}
        box, page = metadata.get("bbox"), table.get("page_number", metadata.get("page_number"))
        if box and page is not None:
            tables_by_page.setdefault(int(page), []).append([float(value) for value in box])

    cleaned: list[dict] = []
    edge_strips_by_page = {
        page_number: detect_repeated_edge_strips(image)
        for page_number, image in page_images.items()
    }
    for element in elements:
        metadata = element.get("metadata") or {}
        engine_tag = str(metadata.get("text_extraction_method", ""))
        page_number = metadata.get("page_number")
        text = str(element.get("text") or "").strip()
        box = metadata.get("bbox")
        image = page_images.get(int(page_number)) if page_number is not None else None
        if (
            not text or not box or image is None
            or engine_tag not in {"docling.vietocr", "docling.tesseract"}
        ):
            cleaned.append(element)
            continue
        page_height, page_width = image.shape[:2]
        source_width, source_height = page_sizes.get(int(page_number), (float(page_width), float(page_height)))
        norm = [float(box[0]) / source_width, float(box[1]) / source_height,
                float(box[2]) / source_width, float(box[3]) / source_height]
        table_boxes = tables_by_page.get(int(page_number), [])
        figures = figures_by_page.get(int(page_number), [])
        signature_boxes = [
            candidate for candidate, label in figures
            if label == "seal" or _is_seal_or_signature(
                [candidate[0] / source_width, candidate[1] / source_height,
                 candidate[2] / source_width, candidate[3] / source_height], image
            )
        ]
        in_table = any(_overlap_ratio(box, candidate) >= 0.5 for candidate in table_boxes)
        in_signature = any(_overlap_ratio(box, candidate) >= 0.8 for candidate in signature_boxes)
        edge_strips = edge_strips_by_page.get(int(page_number), [])
        in_edge_strip = any(overlaps_region(norm, strip) for strip in edge_strips)
        visible = [char for char in text if not char.isspace()]
        punctuation_ratio = sum(not char.isalnum() for char in visible) / max(1, len(visible))
        tokens = re.findall(r"[^\W_]+", text, flags=re.UNICODE)
        short_fragments = (
            len(tokens) >= 3 and sum(len(token) == 1 for token in tokens) / len(tokens) >= 0.6
        ) or (len(tokens) <= 2 and tokens and all(len(token) == 1 for token in tokens))
        quality = _quality(text)
        width = norm[2] - norm[0]
        separator = not in_table and len(visible) >= 8 and punctuation_ratio >= 0.75 and width >= 0.25
        tiny_symbol = (
            not in_table and "".join(visible) in {".", ":", "'", "`", "~", "¬", "|", "\\"}
            and width * (norm[3] - norm[1]) <= 0.0002
        )
        edge_noise = not in_table and in_edge_strip and quality < 0.78 and not _protected_token(text)
        figure_noise = in_signature and not _protected_token(text) and not (
            any(len(token) >= 2 for token in tokens) and quality >= 0.68 and punctuation_ratio < 0.4
        )
        reason = (
            "long_separator_outside_table" if separator else
            "isolated_symbol" if tiny_symbol else
            "repeated_edge_artifact" if edge_noise else
            "nontext_in_figure" if figure_noise else None
        )
        if reason:
            diagnostics.append({"page_number": page_number, "bbox": box, "text_before": text,
                                "action": "removed", "reason": reason})
            continue

        suspicious = not in_table and not _protected_token(text) and (
            quality < 0.45 or short_fragments or punctuation_ratio >= 0.45
        )
        if suspicious:
            left = max(0, int(norm[0] * page_width) - 3)
            top = max(0, int(norm[1] * page_height) - 3)
            right = min(page_width, int(norm[2] * page_width) + 3)
            bottom = min(page_height, int(norm[3] * page_height) + 3)
            crop = image[top:bottom, left:right]
            candidate = alternate.recognize(crop) if crop.size else ""
            same_digits = re.findall(r"\d+", text) == re.findall(r"\d+", candidate)
            candidate_tokens = re.findall(r"[^\W_]+", candidate, flags=re.UNICODE)
            if (
                candidate and sum(len(token) >= 2 for token in candidate_tokens) >= 2
                and same_digits and _quality(candidate) >= 0.78
                and _quality(candidate) >= quality + 0.2
            ):
                replacement = dict(element, text=candidate)
                cleaned.append(replacement)
                diagnostics.append({"page_number": page_number, "bbox": box, "text_before": text,
                                    "text_after": candidate, "action": "replaced",
                                    "reason": "alternate_ocr_clearer"})
                continue
            diagnostics.append({"page_number": page_number, "bbox": box, "text_before": text,
                                "alternate_text": candidate, "action": "kept_and_flagged",
                                "reason": "alternate_ocr_not_decisive"})
        cleaned.append(element)
    return cleaned, diagnostics


def recover_empty_cell_dashes(
    cells: list,
    grid: list[list[str]],
    page_image: np.ndarray,
    page_width: float,
    page_height: float,
) -> list[list[int]]:
    """Fill blank 1x1 TableFormer cells when a small horizontal dash is visible."""
    if not grid or not grid[0] or any(len(row) != len(grid[0]) for row in grid):
        return []
    rows, columns = len(grid), len(grid[0])
    by_row: list[list[list[float]]] = [[] for _ in range(rows)]
    by_column: list[list[list[float]]] = [[] for _ in range(columns)]
    cell_boxes = {}
    for cell in cells:
        row, column = int(cell.start_row_offset_idx), int(cell.start_col_offset_idx)
        if not (0 <= row < rows and 0 <= column < columns) or cell.bbox is None:
            continue
        box = _top_left_box(cell.bbox, page_height)
        cell_boxes[(row, column)] = (cell, box)
        by_row[row].append(box)
        by_column[column].append(box)
    if any(not values for values in by_row) or any(not values for values in by_column):
        return []
    row_centers = [float(np.median([(b[1] + b[3]) / 2 for b in boxes])) for boxes in by_row]
    column_rights = [float(np.median([b[2] for b in boxes])) for boxes in by_column]
    x_edges = [min(b[0] for b in by_column[0])]
    x_edges.extend((column_rights[i] + column_rights[i + 1]) / 2 for i in range(columns - 1))
    x_edges.append(max(b[2] for b in by_column[-1]))
    if any(right <= left for left, right in zip(x_edges, x_edges[1:])):
        return []
    image_height, image_width = page_image.shape[:2]
    scale_x, scale_y = image_width / page_width, image_height / page_height
    width_min = max(2, int(np.ceil(4 * scale_x / 2.5)))
    width_max = max(3, int(np.ceil(28 * scale_x / 2.5)))
    height_min = max(1, int(np.ceil(scale_y / 2.5)))
    height_max = max(height_min, int(np.ceil(6 * scale_y / 2.5)))
    area_min = max(3, int(np.ceil(6 * scale_x * scale_y / 2.5**2)))
    recovered = []
    for row in range(rows):
        for column in range(columns):
            if grid[row][column].strip():
                continue
            cell_info = cell_boxes.get((row, column))
            if cell_info is None:
                continue
            cell, _box = cell_info
            if int(cell.row_span) != 1 or int(cell.col_span) != 1 or str(cell.text or "").strip():
                continue
            gaps = []
            if row:
                gaps.append(row_centers[row] - row_centers[row - 1])
            if row + 1 < rows:
                gaps.append(row_centers[row + 1] - row_centers[row])
            gap = min(gaps) if gaps else 0
            if gap <= 0:
                continue
            left, right = x_edges[column:column + 2]
            margin = 0.02 * (right - left)
            x0, x1 = int((left + margin) * scale_x), int((right - margin) * scale_x)
            y0, y1 = int((row_centers[row] - 0.28 * gap) * scale_y), int((row_centers[row] + 0.28 * gap) * scale_y)
            crop = page_image[max(0, y0):min(image_height, y1), max(0, x0):min(image_width, x1)]
            if crop.size == 0:
                continue
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
            count, _, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
            if any(width_min <= w <= width_max and height_min <= h <= height_max
                   and w / max(h, 1) >= 2 and area >= area_min
                   for _, _, w, h, area in stats[1:count]):
                grid[row][column] = "-"
                recovered.append([row, column])
    return recovered


def _top_left_box(box, page_height: float) -> list[float]:
    values = [float(box.l), float(box.t), float(box.r), float(box.b)]
    if str(getattr(box, "coord_origin", "")).upper().endswith("BOTTOMLEFT"):
        return [min(values[0], values[2]), page_height - max(values[1], values[3]),
                max(values[0], values[2]), page_height - min(values[1], values[3])]
    return [min(values[0], values[2]), min(values[1], values[3]),
            max(values[0], values[2]), max(values[1], values[3])]
