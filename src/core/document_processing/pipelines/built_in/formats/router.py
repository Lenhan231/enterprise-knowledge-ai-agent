"""Route Built-in inputs to native format readers or its scanned parsers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.document_processing.readers.csv.digital_born.processor import CSVProcessor
from core.document_processing.readers.image.processor import ScannedImageProcessor
from core.document_processing.readers.office.processor import OfficeProcessor
from core.document_processing.readers.text.digital_born.processor import TextProcessor
from core.document_processing.pipelines.built_in.processor import BuiltInProcessor


def process_file(filename: str, content: bytes, metadata: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    document = {"content": content, "metadata": metadata}
    if suffix == ".pdf":
        return BuiltInProcessor(config).process(document)
    if suffix == ".csv":
        return CSVProcessor(config).process_file(content, metadata)
    if suffix in {".txt", ".md"}:
        return TextProcessor(config).process_file(content, metadata)
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        return ScannedImageProcessor(config).process(suffix, content, metadata)
    return OfficeProcessor(config).process(suffix, content, metadata)
