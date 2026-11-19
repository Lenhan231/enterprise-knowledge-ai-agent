"""Parse supported documents with Docling and normalize the results."""

from __future__ import annotations

from pathlib import Path
import base64
import json
import logging
import os
import time
from typing import Any
import re

from document_processing.diagnostics import component_errors, document_log_context
from document_processing.element_taxonomy import normalize_element_label
from document_processing.formats import (
    IMAGE_FORMATS, LEGACY_OFFICE_FORMATS, NORMALIZED_RASTER_FORMATS, SUPPORTED_FORMATS,
)
from document_processing.image_input import normalize_image, render_svg, render_webp
from document_processing.invoice.ocr_cache import invoice_docling_cache
from document_processing.legacy_office import convert_legacy_office

_INVOICE_EXTRACTION_CONFIG_KEYS = frozenset({
    "invoice_provider",
    "invoice_worker_python",
    "gemini_invoice_model",
    "groq_invoice_model",
    "invoice_model",
    "invoice_model_revision",
    "invoice_adapter",
    "invoice_adapter_revision",
})
_LOGGER = logging.getLogger(__name__)
_DOCUMENT_ONLY_FORMATS = (LEGACY_OFFICE_FORMATS.keys() | NORMALIZED_RASTER_FORMATS.keys()) - {".webp"}


class DocumentProcessor:
    """Parse a source file; original bytes and persistence belong to app/storage layers."""

    SUPPORTED = SUPPORTED_FORMATS
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def process(
        self,
        filename: str,
        content: bytes,
        metadata: dict[str, Any],
        *,
        invoice_docling_lock=None,
        on_invoice_docling_lock_wait=None,
    ) -> dict[str, Any]:
        """Parse a source file into normalized ordered elements and structured tables."""
        suffix = Path(filename).suffix.lower()
        intent = str(self.config.get("intent", "document")).strip().lower()
        log_context = document_log_context(metadata, source_format=suffix.lstrip("."), intent=intent)
        with component_errors(_LOGGER, "document_input_validation", **log_context):
            if suffix not in self.SUPPORTED:
                raise ValueError(f"Unsupported document format: {suffix or 'unknown'}")
            if intent not in {"document", "invoice"}:
                raise ValueError(f"Unsupported document intent: {intent}")
            if intent != "document" and suffix in _DOCUMENT_ONLY_FORMATS:
                raise ValueError(f"{suffix} is supported for document processing only")
        common = {
            **metadata,
            "filename": Path(filename).name,
            "format": suffix[1:].upper(),
            "intent": intent,
        }
        remote_url = os.getenv("DOCUMENT_PROCESSING_URL", "").strip()
        if remote_url:
            from core.services import client

            timeout_env = (
                "DOCUMENT_PROCESSING_INVOICE_TIMEOUT_SECONDS"
                if intent == "invoice" else "DOCUMENT_PROCESSING_TIMEOUT_SECONDS"
            )
            default_timeout = "600"
            if intent == "invoice":
                default_timeout = "1200"
            with component_errors(_LOGGER, "remote_parser_request", **log_context):
                result = client.post(
                    remote_url,
                    "/parse",
                    {
                        "filename": Path(filename).name,
                        "content": base64.b64encode(content).decode("ascii"),
                        "metadata": common,
                        "config": self.config,
                    },
                    timeout=int(os.getenv(timeout_env, default_timeout)),
                )
            previews = result.get("page_previews")
            if isinstance(previews, dict):
                result["page_previews"] = {
                    page: base64.b64decode(value, validate=True)
                    if isinstance(value, str) else value
                    for page, value in previews.items()
                }
            return result
        parser_suffix = suffix
        if intent == "invoice":
            provider = str(
                self.config.get("invoice_provider")
                or os.environ.get("DOCUMENT_PROCESSING_INVOICE_PROVIDER")
                or "modal"
            ).strip().lower()
            with component_errors(_LOGGER, "invoice_provider_validation", **log_context):
                if provider not in {"gemini", "groq", "modal", "local"}:
                    raise ValueError(f"Unsupported invoice extraction provider: {provider}")
            from document_processing.invoice.text_processor import InvoiceTextProcessor

            extraction_processor = InvoiceTextProcessor(self.config)
            engine = "docling_qwen_invoice_text"

            processor_config = {**self.config, "parser_engine": "docling", "intent": "document"}
            parser_content = content
            if suffix in {".svg", ".webp"}:
                with component_errors(_LOGGER, "image_normalization", **log_context):
                    parser_content = render_svg(content) if suffix == ".svg" else render_webp(content)
                    parser_suffix = ".png"
            parser_metadata = {**common, "format": parser_suffix[1:].upper()}
            cache_config = {
                key: value for key, value in processor_config.items()
                if key not in _INVOICE_EXTRACTION_CONFIG_KEYS
            }
            cache_key = invoice_docling_cache.key(parser_content, suffix[1:], cache_config)
            cache_started = time.perf_counter()
            result = invoice_docling_cache.get(cache_key)
            cache_lookup_ms = (time.perf_counter() - cache_started) * 1000
            cache_hit = result is not None

            def parse_and_cache():
                with component_errors(_LOGGER, "docling_import", **log_context):
                    from document_processing.docling_adapter.processor import DoclingProcessor

                docling_started = time.perf_counter()
                parsed = DoclingProcessor(processor_config).process(
                    parser_content, None, {"content": parser_content, "metadata": parser_metadata}
                )
                _LOGGER.info(
                    "DOCUMENT_PROCESS_COMPONENT %s",
                    json.dumps({
                        "invoice_id": metadata.get("invoice_id"),
                        "component": "invoice_docling_result",
                        "elapsed_ms": round((time.perf_counter() - docling_started) * 1000, 2),
                    }, separators=(",", ":")),
                )
                cache_started = time.perf_counter()
                cache_stored = invoice_docling_cache.put(cache_key, parsed)
                _LOGGER.info(
                    "DOCUMENT_PROCESS_COMPONENT %s",
                    json.dumps({
                        "invoice_id": metadata.get("invoice_id"),
                        "component": "invoice_docling_cache_store",
                        "cache_stored": cache_stored,
                        "elapsed_ms": round((time.perf_counter() - cache_started) * 1000, 2),
                    }, separators=(",", ":")),
                )
                return parsed

            if result is None and invoice_docling_lock is not None:
                lock_started = time.perf_counter()
                invoice_docling_lock.acquire()
                lock_wait_ms = (time.perf_counter() - lock_started) * 1000
                try:
                    if on_invoice_docling_lock_wait is not None:
                        on_invoice_docling_lock_wait(lock_wait_ms)
                    # Another request may have populated the cache while this
                    # request waited for the shared Docling pipeline.
                    cache_started = time.perf_counter()
                    result = invoice_docling_cache.get(cache_key)
                    cache_lookup_ms += (time.perf_counter() - cache_started) * 1000
                    cache_hit = result is not None
                    if result is None:
                        result = parse_and_cache()
                        cache_hit = False
                finally:
                    invoice_docling_lock.release()
            elif result is None:
                result = parse_and_cache()
                cache_hit = False

            _LOGGER.info(
                "DOCUMENT_PROCESS_COMPONENT %s",
                json.dumps({
                    "invoice_id": metadata.get("invoice_id"),
                    "component": "invoice_docling_cache_lookup",
                    "cache_hit": cache_hit,
                    "elapsed_ms": round(cache_lookup_ms, 2),
                }, separators=(",", ":")),
            )
            extraction_started = time.perf_counter()
            with component_errors(_LOGGER, "invoice_extraction_result", **log_context, provider=provider):
                extraction = extraction_processor.process(
                    result.get("elements", []), result.get("tables", []),
                    reference_id=metadata.get("invoice_id"),
                )
            _LOGGER.info(
                "DOCUMENT_PROCESS_COMPONENT %s",
                json.dumps({
                    "invoice_id": metadata.get("invoice_id"),
                    "component": "invoice_extraction_result",
                    "elapsed_ms": round((time.perf_counter() - extraction_started) * 1000, 2),
                }, separators=(",", ":")),
            )
            result["invoice_extraction"] = extraction
            result.setdefault("metadata", {}).update({
                "pipeline_id": engine,
                "parser_engine": "docling",
                "invoice_model": extraction["model"],
                "invoice_model_revision": extraction["revision"],
                "invoice_schema_version": extraction["schema_version"],
                "invoice_review_required": True,
            })
        else:
            engine = str(self.config.get("parser_engine", "docling"))
            if engine != "docling":
                raise ValueError(f"Unsupported parser pipeline: {engine}")
            processor_config = {**self.config, "parser_engine": engine}
            parser_content = content
            if suffix in LEGACY_OFFICE_FORMATS:
                with component_errors(_LOGGER, "legacy_office_conversion", **log_context):
                    parser_content, parser_suffix = convert_legacy_office(content, suffix)
            elif suffix in IMAGE_FORMATS:
                with component_errors(_LOGGER, "image_normalization", **log_context):
                    parser_content, parser_suffix = normalize_image(content, suffix)
            parser_metadata = {**common, "format": parser_suffix[1:].upper()}
            with component_errors(_LOGGER, "docling_import", **log_context):
                from document_processing.docling_adapter.processor import DoclingProcessor

            result = DoclingProcessor(processor_config).process(
                parser_content, None, {"content": parser_content, "metadata": parser_metadata}
            )
        normalization_started = time.perf_counter()
        elements = result.get("elements", [])
        tables = result.get("tables", [])
        if suffix in IMAGE_FORMATS and parser_suffix not in {".tif", ".tiff"}:
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
            if parser_suffix != suffix:
                table_metadata["format"] = common["format"]
            table_metadata.update({key: value for key, value in common.items() if key not in table_metadata and key not in {"title", "uploaded_by"}})
            table_metadata.update({"pipeline_id": engine, "parser_engine": "docling" if intent == "invoice" else engine})
            table_metadata.update({"element_type": "table", "layout_type": "table"})
            parser = table_metadata.get("parser") or table_metadata.get("table_extraction_method")
            parser = parser or "docling"
            table_metadata["parser"] = parser
            table_metadata.setdefault("text_extraction_method", parser)

        for table in tables:
            normalize_table(table)

        for element in elements:
            element_metadata = dict(element.get("metadata") or {})
            if parser_suffix != suffix:
                element_metadata["format"] = common["format"]
            element_metadata.pop("word_style", None)
            element_metadata.pop("word_style_id", None)
            element_metadata.update({
                key: value for key, value in common.items()
                if key not in element_metadata and key not in {"title", "uploaded_by"}
            })
            element_metadata["pipeline_id"] = engine
            element_metadata["parser_engine"] = "docling" if intent == "invoice" else engine
            parser = element_metadata.get("parser") or element_metadata.get("text_extraction_method")
            parser = parser or "docling"
            element_metadata["parser"] = parser
            element_metadata.setdefault("text_extraction_method", parser)
            source_label = element_metadata.get("layout_type") or element_metadata.get("element_type") or element.get("element_type") or "text"
            element_type = normalize_element_label(source_label)
            element_metadata["element_type"] = element_type
            element_metadata["layout_type"] = element_type
            element["element_type"] = element_type
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
            "parser_engine": "docling" if intent == "invoice" else engine,
            "filename": common["filename"],
            "format": common["format"],
            **{key: value for key, value in metadata.items() if key not in {"title", "uploaded_by"}},
        })
        result["elements"] = elements
        result["tables"] = tables
        if intent == "invoice":
            _LOGGER.info(
                "DOCUMENT_PROCESS_COMPONENT %s",
                json.dumps({
                    "invoice_id": metadata.get("invoice_id"),
                    "component": "result_normalization",
                    "element_count": len(elements),
                    "table_count": len(tables),
                    "elapsed_ms": round((time.perf_counter() - normalization_started) * 1000, 2),
                }, separators=(",", ":")),
            )
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
