"""Use Docling's native format backends through one normalized adapter."""

from __future__ import annotations

from typing import Any

from core.document_processing.readers.text.digital_born.processor import TextProcessor
from core.document_processing.pipelines.docling.processor import DoclingProcessor


def process_file(filename: str, content: bytes, metadata: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if filename.lower().endswith(".txt"):
        result = TextProcessor(config).process_file(content, metadata)
        for chunk in result["chunks"]:
            chunk["metadata"].update({
                "parser": "native.text",
                "text_extraction_method": "native.text",
            })
        return result
    return DoclingProcessor(config).process(content, None, {"content": content, "metadata": metadata})
