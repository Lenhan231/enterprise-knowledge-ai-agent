"""Paragraph and sentence-aware character chunking."""

import re

from .fixed import split_ranges as split_fixed_ranges


def split_ranges(text: str, size: int, overlap: int) -> list[tuple[int, int]]:
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
                ranges.extend(split_fixed_ranges(
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
