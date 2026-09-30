"""Dispatch uploaded Office, text, image, and PDF files into one parse result."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .image_processor import ImageProcessor
from .office_processor import OfficeProcessor
from .pdf_processor import PDFProcessor
from .text_processor import TextProcessor


class DocumentProcessor:
    """Parse a source file; original bytes and persistence belong to app/storage layers."""

    SUPPORTED = {
        ".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md",
        ".png", ".jpg", ".jpeg", ".tif", ".tiff",
    }

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.chunking_strategy = self.config.get("chunking_strategy", "sentence")
        self.paddle_formula_recognition = bool(self.config.get("paddle_formula_recognition", False))
        self.paddle_layout = bool(self.config.get("paddle_layout", False) or self.paddle_formula_recognition)
        self.vision_captioning = bool(self.config.get("vision_captioning", False))
        if self.chunking_strategy not in {"fixed", "sentence", "semantic"}:
            raise ValueError("chunking_strategy must be 'fixed' or 'sentence'")
        self.chunk_size = int(self.config.get("chunk_size", 1100))
        self.chunk_overlap = int(self.config.get("chunk_overlap", 120))
        if self.chunk_size <= 0 or self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk size must be positive and overlap smaller than size")

    def process(self, filename: str, content: bytes, metadata: dict[str, Any]) -> dict[str, list[dict]]:
        suffix = Path(filename).suffix.lower()
        if suffix not in self.SUPPORTED:
            raise ValueError(f"Unsupported document format: {suffix or 'unknown'}")
        common = {**metadata, "filename": Path(filename).name, "format": suffix[1:].upper()}
        if suffix == ".pdf":
            result = PDFProcessor({
                "paddle_layout": self.paddle_layout,
                "paddle_formula_recognition": self.paddle_formula_recognition,
                "vision_captioning": self.vision_captioning,
                "ocr_fallback": True,
                "ocr_language": "vie+eng",
                "tesseract_psm": self.config.get("tesseract_psm", 11),
                "tesseract_table_psm": self.config.get("tesseract_table_psm", 3),
                "ocr_render_scale": self.config.get("ocr_render_scale", 1.5),
                "ocr_table_render_scale": self.config.get("ocr_table_render_scale", 2.5),
                "extract_tables": True,
                "chunking_strategy": self.chunking_strategy,
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
            }).process({"content": content, "metadata": common})
        elif suffix in {".txt", ".md"}:
            result = TextProcessor(self.config).process_file(content, common)
        elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            result = ImageProcessor(self.config).process(suffix, content, common)
        else:
            result = OfficeProcessor(self.config).process(suffix, content, common)
        for index, chunk in enumerate(result["chunks"]):
            chunk["metadata"].update({
                key: value for key, value in common.items()
                if key not in chunk["metadata"] and key not in {"title", "uploaded_by"}
            })
            chunk["metadata"]["chunk_index"] = index
        for table in result["tables"]:
            table.setdefault("metadata", {}).update({key: value for key, value in common.items() if key not in table["metadata"]})
        return result
