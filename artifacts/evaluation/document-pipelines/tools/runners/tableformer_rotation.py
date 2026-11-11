"""Experimental rotation of table crops before Docling's TableFormer inference."""

from __future__ import annotations

from collections.abc import Callable
import re
import subprocess
import tempfile

import numpy as np
from PIL import Image

MINIMUM_OSD_CONFIDENCE = 5.0


def _detect_rotation_clockwise(crop: np.ndarray) -> tuple[int, float | None]:
    """Use Tesseract OSD; uncertain crops stay in their original orientation."""
    with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
        Image.fromarray(crop).save(image_file.name)
        try:
            output = subprocess.run(
                ["tesseract", image_file.name, "stdout", "--psm", "0", "-l", "osd"],
                capture_output=True,
                check=True,
                text=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            return 0, None
    rotation = re.search(r"Rotate:\s*(\d+)", output)
    confidence = re.search(r"Orientation confidence:\s*([\d.]+)", output)
    if not rotation or not confidence:
        return 0, None
    confidence_value = float(confidence.group(1))
    if confidence_value < MINIMUM_OSD_CONFIDENCE:
        return 0, confidence_value
    return int(rotation.group(1)) % 360, confidence_value


def _rotate_bbox(
    box: dict, width: int, height: int, rotation_clockwise: int
) -> dict:
    """Rotate a top-left-origin bbox and preserve any extra cell metadata."""
    left, top, right, bottom = (
        float(box[key]) for key in ("l", "t", "r", "b")
    )
    corners = ((left, top), (right, top), (right, bottom), (left, bottom))
    if rotation_clockwise == 90:
        points = [(height - y, x) for x, y in corners]
    elif rotation_clockwise == 180:
        points = [(width - x, height - y) for x, y in corners]
    elif rotation_clockwise == 270:
        points = [(y, width - x) for x, y in corners]
    else:
        points = list(corners)
    rotated = dict(box)
    rotated.update(
        l=min(x for x, _ in points),
        t=min(y for _, y in points),
        r=max(x for x, _ in points),
        b=max(y for _, y in points),
    )
    return rotated


def enable_table_crop_rotation(
    predictor: object, rotation_clockwise: int | str
) -> Callable[[str], None]:
    """Optionally orient each table crop before TableFormer and map boxes back."""
    if rotation_clockwise != "auto" and rotation_clockwise not in {0, 90, 180, 270}:
        raise ValueError("Table crop rotation must be auto, 0, 90, 180, or 270 degrees")
    if rotation_clockwise == 0:
        return lambda _page_id: None

    original: Callable = predictor.multi_table_predict
    current_page_id = {"value": None}
    page_table_counts: dict[str, int] = {}
    diagnostics: list[dict] = []
    predictor.table_rotation_diagnostics = diagnostics

    def rotated_multi_table_predict(
        iocr_page: dict, table_bboxes: list[list[float]], *args, **kwargs
    ) -> list[dict]:
        page_image = np.asarray(iocr_page["image"])
        page_height, page_width = page_image.shape[:2]
        rotated_outputs = []

        for table_bbox in table_bboxes:
            x0, y0, x1, y1 = map(lambda value: int(round(value)), table_bbox)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(page_width, x1), min(page_height, y1)
            if x1 <= x0 or y1 <= y0:
                continue

            crop = page_image[y0:y1, x0:x1]
            page_id = current_page_id["value"]
            table_index = page_table_counts.get(page_id, 0) + 1
            page_table_counts[page_id] = table_index
            if rotation_clockwise == "auto":
                table_rotation, osd_confidence = _detect_rotation_clockwise(crop)
            else:
                table_rotation, osd_confidence = rotation_clockwise, None
            diagnostics.append({
                "page_id": page_id,
                "table_index_1based": table_index,
                "bbox_scaled": [x0, y0, x1, y1],
                "rotation_clockwise": table_rotation,
                "osd_confidence": osd_confidence,
                "minimum_osd_confidence": MINIMUM_OSD_CONFIDENCE if rotation_clockwise == "auto" else None,
            })
            if table_rotation == 0:
                output = original(
                    iocr_page, [[x0, y0, x1, y1]], *args, **kwargs
                )[0]
                rotated_outputs.append(output)
                continue

            quarter_turns_ccw = (-table_rotation // 90) % 4
            rotated_image = np.rot90(crop, k=quarter_turns_ccw).copy()
            crop_height, crop_width = crop.shape[:2]
            rotated_height, rotated_width = rotated_image.shape[:2]

            rotated_tokens = []
            for token in iocr_page.get("tokens", []):
                cell = token.get("bbox", {})
                left = max(float(cell.get("l", 0)), x0)
                top = max(float(cell.get("t", 0)), y0)
                right = min(float(cell.get("r", 0)), x1)
                bottom = min(float(cell.get("b", 0)), y1)
                if right <= left or bottom <= top:
                    continue
                local_box = dict(
                    cell,
                    l=left - x0,
                    t=top - y0,
                    r=right - x0,
                    b=bottom - y0,
                )
                rotated_token = dict(token)
                rotated_token["bbox"] = _rotate_bbox(
                    local_box, crop_width, crop_height, table_rotation
                )
                rotated_tokens.append(rotated_token)

            rotated_page = {
                "image": rotated_image,
                "width": rotated_width,
                "height": rotated_height,
                "tokens": rotated_tokens,
            }
            output = original(
                rotated_page,
                [[0, 0, rotated_width, rotated_height]],
                *args,
                **kwargs,
            )[0]

            inverse_rotation = (360 - table_rotation) % 360
            for cell in output.get("tf_responses", []):
                for cell_box in [cell.get("bbox"), *cell.get("text_cell_bboxes", [])]:
                    if not cell_box:
                        continue
                    mapped = _rotate_bbox(
                        cell_box,
                        rotated_width,
                        rotated_height,
                        inverse_rotation,
                    )
                    mapped.update(
                        l=mapped["l"] + x0,
                        t=mapped["t"] + y0,
                        r=mapped["r"] + x0,
                        b=mapped["b"] + y0,
                    )
                    cell_box.update(mapped)
            rotated_outputs.append(output)

        return rotated_outputs

    predictor.multi_table_predict = rotated_multi_table_predict

    def set_page_id(page_id: str) -> None:
        current_page_id["value"] = page_id

    return set_page_id
