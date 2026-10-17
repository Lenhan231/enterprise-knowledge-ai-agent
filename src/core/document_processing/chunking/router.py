"""Route text and structured tables to their respective chunkers."""

from typing import Any, Literal

from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.chunking.table.chunker import build_table_chunks
from core.document_processing.chunking.text.chunk_builder import build_text_chunks


def build_chunks(
    content: str | dict[str, Any],
    config: ChunkingConfig,
    *,
    kind: Literal["text", "table"],
    metadata: dict[str, Any] | None = None,
    title: str = "",
) -> list[dict[str, Any]]:
    """Dispatch parser content to the shared text or table chunking path."""
    if kind == "text":
        if not isinstance(content, str):
            raise TypeError("text chunking requires string content")
        return build_text_chunks(content, metadata or {}, config)
    if kind == "table":
        if not isinstance(content, dict):
            raise TypeError("table chunking requires a structured table")
        return build_table_chunks(content, config, metadata=metadata, title=title)
    raise ValueError("chunk kind must be 'text' or 'table'")
