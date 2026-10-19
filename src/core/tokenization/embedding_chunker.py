"""Prepare parser output as token-bounded embedding passages."""

import hashlib
from typing import Any

from .token_counter import TokenCounter


def _context_prefix(text: str) -> tuple[str, str]:
    """Separate section/table headers so each token fragment can retain them."""
    lines = text.splitlines()
    prefix_lines = []
    while lines and lines[0].startswith(("Section: ", "Table: ", "Columns: ")):
        prefix_lines.append(lines.pop(0))
    return "\n".join(prefix_lines), "\n".join(lines)


def _split_body(token_counter: TokenCounter, body: str, sequence_limit: int) -> list[tuple[str, int, int]]:
    content_limit = sequence_limit - token_counter.tokenizer.num_special_tokens_to_add(pair=False)
    overlap = min(32, max(0, content_limit // 8))
    return token_counter.split_text_with_offsets(
        body, max_sequence_tokens=sequence_limit, overlap_tokens=overlap,
    )


def _normalized_source_positions(text: str) -> list[int | None]:
    """Map the existing splitlines/join header normalization back to exact input."""
    positions = []
    source_start = 0
    for line_number, raw_line in enumerate(text.splitlines(keepends=True)):
        if line_number:
            # A normalized LF can map to a real LF, but never to an original CR.
            positions.append(source_start - 1 if text[source_start - 1] == "\n" else None)
        line = raw_line.splitlines()[0]
        positions.extend(range(source_start, source_start + len(line)))
        source_start += len(raw_line)
    return positions


def _source_spans(positions: list[int | None]) -> list[dict[str, int]]:
    """Compress only truly consecutive input/output coordinates into source spans."""
    spans = []
    for child_index, source_index in enumerate(positions):
        if source_index is None:
            continue  # Generated separators are not original evidence characters.
        if spans and spans[-1]["source_end"] == source_index and spans[-1]["chunk_end"] == child_index:
            spans[-1]["source_end"] += 1
            spans[-1]["chunk_end"] += 1
        else:
            spans.append({"source_start": source_index, "source_end": source_index + 1,
                          "chunk_start": child_index, "chunk_end": child_index + 1})
    return spans


def build_embedding_chunks(
    parser_chunks: list[dict[str, Any]],
    token_counter: TokenCounter,
    max_sequence_tokens: int,
    model_name: str,
) -> list[dict[str, Any]]:
    """Split parser chunks to the embedding limit and add final-chunk metadata."""
    bounded_chunks = []
    for parser_position, parser_chunk in enumerate(parser_chunks):
        text = parser_chunk.get("text", parser_chunk.get("content", ""))
        if not isinstance(text, str) or not text.strip():
            continue
        metadata = dict(parser_chunk.get("metadata") or {})
        prefix, body = _context_prefix(text)
        special_tokens = token_counter.tokenizer.num_special_tokens_to_add(pair=False)
        if not prefix or token_counter.count(text) <= max_sequence_tokens - special_tokens:
            slices = token_counter.split_text_with_offsets(text, max_sequence_tokens=max_sequence_tokens)
            parts = [(part, [{"source_start": start, "source_end": end,
                              "chunk_start": 0, "chunk_end": len(part)}])
                     for part, start, end in slices]
        else:
            body_limit = max_sequence_tokens - token_counter.count(prefix)
            if body_limit <= special_tokens:
                raise ValueError("Heading and table headers exceed the embedding token limit")
            slices = _split_body(token_counter, body, body_limit)
            while any(token_counter.count(f"{prefix}\n{part}") > max_sequence_tokens - special_tokens
                      for part, _, _ in slices):
                body_limit -= 1
                if body_limit <= special_tokens:
                    raise ValueError("Heading and table headers exceed the embedding token limit")
                slices = _split_body(token_counter, body, body_limit)
            positions = _normalized_source_positions(text)
            body_start = len(prefix) + 1
            prefix_positions = positions[:len(prefix)] + [positions[len(prefix)] if len(positions) > len(prefix) else None]
            parts = [(f"{prefix}\n{part}", _source_spans(prefix_positions + positions[body_start + start:body_start + end]))
                     for part, start, end in slices]
        source_index = next(value for value in (
            parser_chunk.get("parser_chunk_index"), parser_chunk.get("chunk_index"),
            metadata.get("chunk_index"), parser_position,
        ) if value is not None)
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        for child_index, (part, source_spans) in enumerate(parts):
            chunk_metadata = dict(metadata)
            chunk_metadata.update({
                "chunk_index": len(bounded_chunks),
                "source_parser_index": source_index,
                "source_content_sha256": source_hash,
                "source_child_index": child_index,
                "source_child_count": len(parts),
                "source_spans": source_spans,
                "token_count": token_counter.count(part),
                "embedding_max_sequence_length": max_sequence_tokens,
                "actual_char_count": len(part),
                "embedding_model": model_name,
            })
            bounded_chunks.append({"text": part, "metadata": chunk_metadata})
    return bounded_chunks
