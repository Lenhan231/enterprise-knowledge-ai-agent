"""Route visual pages to PP-StructureV3 and native files to format readers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.document_processing.readers.csv.digital_born.processor import CSVProcessor
from core.document_processing.readers.office.processor import OfficeProcessor
from core.document_processing.readers.text.digital_born.processor import TextProcessor
from core.document_processing.pipelines.pp_structurev3.processor import PPStructureV3Processor


def process_file(filename: str, content: bytes, metadata: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    document = {"content": content, "metadata": metadata}
    parser = PPStructureV3Processor(config)
    if suffix == ".pdf":
        return parser.process(content, None, document)
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        return parser.process_image(content, suffix, document)
    if suffix == ".csv":
        return CSVProcessor(config).process_file(content, metadata)
    if suffix in {".txt", ".md"}:
        return TextProcessor(config).process_file(content, metadata)
    return OfficeProcessor(config).process(suffix, content, metadata)
