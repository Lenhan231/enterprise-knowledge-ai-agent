"""Experimental per-page orientation for layout inference only."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
from PIL import Image

from tableformer_rotation import MINIMUM_OSD_CONFIDENCE, _detect_rotation_clockwise


def _map_bbox_to_source(box: object, width: float, height: float, rotation: int) -> None:
    left, top, right, bottom = (getattr(box, key) for key in ("l", "t", "r", "b"))
    if rotation == 90:
        mapped = (top, height - right, bottom, height - left)
    elif rotation == 180:
        mapped = (width - right, height - bottom, width - left, height - top)
    elif rotation == 270:
        mapped = (width - bottom, left, width - top, right)
    else:
        mapped = (left, top, right, bottom)
    box.l, box.t, box.r, box.b = mapped


def enable_layout_rotation(layout_model: object) -> Callable[[str], None]:
    """Rotate only layout inference pixels, then restore source-page geometry."""
    original_predict_layout = layout_model.predict_layout
    current_page_id = {"value": None}
    diagnostics: list[dict] = []
    layout_model.orientation_diagnostics = diagnostics

    def rotated_predict_layout(conv_res: object, pages: Sequence[object]):
        saved = []
        for page in pages:
            if page._backend is None or not page._backend.is_valid():
                saved.append(None)
                continue
            original_image = page.get_image(scale=1.0)
            if original_image is None:
                saved.append(None)
                continue

            original_size = page.size.model_copy(deep=True)
            original_cache = page._image_cache.copy()
            osd_scale = min(3.0, max(1.0, 1800 / max(original_image.size)))
            osd_image = page.get_image(scale=osd_scale) or original_image
            rotation, confidence = _detect_rotation_clockwise(
                np.asarray(osd_image.convert("RGB"))
            )
            saved.append((original_size, original_cache, rotation))
            diagnostics.append({
                "reference_id": current_page_id["value"],
                "osd_rotation_clockwise": rotation,
                "osd_confidence": confidence,
                "minimum_osd_confidence": MINIMUM_OSD_CONFIDENCE,
                "source_size": list(original_image.size),
                "osd_size": list(osd_image.size),
            })
            if rotation == 0:
                page._image_cache.clear()
                page._image_cache.update(original_cache)
                continue

            inference_image = original_image.rotate(-rotation, expand=True)
            page.size.width, page.size.height = original_size.height, original_size.width
            page._image_cache.clear()
            page._image_cache[1.0] = inference_image

        try:
            predictions = original_predict_layout(conv_res, pages)
        finally:
            for page, state in zip(pages, saved):
                if state is None:
                    continue
                original_size, original_cache, _rotation = state
                page.size = original_size
                page._image_cache.clear()
                page._image_cache.update(original_cache)

        for prediction, state in zip(predictions, saved):
            if state is None:
                continue
            original_size, _original_cache, rotation = state
            for cluster in prediction.clusters:
                _map_bbox_to_source(
                    cluster.bbox, original_size.width, original_size.height, rotation
                )
                for child in cluster.children:
                    _map_bbox_to_source(
                        child.bbox, original_size.width, original_size.height, rotation
                    )
        return predictions

    layout_model.predict_layout = rotated_predict_layout

    def set_page_id(page_id: str) -> None:
        current_page_id["value"] = page_id

    return set_page_id
