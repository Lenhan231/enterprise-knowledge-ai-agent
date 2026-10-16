"""Character-based chunking used to turn extracted document text into passages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .strategies.fixed import split_ranges as split_fixed_ranges
from .strategies.sentence import split_ranges as split_sentence_ranges

DEFAULT_CHUNKING_STRATEGY = "sentence"
DEFAULT_CHUNK_SIZE = 1100
DEFAULT_CHUNK_OVERLAP = 120


@dataclass(frozen=True)
class ChunkingConfig:
    """Validated character-chunking options shared by document processors."""

    strategy: str = DEFAULT_CHUNKING_STRATEGY
    size: int = DEFAULT_CHUNK_SIZE
    overlap: int = DEFAULT_CHUNK_OVERLAP

    @classmethod
    def from_config(cls, config: dict[str, Any] | None = None) -> "ChunkingConfig":
        config = config or {}
        existing = config.get("chunking")
        if isinstance(existing, cls):
            return existing
        strategy = config.get("chunking_strategy", DEFAULT_CHUNKING_STRATEGY)
        size = int(config.get("chunk_size", DEFAULT_CHUNK_SIZE))
        overlap = int(config.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP))
        if strategy not in {"fixed", "sentence"}:
            raise ValueError("chunking strategy must be 'fixed' or 'sentence'")
        if size <= 0 or overlap < 0 or overlap >= size:
            raise ValueError("chunk size must be positive and overlap smaller than size")
        return cls(strategy=strategy, size=size, overlap=overlap)


def split_ranges(
    text: str,
    *,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    strategy: str = DEFAULT_CHUNKING_STRATEGY,
) -> list[tuple[int, int]]:
    """Route to a chunking strategy and return source text offsets."""
    if strategy == "fixed":
        return split_fixed_ranges(text, size, overlap)
    if strategy == "sentence":
        return split_sentence_ranges(text, size, overlap)
    raise ValueError("chunking strategy must be 'fixed' or 'sentence'")


def split_text(
    text: str,
    *,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    strategy: str = DEFAULT_CHUNKING_STRATEGY,
) -> list[str]:
    return [text[start:end].strip() for start, end in split_ranges(
        text, size=size, overlap=overlap, strategy=strategy
    )]


def split_document_text(
    text: str,
    metadata: dict[str, Any],
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    strategy: str = DEFAULT_CHUNKING_STRATEGY,
) -> list[dict[str, Any]]:
    """Split text into chunks and attach consistent chunk metadata."""
    return [{
        "text": value,
        "metadata": {
            **metadata,
            "chunk_index": index,
            "chunk_strategy": strategy,
            "chunk_size_chars": size,
            "chunk_overlap_chars": overlap if strategy == "fixed" else 0,
        },
    } for index, value in enumerate(split_text(text, size=size, overlap=overlap, strategy=strategy))]
