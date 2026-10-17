"""Shared configuration for character-based chunking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_CHUNKING_STRATEGY = "sentence"
DEFAULT_CHUNK_SIZE = 1100
DEFAULT_CHUNK_OVERLAP = 120


@dataclass(frozen=True)
class ChunkingConfig:
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
