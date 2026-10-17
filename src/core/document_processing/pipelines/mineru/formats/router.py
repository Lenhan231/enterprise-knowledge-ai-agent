"""Route MinerU inputs to their format-specific adapters."""

from __future__ import annotations

from typing import Any

from .csv.processor import process as process_csv
from .image.processor import process as process_image
from .office.processor import process as process_office
from .pdf.processor import process as process_pdf
from .text.processor import process as process_text


def process(runtime: Any, content: bytes, source_format: str, document: dict[str, Any]) -> dict[str, Any]:
    if source_format in {"txt", "md"}:
        return process_text(runtime, content, document)
    if source_format == "pdf":
        return process_pdf(runtime, content, document)
    if source_format in {"png", "jpg", "jpeg", "tif", "tiff"}:
        return process_image(runtime, content, source_format, document)
    if source_format == "csv":
        return process_csv(runtime, content, document)
    if source_format in {"docx", "pptx", "xlsx"}:
        return process_office(runtime, content, source_format, document)
    raise ValueError(f"MinerU does not support this format in Upload Test: .{source_format}")


def process_file(
    filename: str,
    content: bytes,
    metadata: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Keep the pipeline router interface used by DocumentProcessor."""
    from ..processor import MineruProcessor

    return MineruProcessor(config).process(
        content, None, {"content": content, "metadata": metadata},
    )
