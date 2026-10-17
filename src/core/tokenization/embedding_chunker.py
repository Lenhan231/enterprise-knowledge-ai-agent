"""Prepare parser output as token-bounded embedding passages."""

from typing import Any

from .token_counter import TokenCounter


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
        for part in token_counter.split_text(
            text, max_sequence_tokens=max_sequence_tokens,
        ):
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
