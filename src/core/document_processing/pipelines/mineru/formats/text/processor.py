"""Read plain text directly without starting the MinerU runtime."""

from __future__ import annotations

from typing import Any

from core.document_processing.readers.text.digital_born.processor import TextProcessor


def process(runtime: Any, content: bytes, document: dict[str, Any]) -> dict[str, Any]:
    metadata = document.get("metadata", {})
    result = TextProcessor(runtime.config).process_file(content, metadata)
    for element in result["elements"]:
        element["metadata"].update({
            "parser": "native.text",
            "text_extraction_method": "native.text",
        })
    return result
