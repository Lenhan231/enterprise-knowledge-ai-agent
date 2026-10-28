"""OCR embedded document images through the scanned-page pipeline."""

from __future__ import annotations

import hashlib
import logging
import tempfile
from typing import Any

from ..converters import get_converter

_log = logging.getLogger(__name__)


def process_embedded_images(
    *,
    result: Any,
    source_format: str,
    formats_to_scan: set[str],
    picture_item_type: type,
    pipeline_options: Any,
    processor_config: dict[str, Any],
    table_item_type: type,
    ocr_enabled: bool,
    docling_version: str | None,
) -> dict[int, dict[str, Any]]:
    """Extract selected document pictures and send only those through OCR."""
    if not ocr_enabled or source_format not in formats_to_scan:
        return {}

    from ..result_mapper import map_result

    picture_items: list[tuple[Any, int, bytes]] = []
    unique_images: dict[bytes, Any] = {}
    image_index = 0
    for item, _level in result.document.iterate_items():
        if not isinstance(item, picture_item_type):
            continue
        image = item.get_image(result.document)
        if image is None:
            continue
        normalized_image = image.convert("RGB")
        image_key = hashlib.sha256(
            f"{normalized_image.size}".encode() + normalized_image.tobytes()
        ).digest()
        if image_key in unique_images:
            normalized_image.close()
        else:
            unique_images[image_key] = normalized_image
        picture_items.append((item, image_index, image_key))
        image_index += 1

    unique_items = list(unique_images.items())
    if not unique_items:
        return {}

    image_outputs: dict[bytes, dict[str, Any]] = {}
    image_options = pipeline_options.model_copy(update={
        "do_ocr": True,
        "generate_page_images": False,
    })
    converter = get_converter(image_options)
    for batch_start in range(0, len(unique_items), 8):
        batch = unique_items[batch_start:batch_start + 8]
        try:
            images = [entry[1] for entry in batch]
            with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
                images[0].save(
                    temporary,
                    format="PDF",
                    save_all=True,
                    append_images=images[1:],
                    resolution=72,
                )
                temporary.flush()
                image_result = converter.convert(temporary.name)
            if "FAILURE" in str(image_result.status).upper():
                raise RuntimeError(str(image_result.status))
            image_output = map_result(
                image_result,
                processor_config,
                table_item_type,
                True,
                docling_version,
                "pdf",
                preserve_chart_items=True,
            )
            for page_index, (image_key, _image) in enumerate(batch, 1):
                image_outputs[image_key] = {
                    "image_size": list(_image.size),
                    "output": {
                        "elements": [
                            element for element in image_output["elements"]
                            if (element.get("metadata") or {}).get("page_number") == page_index
                        ],
                        "tables": [
                            table for table in image_output["tables"]
                            if table.get("page_number", (table.get("metadata") or {}).get("page_number")) == page_index
                        ],
                    },
                }
        except Exception as error:
            _log.warning(
                "Could not OCR embedded images %s-%s in %s: %s",
                batch_start,
                batch_start + len(batch) - 1,
                source_format,
                error,
            )
        finally:
            for _image_key, image in batch:
                image.close()

    return {
        id(item): {"image_index": image_index, **image_outputs[image_key]}
        for item, image_index, image_key in picture_items
        if image_key in image_outputs
    }
