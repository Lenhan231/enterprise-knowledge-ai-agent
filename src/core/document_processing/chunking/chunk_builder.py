"""Build parser chunks and attach the shared chunk metadata."""

from typing import Any

from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.chunking.router import split_text


def build_text_chunks(
    text: str,
    metadata: dict[str, Any],
    config: ChunkingConfig,
) -> list[dict[str, Any]]:
    values = split_text(
        text,
        size=config.size,
        overlap=config.overlap,
        strategy=config.strategy,
    )
    return [
        build_text_chunk(value, metadata, config, index=index)
        for index, value in enumerate(values)
    ]


def build_text_chunk(
    text: str,
    metadata: dict[str, Any],
    config: ChunkingConfig,
    *,
    index: int,
) -> dict[str, Any]:
    """Build one already-split chunk with the shared chunk metadata."""
    return {
        "text": text,
        "metadata": {
            **metadata,
            "chunk_index": index,
            "chunk_strategy": config.strategy,
            "chunk_size_chars": config.size,
            "chunk_overlap_chars": config.overlap if config.strategy == "fixed" else 0,
        },
    }
