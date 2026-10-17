"""Route supported documents through a selected parser pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .chunking.router import build_chunks
from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.pipelines.built_in.formats.router import process_file as process_built_in
from core.document_processing.pipelines.docling.formats.router import process_file as process_docling
from core.document_processing.pipelines.mineru.formats.router import process_file as process_mineru
from core.document_processing.pipelines.pp_structurev3.formats.router import process_file as process_pp_structurev3

SUPPORTED_FORMATS = frozenset({
    ".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff",
})

class DocumentProcessor:
    """Parse a source file; original bytes and persistence belong to app/storage layers."""

    SUPPORTED = SUPPORTED_FORMATS
    _NATIVE_PARSERS = {
        ".docx": "python-stdlib-docx-xml",
        ".pptx": "python-stdlib-pptx-xml",
        ".xlsx": "python-stdlib-xlsx-xml",
        ".csv": "python-csv",
        ".txt": "python-text",
        ".md": "python-markdown-text",
    }

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.chunking = ChunkingConfig.from_config(self.config)

    def process(self, filename: str, content: bytes, metadata: dict[str, Any]) -> dict[str, list[dict]]:
        suffix = Path(filename).suffix.lower()
        if suffix not in self.SUPPORTED:
            raise ValueError(f"Unsupported document format: {suffix or 'unknown'}")
        common = {**metadata, "filename": Path(filename).name, "format": suffix[1:].upper()}
        engine = self.config.get("parser_engine", "built_in")
        if engine not in {"built_in", "docling", "mineru", "pp-structurev3"}:
            raise ValueError(f"Unsupported parser pipeline: {engine}")
        processor_config = {**self.config, "chunking": self.chunking, "parser_engine": engine}
        pipeline_router = {
            "built_in": process_built_in,
            "docling": process_docling,
            "mineru": process_mineru,
            "pp-structurev3": process_pp_structurev3,
        }[engine]
        result = pipeline_router(Path(filename).name, content, common, processor_config)
        if suffix in {".png", ".jpg", ".jpeg"}:
            for chunk in result.get("chunks", []):
                (chunk.get("metadata") or {}).pop("page_number", None)
            for table in result.get("tables", []):
                table.pop("page_number", None)
                (table.get("metadata") or {}).pop("page_number", None)
        cleaned_chunks = []
        for chunk in result.get("chunks", []):
            chunk["text"] = self._clean_text(str(chunk.get("text") or ""))
            if not chunk["text"]:
                continue
            chunk["metadata"].update({
                key: value for key, value in common.items()
                if key not in chunk["metadata"] and key not in {"title", "uploaded_by"}
            })
            chunk_metadata = chunk["metadata"]
            chunk_metadata["pipeline_id"] = engine
            chunk_metadata["parser_engine"] = engine
            parser = chunk_metadata.get("parser") or chunk_metadata.get("text_extraction_method")
            parser = parser or self._NATIVE_PARSERS.get(suffix, "tesseract")
            chunk_metadata["parser"] = parser
            chunk_metadata.setdefault("text_extraction_method", parser)
            cleaned_chunks.append(chunk)
        cleaned_chunks = self._merge_short_text_chunks(cleaned_chunks)
        result["chunks"] = cleaned_chunks
        for index, chunk in enumerate(cleaned_chunks):
            chunk["metadata"]["chunk_index"] = index
            chunk["metadata"]["actual_char_count"] = len(chunk["text"])
        for table in result.get("tables", []):
            table["columns"] = [self._clean_inline_text(str(value or "")) for value in table.get("columns", [])]
            table["rows"] = [
                {self._clean_inline_text(str(key)): self._clean_value(value) for key, value in row.items()}
                for row in table.get("rows", []) if isinstance(row, dict)
            ]
            table_metadata = table.setdefault("metadata", {})
            table_metadata.update({key: value for key, value in common.items() if key not in table_metadata})
            table_metadata.update({"pipeline_id": engine, "parser_engine": engine})
            table_parser = table_metadata.get("parser") or table_metadata.get("table_extraction_method")
            table_parser = table_parser or self._NATIVE_PARSERS.get(suffix, "native.table")
            table_metadata["parser"] = table_parser
            table_metadata.setdefault("text_extraction_method", table_parser)
        result.setdefault("metadata", {}).update({
            "pipeline_id": engine,
            "parser_engine": engine,
            "filename": common["filename"],
            "format": common["format"],
            **{key: value for key, value in metadata.items() if key not in {"title", "uploaded_by"}},
        })
        return result

    def _merge_short_text_chunks(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fold heading-only and tiny prose chunks into nearby text in the same section."""
        merged: list[dict[str, Any]] = []

        def location(metadata: dict[str, Any]) -> tuple[Any, ...]:
            section_path = metadata.get("section_path")
            section = tuple(section_path) if isinstance(section_path, list) else (
                str(metadata.get("section_title") or ""),
            )
            return (metadata.get("page_number"), metadata.get("sheet_name"), metadata.get("slide_number"), section)

        def join_text(left: str, right: str, metadata: dict[str, Any]) -> str:
            title = str(metadata.get("section_title") or "").strip()
            prefix = f"Section: {title}" if title else ""
            pieces = []
            for value in (left.strip(), right.strip()):
                if prefix and value.startswith(prefix + "\n"):
                    value = value[len(prefix):].lstrip("\n")
                if value:
                    pieces.append(value)
            body = "\n\n".join(pieces)
            return f"{prefix}\n{body}" if prefix and body else body

        for index, chunk in enumerate(chunks):
            text = str(chunk.get("text") or "").strip()
            metadata = chunk.get("metadata") or {}
            element = str(metadata.get("element_type") or metadata.get("layout_type") or "text").lower()
            if index + 1 < len(chunks):
                next_chunk = chunks[index + 1]
                next_metadata = next_chunk.get("metadata") or {}
                title = str(metadata.get("section_title") or "").strip()
                heading_text = text.splitlines()[0].strip().strip("#* ") if text else ""
                if (
                    title and location(metadata) == location(next_metadata)
                    and heading_text == title
                    and str(next_metadata.get("section_title") or "").strip() == title
                ):
                    continue  # The following chunk carries this heading in text and metadata.
            if element in {"text", "title"} and 0 < len(text) < 80:
                if index + 1 < len(chunks):
                    following = chunks[index + 1]
                    following_metadata = following.get("metadata") or {}
                    following_type = str(
                        following_metadata.get("element_type") or following_metadata.get("layout_type") or "text"
                    ).lower()
                    if (
                        following_type == "text"
                        and location(metadata) == location(following_metadata)
                        and len(text) + len(str(following.get("text") or "")) + 2 <= self.chunking.size
                    ):
                        following["text"] = join_text(text, str(following.get("text") or ""), following_metadata)
                        continue
                if merged:
                    previous = merged[-1]
                    previous_metadata = previous.get("metadata") or {}
                    previous_type = str(
                        previous_metadata.get("element_type") or previous_metadata.get("layout_type") or "text"
                    ).lower()
                    previous_text = str(previous.get("text") or "")
                    if (
                        previous_type == "text"
                        and location(metadata) == location(previous_metadata)
                        and len(previous_text) + len(text) + 2 <= self.chunking.size
                    ):
                        previous["text"] = join_text(previous_text, text, previous_metadata)
                        continue
            merged.append(chunk)
        for index, chunk in enumerate(merged):
            chunk.setdefault("metadata", {}).update({
                "chunk_index": index,
                "actual_char_count": len(str(chunk.get("text") or "")),
            })
        return merged

    def prepare_upload_test_output(
        self, result: dict[str, Any], source_metadata: dict[str, Any], parser_engine: str,
    ) -> dict[str, Any]:
        """Apply one cleanup, metadata, and chunking path to every Upload Test parser."""
        result_metadata = result.get("metadata") or {}
        output_source = {**source_metadata, **{
            key: result_metadata[key] for key in ("filename", "format")
            if result_metadata.get(key) is not None
        }}
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
                **output_source,
                "filename": metadata.get("filename", output_source.get("filename")),
                "format": metadata.get("format", output_source.get("format")),
                "parser_engine": parser_engine,
                "pipeline_id": parser_engine,
                "element_type": element_type,
                "layout_type": element_type,
                "section_path": section_path,
                "section_title": section_title,
                "bbox": metadata.get("bbox"),
                "text_extraction_method": metadata.get("text_extraction_method", metadata.get("parser", parser_engine)),
                "parser": metadata.get("parser", metadata.get("text_extraction_method", parser_engine)),
                "ocr": metadata.get("ocr"),
                "ocr_diagnostics": metadata.get("ocr_diagnostics", []),
                "parser_details": {
                    key: value for key, value in metadata.items()
                    if key not in {
                        "filename", "format", "source_type", "source_sha256",
                        "page_number", "element_type", "layout_type", "section_path",
                        "section_title", "title", "bbox", "bbox_coordinate_system",
                        "text_extraction_method", "ocr", "ocr_diagnostics",
                        "parser", "parser_engine", "pipeline_id",
                        "chunk_index", "chunk_strategy", "chunk_size_chars",
                        "chunk_overlap_chars", "actual_char_count",
                    }
                },
            }
            if metadata.get("page_number") is not None:
                normalized["page_number"] = int(metadata["page_number"])
            if metadata.get("bbox") is not None:
                normalized["bbox"] = metadata["bbox"]
                normalized["bbox_coordinate_system"] = metadata.get("bbox_coordinate_system")
            for location_key in ("sheet_name", "slide_number", "paragraph_index", "source_part"):
                if metadata.get(location_key) is not None:
                    normalized[location_key] = metadata[location_key]
            if metadata.get("table_index") is not None:
                normalized["table_index"] = metadata["table_index"]
            if metadata.get("heading_level") is not None:
                normalized["heading_level"] = metadata["heading_level"]
            key = tuple(
                normalized.get(name) for name in (
                    "page_number", "sheet_name", "slide_number", "paragraph_index",
                )
            ) + (tuple(section_path), element_type, metadata.get("table_index"))
            if element_type == "table":
                # Table parser chunks already came from the row-aware table strategy.
                # Keep each fragment separate so the shared text splitter cannot flatten it.
                key += ("table_fragment", metadata.get("chunk_index", len(groups)))
            if groups and group_keys[-1] == key:
                if element_type != "table" and section_title:
                    prefix = f"Section: {section_title}\n"
                    if text.startswith(prefix):
                        text = text[len(prefix):]
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
            if group["metadata"].get("layout_type") == "table":
                chunk = {"text": group["text"], "metadata": dict(group["metadata"])}
                chunk["metadata"].update({
                    "chunk_index": len(chunks),
                    "chunk_strategy": self.chunking.strategy,
                    "chunk_size_chars": self.chunking.size,
                    "chunk_overlap_chars": 0,
                    "actual_char_count": len(chunk["text"]),
                })
                chunks.append(chunk)
                continue
            chunks.extend(build_chunks(
                group["text"], self.chunking, kind="text", metadata=group["metadata"],
            ))
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
                **output_source,
                "filename": original.get("filename", output_source.get("filename")),
                "format": original.get("format", output_source.get("format")),
                "parser_engine": parser_engine,
                "pipeline_id": parser_engine,
                "element_type": "table",
                "layout_type": "table",
                "table_index": int(table.get("table_index", table_index)),
                "parser": original.get("parser", original.get("table_extraction_method", parser_engine)),
                "text_extraction_method": original.get("text_extraction_method", original.get("parser", parser_engine)),
                "ocr": original.get("ocr"),
                "table_extraction_method": original.get("table_extraction_method"),
                "table_detection_strategy": original.get("table_detection_strategy"),
                "parser_details": {
                    key: value for key, value in original.items()
                    if key not in {
                        "filename", "format", "source_type", "source_sha256",
                        "parser", "parser_engine", "pipeline_id",
                        "page_number", "table_index", "bbox", "bbox_coordinate_system",
                        "sheet_name", "slide_number", "paragraph_index", "source_part",
                        "element_type", "layout_type",
                    }
                },
            }
            page_number = table.get("page_number", original.get("page_number"))
            if page_number is not None:
                table["metadata"]["page_number"] = int(page_number)
            if original.get("bbox") is not None:
                table["metadata"]["bbox"] = original["bbox"]
                table["metadata"]["bbox_coordinate_system"] = original.get("bbox_coordinate_system")
            for location_key in ("sheet_name", "slide_number", "paragraph_index", "source_part"):
                if original.get(location_key) is not None:
                    table["metadata"][location_key] = original[location_key]
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
