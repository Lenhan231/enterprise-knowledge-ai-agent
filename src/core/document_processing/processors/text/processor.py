"""Decode text uploads and create chunks for TXT and Markdown files."""

from __future__ import annotations

from typing import Any

from core.chunking.text_chunker import ChunkingConfig, split_document_text


class TextProcessor:
    """Decode TXT/Markdown files and pass their text to the shared chunker."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.chunking = ChunkingConfig.from_config(self.config)

    def process_file(self, content: bytes, metadata: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Decode a UTF-8 text/Markdown upload and chunk it with source metadata."""
        text = content.decode("utf-8-sig")
        return {"chunks": self.process({"text": text, "metadata": metadata}), "tables": []}

    def process(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        text = document.get("content", document.get("text"))
        if not isinstance(text, str):
            raise ValueError("Document must contain a text or content string")
        return split_document_text(
            text,
            document.get("metadata", {}),
            self.chunking.size,
            self.chunking.overlap,
            self.chunking.strategy,
        )
