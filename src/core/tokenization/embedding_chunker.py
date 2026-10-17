"""Prepare parser output as token-bounded embedding passages."""

from typing import Any

from .token_counter import TokenCounter


def _context_prefix(text: str) -> tuple[str, str]:
    """Separate section/table headers so each token fragment can retain them."""
    lines = text.splitlines()
    prefix_lines = []
    while lines and lines[0].startswith(("Section: ", "Table: ", "Columns: ")):
        prefix_lines.append(lines.pop(0))
    return "\n".join(prefix_lines), "\n".join(lines)


def _split_body(token_counter: TokenCounter, body: str, sequence_limit: int) -> list[str]:
    content_limit = sequence_limit - token_counter.tokenizer.num_special_tokens_to_add(pair=False)
    overlap = min(32, max(0, content_limit // 8))
    return token_counter.split_text(
        body, max_sequence_tokens=sequence_limit, overlap_tokens=overlap,
    )


def build_embedding_chunks(
    parser_chunks: list[dict[str, Any]],
    token_counter: TokenCounter,
    max_sequence_tokens: int,
    model_name: str,
) -> list[dict[str, Any]]:
    """Split parser chunks to the embedding limit and add final-chunk metadata."""
    bounded_chunks = []
    for parser_chunk in parser_chunks:
        text = parser_chunk.get("text", parser_chunk.get("content", ""))
        if not isinstance(text, str) or not text.strip():
            continue
        metadata = dict(parser_chunk.get("metadata") or {})
        prefix, body = _context_prefix(text)
        special_tokens = token_counter.tokenizer.num_special_tokens_to_add(pair=False)
        if not prefix or token_counter.count(text) <= max_sequence_tokens - special_tokens:
            parts = token_counter.split_text(text, max_sequence_tokens=max_sequence_tokens)
        else:
            body_limit = max_sequence_tokens - token_counter.count(prefix)
            if body_limit <= special_tokens:
                raise ValueError("Heading and table headers exceed the embedding token limit")
            parts = [f"{prefix}\n{part}" for part in _split_body(token_counter, body, body_limit)]
            while any(token_counter.count(part) > max_sequence_tokens - special_tokens for part in parts):
                body_limit -= 1
                if body_limit <= special_tokens:
                    raise ValueError("Heading and table headers exceed the embedding token limit")
                parts = [f"{prefix}\n{part}" for part in _split_body(token_counter, body, body_limit)]
        for part in parts:
            chunk_metadata = dict(metadata)
            chunk_metadata.update({
                "chunk_index": len(bounded_chunks),
                "token_count": token_counter.count(part),
                "embedding_max_sequence_length": max_sequence_tokens,
                "actual_char_count": len(part),
                "embedding_model": model_name,
            })
            bounded_chunks.append({"text": part, "metadata": chunk_metadata})
    return bounded_chunks
