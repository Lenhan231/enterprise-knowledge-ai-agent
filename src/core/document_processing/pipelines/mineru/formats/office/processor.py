"""Parse Office files and OCR MinerU's own extracted image assets."""

from __future__ import annotations

import logging
import tempfile
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from ..image.processor import process as process_image

logger = logging.getLogger(__name__)
_OCR_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def process(runtime: Any, content: bytes, source_format: str, document: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="upload-test-mineru-office-") as temporary_dir:
        work_dir = Path(temporary_dir)
        input_path = work_dir / f"input.{source_format}"
        output_path = work_dir / "mineru-output.zip"
        input_path.write_bytes(content)
        runtime.run([
            "parse", str(input_path), "--output", str(output_path),
            "--tier", "flash", "--format", "zip",
        ])

        try:
            with zipfile.ZipFile(output_path) as output:
                markdown_files = [name for name in output.namelist() if name.lower().endswith(".md")]
                if len(markdown_files) != 1:
                    raise RuntimeError(
                        f"Local MinerU produced {len(markdown_files)} Markdown files; expected one"
                    )
                markdown = output.read(markdown_files[0]).decode("utf-8")
                image_assets = [
                    (name, output.read(name))
                    for name in output.namelist()
                    if "images" in PurePosixPath(name).parts
                    and Path(name).suffix.lower() in _OCR_IMAGE_SUFFIXES
                ]
        except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as error:
            raise RuntimeError("Local MinerU produced an unreadable Office result archive") from error

    source_metadata = document.get("metadata", {})
    image_chunks_by_asset: dict[str, list[dict[str, Any]]] = {}
    for image_index, (asset_path, image_bytes) in enumerate(image_assets):
        suffix = Path(asset_path).suffix.lower().lstrip(".")
        image_document = {
            "content": image_bytes,
            "metadata": {
                **source_metadata,
                "format": suffix,
                "source_part": asset_path,
                "image_index": image_index,
            },
        }
        try:
            image_result = process_image(runtime, image_bytes, suffix, image_document)
        except Exception as error:
            logger.warning(
                "Could not OCR MinerU Office image asset %s (%s)",
                asset_path, type(error).__name__,
            )
            continue
        asset_chunks = []
        for element in image_result.get("elements", []):
            metadata = element.setdefault("metadata", {})
            metadata.pop("page_number", None)
            metadata.pop("bbox", None)
            metadata.pop("bbox_coordinate_system", None)
            metadata.update({
                **source_metadata,
                "source_part": asset_path,
                "image_index": image_index,
                "element_type": "image",
                "layout_type": "image",
                "parser": "mineru",
                "mineru_tier": "basic",
                "text_extraction_method": "mineru.local.basic",
            })
            asset_chunks.append(element)
        normalized_asset = PurePosixPath(asset_path).as_posix()
        image_chunks_by_asset[normalized_asset] = asset_chunks
    return runtime.result_mapper.markdown_result(
        markdown,
        {**document, "image_chunks_by_asset": image_chunks_by_asset},
    )
