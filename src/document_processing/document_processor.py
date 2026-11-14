"""Parse supported documents with Docling and normalize the results."""

from __future__ import annotations

from pathlib import Path
import json
import logging
import time
from typing import Any
from io import BytesIO
import math
import re
import xml.etree.ElementTree as ET

from document_processing.element_taxonomy import normalize_element_label
from document_processing.invoice_ocr_cache import invoice_docling_cache

SUPPORTED_FORMATS = frozenset({
    ".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".svg", ".webp",
})
_INVOICE_EXTRACTION_CONFIG_KEYS = frozenset({
    "invoice_provider",
    "gemini_invoice_model",
    "groq_invoice_model",
    "invoice_model",
    "invoice_model_revision",
    "invoice_adapter",
    "invoice_adapter_revision",
})
_LOGGER = logging.getLogger(__name__)


def render_webp(content: bytes) -> bytes:
    """Convert a single WebP image to PNG for Docling and preview generation."""
    from PIL import Image

    try:
        with Image.open(BytesIO(content)) as image:
            if image.format != "WEBP" or getattr(image, "n_frames", 1) != 1:
                raise ValueError("Expected a single-frame WebP image")
            if image.width * image.height > 16_000_000:
                raise ValueError("WebP image is too large")
            output = BytesIO()
            rgba = image.convert("RGBA")
            background = Image.new("RGB", image.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            background.save(output, format="PNG")
            return output.getvalue()
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("Could not open WebP image") from error


def render_svg(content: bytes) -> bytes:
    """Render a self-contained SVG as PNG without fetching external resources."""
    try:
        text = content.decode("utf-8-sig")
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)|<\?xml-stylesheet", text, re.IGNORECASE):
            raise ValueError("SVG document declarations are not supported")
        root = ET.fromstring(text)
        if root.tag != "{http://www.w3.org/2000/svg}svg" and root.tag != "svg":
            raise ValueError("File is not an SVG")
        for node in root.iter():
            for name, value in node.attrib.items():
                if name.rsplit("}", 1)[-1] == "href" and not value.strip().startswith("#"):
                    raise ValueError("SVG external references are not supported")
                if re.search(r"url\s*\(\s*['\"]?(?!#)", value, re.IGNORECASE):
                    raise ValueError("SVG external references are not supported")
            if node.tag.rsplit("}", 1)[-1] in {"script", "style", "foreignObject"}:
                raise ValueError("SVG scripts, stylesheets and foreign objects are not supported")
        import fitz
        with fitz.open(stream=content, filetype="svg") as document:
            page = document[0]
            width, height = page.rect.width, page.rect.height
            if not all(math.isfinite(v) and 0 < v <= 10000 for v in (width, height)):
                raise ValueError("SVG dimensions are invalid")
            scale = min(2.0, 4096 / width, 4096 / height)
            return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png")
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("Could not render SVG") from error

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
        if suffix not in self.SUPPORTED:
            raise ValueError(f"Unsupported document format: {suffix or 'unknown'}")
        intent = str(self.config.get("intent", "document")).strip().lower()
        if intent not in {"document", "invoice", "image_caption"}:
            raise ValueError(f"Unsupported document intent: {intent}")
        common = {
            **metadata,
            "filename": Path(filename).name,
            "format": suffix[1:].upper(),
            "intent": intent,
        }
        if intent == "invoice":
            from document_processing.docling_adapter.processor import DoclingProcessor
            from document_processing.invoice_text_processor import InvoiceTextProcessor

            engine = "docling_qwen_invoice_text"
            processor_config = {**self.config, "parser_engine": "docling", "intent": "document"}
            parser_content = render_svg(content) if suffix == ".svg" else render_webp(content) if suffix == ".webp" else content
            parser_metadata = {**common, "format": "PNG"} if suffix in {".svg", ".webp"} else common
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
            extraction = InvoiceTextProcessor(self.config).process(
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
        elif intent == "image_caption":
            from document_processing.vintern_processor import VinternProcessor

            engine = "vintern_image_caption"
            result = VinternProcessor(self.config).process(filename, content, common)
        else:
            engine = str(self.config.get("parser_engine", "docling"))
            if engine != "docling":
                raise ValueError(f"Unsupported parser pipeline: {engine}")
            from document_processing.docling_adapter.processor import DoclingProcessor

            processor_config = {**self.config, "parser_engine": engine}
            parser_content = render_svg(content) if suffix == ".svg" else render_webp(content) if suffix == ".webp" else content
            parser_metadata = {**common, "format": "PNG"} if suffix in {".svg", ".webp"} else common
            result = DoclingProcessor(processor_config).process(
                parser_content, None, {"content": parser_content, "metadata": parser_metadata}
            )
        normalization_started = time.perf_counter()
        elements = result.get("elements", [])
        tables = result.get("tables", [])
        if suffix in {".png", ".jpg", ".jpeg", ".svg", ".webp"}:
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
            if suffix in {".svg", ".webp"}:
                table_metadata["format"] = suffix[1:].upper()
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
            if suffix in {".svg", ".webp"}:
                element_metadata["format"] = suffix[1:].upper()
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
