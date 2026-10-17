"""Dispatch uploaded Office, text, image, and PDF files into one parse result."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .chunking.chunk_builder import build_text_chunks
from .processors.csv.digital_born.processor import CSVProcessor
from .processors.office.processor import OfficeProcessor
from .processors.pdf.processor import PDFProcessor
from .processors.text.digital_born.processor import TextProcessor
from .scanned.processor import ScannedImageProcessor
from core.document_processing.chunking.config import ChunkingConfig


class DocumentProcessor:
    """Parse a source file; original bytes and persistence belong to app/storage layers."""

    SUPPORTED = {
        ".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt", ".md",
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
        elif suffix == ".csv":
            result = CSVProcessor(processor_config).process_file(content, common)
        elif suffix in {".txt", ".md"}:
            result = TextProcessor(processor_config).process_file(content, common)
        elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            result = ScannedImageProcessor(processor_config).process(suffix, content, common)
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

    def prepare_upload_test_output(
        self, result: dict[str, Any], source_metadata: dict[str, Any], parser_engine: str,
    ) -> dict[str, Any]:
        """Apply one cleanup, metadata, and chunking path to every Upload Test parser."""
        groups: list[dict[str, Any]] = []
        group_keys: list[tuple[Any, ...]] = []
        for parser_chunk in result.get("chunks", []):
            metadata = dict(parser_chunk.get("metadata") or {})
            text = self._clean_text(str(parser_chunk.get("text") or ""))
            if not text:
                continue
            section_path = metadata.get("section_path")
            if not isinstance(section_path, list):
                title = metadata.get("section_title") or metadata.get("title")
                section_path = [title] if title else []
            section_path = [self._clean_inline_text(str(item)) for item in section_path if str(item).strip()]
            section_title = metadata.get("section_title") or (section_path[-1] if section_path else None)
            section_title = self._clean_inline_text(str(section_title)) if section_title else None
            element_type = str(
                metadata.get("element_type") or metadata.get("layout_type") or "text"
            ).lower()
            normalized = {
                **source_metadata,
                "filename": metadata.get("filename"),
                "format": metadata.get("format", "PDF"),
                "parser_engine": parser_engine,
                "page_number": int(metadata.get("page_number") or 1),
                "element_type": element_type,
                "layout_type": element_type,
                "section_path": section_path,
                "section_title": section_title,
                "bbox": metadata.get("bbox"),
                "bbox_coordinate_system": metadata.get("bbox_coordinate_system", "pdf_point"),
                "text_extraction_method": metadata.get(
                    "text_extraction_method", parser_engine,
                ),
                "ocr": metadata.get("ocr"),
                "ocr_diagnostics": metadata.get("ocr_diagnostics", []),
                "parser_details": {
                    key: value for key, value in metadata.items()
                    if key not in {
                        "filename", "format", "source_type", "source_sha256",
                        "page_number", "element_type", "layout_type", "section_path",
                        "section_title", "title", "bbox", "bbox_coordinate_system",
                        "text_extraction_method", "ocr", "ocr_diagnostics",
                        "chunk_index", "chunk_strategy", "chunk_size_chars",
                        "chunk_overlap_chars", "actual_char_count",
                    }
                },
            }
            if metadata.get("table_index") is not None:
                normalized["table_index"] = metadata["table_index"]
            if metadata.get("heading_level") is not None:
                normalized["heading_level"] = metadata["heading_level"]
            key = (
                normalized["page_number"], tuple(section_path), element_type,
                metadata.get("table_index"),
            )
            if groups and group_keys[-1] == key:
                groups[-1]["text"] = self._join_without_overlap(
                    groups[-1]["text"], text,
                    self.chunking.overlap if self.chunking.strategy == "fixed" else 0,
                )
                details = groups[-1]["metadata"]["parser_details"]
                for name, value in normalized["parser_details"].items():
                    if name not in details:
                        details[name] = value
                    elif details[name] != value:
                        existing = details[name] if isinstance(details[name], list) else [details[name]]
                        if value not in existing:
                            details[name] = [*existing, value]
                if normalized.get("bbox") and groups[-1]["metadata"].get("bbox"):
                    boxes = (groups[-1]["metadata"]["bbox"], normalized["bbox"])
                    groups[-1]["metadata"]["bbox"] = [
                        min(box[0] for box in boxes), min(box[1] for box in boxes),
                        max(box[2] for box in boxes), max(box[3] for box in boxes),
                    ]
            else:
                groups.append({"text": text, "metadata": normalized})
                group_keys.append(key)

        chunks = []
        for group in groups:
            chunks.extend(build_text_chunks(group["text"], group["metadata"], self.chunking))
        for index, chunk in enumerate(chunks):
            chunk["metadata"].update({
                "chunk_index": index,
                "chunk_strategy": self.chunking.strategy,
                "chunk_size_chars": self.chunking.size,
                "chunk_overlap_chars": self.chunking.overlap if self.chunking.strategy == "fixed" else 0,
                "actual_char_count": len(chunk["text"]),
            })

        tables = result.get("tables", [])
        for table_index, table in enumerate(tables):
            original = dict(table.get("metadata") or {})
            table["columns"] = [
                self._clean_inline_text(str(column or "")) for column in table.get("columns", [])
            ]
            table["rows"] = [
                {
                    self._clean_inline_text(str(column)): (
                        self._clean_value(value)
                    )
                    for column, value in row.items()
                }
                for row in table.get("rows", []) if isinstance(row, dict)
            ]
            table["context"] = self._clean_value(table.get("context") or {})
            table["metadata"] = {
                **source_metadata,
                "filename": original.get("filename", source_metadata.get("filename")),
                "format": original.get("format", "PDF"),
                "parser_engine": parser_engine,
                "page_number": int(table.get("page_number") or original.get("page_number") or 1),
                "element_type": "table",
                "layout_type": "table",
                "bbox": original.get("bbox"),
                "bbox_coordinate_system": original.get("bbox_coordinate_system", "pdf_point"),
                "table_index": int(table.get("table_index", table_index)),
                "ocr": original.get("ocr"),
                "table_extraction_method": original.get("table_extraction_method"),
                "table_detection_strategy": original.get("table_detection_strategy"),
                "parser_details": original,
            }
        return {**result, "chunks": chunks, "tables": tables}

    @staticmethod
    def _clean_text(text: str) -> str:
        lines = [" ".join(line.replace("\u00a0", " ").replace("\x00", " ").split()) for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        cleaned = "\n".join(lines)
        while "\n\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n\n", "\n\n")
        return cleaned.strip()

    @classmethod
    def _clean_inline_text(cls, text: str) -> str:
        return " ".join(cls._clean_text(text).split())

    @classmethod
    def _clean_value(cls, value: Any) -> Any:
        if isinstance(value, str):
            return cls._clean_inline_text(value)
        if isinstance(value, list):
            return [cls._clean_value(item) for item in value]
        if isinstance(value, dict):
            return {
                cls._clean_inline_text(str(key)): cls._clean_value(item)
                for key, item in value.items()
            }
        return value

    @staticmethod
    def _join_without_overlap(left: str, right: str, max_overlap: int) -> str:
        overlap_limit = min(max_overlap, len(left), len(right))
        for overlap in range(overlap_limit, 0, -1):
            if left[-overlap:] == right[:overlap]:
                return left + right[overlap:]
        return f"{left}\n{right}"
