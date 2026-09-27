"""Deterministic fixed and sentence/paragraph-aware text chunking."""

from __future__ import annotations

import re
from typing import Any


def _fixed_ranges(text: str, size: int, overlap: int, base: int = 0) -> list[tuple[int, int]]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("chunk size must be positive and overlap smaller than size")
    ranges = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        if text[start:end].strip():
            ranges.append((base + start, base + end))
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return ranges


def split_ranges(
    text: str,
    *,
    size: int = 1100,
    overlap: int = 120,
    strategy: str = "sentence",
) -> list[tuple[int, int]]:
    """Return source offsets for fixed or paragraph/sentence-aware chunks."""
    if strategy == "fixed":
        return _fixed_ranges(text, size, overlap)
    if strategy not in {"sentence", "semantic"}:
        raise ValueError("chunking strategy must be 'fixed' or 'sentence'")
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("chunk size must be positive and overlap smaller than size")

    ranges: list[tuple[int, int]] = []
    paragraph_pattern = re.compile(r"\S(?:.*?\S)?(?=\n\s*\n|\s*\Z)", re.DOTALL)
    sentence_boundary = re.compile(r"(?<=[.!?。！？])\s+")
    for paragraph in paragraph_pattern.finditer(text):
        paragraph_text = paragraph.group()
        sentence_spans = []
        start = 0
        for boundary in sentence_boundary.finditer(paragraph_text):
            if paragraph_text[start:boundary.start()].strip():
                sentence_spans.append((start, boundary.start()))
            start = boundary.end()
        if paragraph_text[start:].strip():
            sentence_spans.append((start, len(paragraph_text)))
        if not sentence_spans:
            continue

        chunk_start: int | None = None
        chunk_end: int | None = None
        for sentence_start, sentence_end in sentence_spans:
            absolute_start = paragraph.start() + sentence_start
            absolute_end = paragraph.start() + sentence_end
            if absolute_end - absolute_start > size:
                if chunk_start is not None and chunk_end is not None:
                    ranges.append((chunk_start, chunk_end))
                    chunk_start = chunk_end = None
                ranges.extend(_fixed_ranges(
                    text[absolute_start:absolute_end], size, overlap, base=absolute_start
                ))
            elif chunk_start is None:
                chunk_start, chunk_end = absolute_start, absolute_end
            elif absolute_end - chunk_start <= size:
                chunk_end = absolute_end
            else:
                ranges.append((chunk_start, chunk_end))
                chunk_start, chunk_end = absolute_start, absolute_end
        if chunk_start is not None and chunk_end is not None:
            ranges.append((chunk_start, chunk_end))
    return ranges


def split_text(
    text: str,
    *,
    size: int = 1100,
    overlap: int = 120,
    strategy: str = "sentence",
) -> list[str]:
    return [text[start:end].strip() for start, end in split_ranges(
        text, size=size, overlap=overlap, strategy=strategy
    )]


class TextProcessor:
    """Compatibility wrapper used by document-processing callers."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def process(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        text = document.get("content", document.get("text"))
        if not isinstance(text, str):
            raise ValueError("Document must contain a text or content string")
        strategy = self.config.get("chunking_strategy", "sentence")
        strategy = "sentence" if strategy == "semantic" else strategy
        chunks = split_text(
            text,
            size=int(self.config.get("chunk_size", 1100)),
            overlap=int(self.config.get("chunk_overlap", 120)),
            strategy=strategy,
        )
        return [{
            "text": chunk,
            "metadata": {
                **document.get("metadata", {}),
                "chunk_index": index,
                "chunk_strategy": strategy,
                "chunk_size_chars": int(self.config.get("chunk_size", 1100)),
                "chunk_overlap_chars": int(self.config.get("chunk_overlap", 120)) if strategy == "fixed" else 0,
            },
        } for index, chunk in enumerate(chunks)]

    def _fixed_size_chunking(self, text: str) -> list[str]:
        return split_text(
            text, size=int(self.config.get("chunk_size", 1100)),
            overlap=int(self.config.get("chunk_overlap", 120)), strategy="fixed",
        )

    def _semantic_chunking(self, text: str) -> list[str]:
        return split_text(
            text, size=int(self.config.get("chunk_size", 1100)),
            overlap=0, strategy="sentence",
        )

    def _recursive_chunking(self, text: str) -> list[str]:
        return self._semantic_chunking(text)
