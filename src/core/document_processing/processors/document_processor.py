"""Dispatch uploaded Office, text, image, and PDF files into one parse result."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .image.processor import ImageProcessor
from .office.processor import OfficeProcessor
from .pdf.processor import PDFProcessor
from .text.processor import TextProcessor
from core.chunking.text_chunker import ChunkingConfig


class DocumentProcessor:
    """Parse a source file; original bytes and persistence belong to app/storage layers."""

    SUPPORTED = {
        ".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md",
        ".png", ".jpg", ".jpeg", ".tif", ".tiff",
    }

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.chunking = ChunkingConfig.from_config(self.config)

    def process(self, filename: str, content: bytes, metadata: dict[str, Any]) -> dict[str, list[dict]]:
        suffix = Path(filename).suffix.lower()
        if suffix not in self.SUPPORTED:
            raise ValueError(f"Unsupported document format: {suffix or 'unknown'}")
        common = {**metadata, "filename": Path(filename).name, "format": suffix[1:].upper()}
        processor_config = {**self.config, "chunking": self.chunking}
        if suffix == ".pdf":
            result = PDFProcessor(processor_config).process({"content": content, "metadata": common})
        elif suffix in {".txt", ".md"}:
            result = TextProcessor(processor_config).process_file(content, common)
        elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            result = ImageProcessor(processor_config).process(suffix, content, common)
        else:
            result = OfficeProcessor(processor_config).process(suffix, content, common)
        for index, chunk in enumerate(result["chunks"]):
            chunk["metadata"].update({
                key: value for key, value in common.items()
                if key not in chunk["metadata"] and key not in {"title", "uploaded_by"}
            })
            chunk["metadata"]["chunk_index"] = index
            chunk["metadata"]["actual_char_count"] = len(chunk["text"])
        for table in result["tables"]:
            table.setdefault("metadata", {}).update({key: value for key, value in common.items() if key not in table["metadata"]})
        return result
