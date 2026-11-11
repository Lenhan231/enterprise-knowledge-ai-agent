"""Route character-based text splitting to the selected strategy."""

from __future__ import annotations

from ..config import (
    DEFAULT_CHUNKING_STRATEGY,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
)
from .strategies.fixed import split_ranges as split_fixed_ranges
from .strategies.sentence import split_ranges as split_sentence_ranges


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
    return [
        text[start:end].strip()
        for start, end in split_ranges(
            text, size=size, overlap=overlap, strategy=strategy
        )
    ]
