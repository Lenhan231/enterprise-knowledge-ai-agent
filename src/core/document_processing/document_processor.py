"""Route supported documents through a selected parser pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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

    def process(self, filename: str, content: bytes, metadata: dict[str, Any]) -> dict[str, Any]:
        """Parse a source file into normalized ordered elements and structured tables."""
        suffix = Path(filename).suffix.lower()
        if suffix not in self.SUPPORTED:
            raise ValueError(f"Unsupported document format: {suffix or 'unknown'}")
        common = {**metadata, "filename": Path(filename).name, "format": suffix[1:].upper()}
        engine = self.config.get("parser_engine", "built_in")
        if engine not in {"built_in", "docling", "mineru", "pp-structurev3"}:
            raise ValueError(f"Unsupported parser pipeline: {engine}")
        processor_config = {**self.config, "parser_engine": engine}
        pipeline_router = {
            "built_in": process_built_in,
            "docling": process_docling,
            "mineru": process_mineru,
            "pp-structurev3": process_pp_structurev3,
        }[engine]
        result = pipeline_router(Path(filename).name, content, common, processor_config)
        elements = result.get("elements", [])
        tables = result.get("tables", [])
        if suffix in {".png", ".jpg", ".jpeg"}:
            for element in elements:
                (element.get("metadata") or {}).pop("page_number", None)
            for table in tables:
                table.pop("page_number", None)
                (table.get("metadata") or {}).pop("page_number", None)

        def normalize_table(table: dict[str, Any]) -> None:
            table["columns"] = [self._clean_inline_text(str(value or "")) for value in table.get("columns", [])]
            table["rows"] = [
                {self._clean_inline_text(str(key)): self._clean_value(value) for key, value in row.items()}
                for row in table.get("rows", []) if isinstance(row, dict)
            ]
            table_metadata = table.setdefault("metadata", {})
            table_metadata.update({key: value for key, value in common.items() if key not in table_metadata and key not in {"title", "uploaded_by"}})
            table_metadata.update({"pipeline_id": engine, "parser_engine": engine})
            parser = table_metadata.get("parser") or table_metadata.get("table_extraction_method")
            parser = parser or self._NATIVE_PARSERS.get(suffix, "native.table")
            table_metadata["parser"] = parser
            table_metadata.setdefault("text_extraction_method", parser)

        for table in tables:
            normalize_table(table)

        for element in elements:
            element_metadata = dict(element.get("metadata") or {})
            element_metadata.update({
                key: value for key, value in common.items()
                if key not in element_metadata and key not in {"title", "uploaded_by"}
            })
            element_metadata["pipeline_id"] = engine
            element_metadata["parser_engine"] = engine
            parser = element_metadata.get("parser") or element_metadata.get("text_extraction_method")
            parser = parser or self._NATIVE_PARSERS.get(suffix, "tesseract")
            element_metadata["parser"] = parser
            element_metadata.setdefault("text_extraction_method", parser)
            element_type = str(element_metadata.get("element_type") or element_metadata.get("layout_type") or "text").lower()
            element_metadata["element_type"] = element_type
            element_metadata.setdefault("layout_type", element_type)
            element["metadata"] = element_metadata

            if element_type == "table":
                table_ref = element.get("table_ref")
                table = element.get("table_data")
                if table is not None:
                    table_ref = len(tables)
                    tables.append(table)
                    normalize_table(table)
                    element.pop("table_data", None)
                    element["table_ref"] = table_ref
                elif isinstance(table_ref, int) and 0 <= table_ref < len(tables):
                    table = tables[table_ref]
                else:
                    continue
                element_metadata.setdefault("table_index", table.get("table_index", table_ref))
                continue

            text = self._clean_text(str(element.get("text") or ""))
            element["text"] = text
        result.setdefault("metadata", {}).update({
            "pipeline_id": engine,
            "parser_engine": engine,
            "filename": common["filename"],
            "format": common["format"],
            **{key: value for key, value in metadata.items() if key not in {"title", "uploaded_by"}},
        })
        result["elements"] = elements
        result["tables"] = tables
        return result

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
