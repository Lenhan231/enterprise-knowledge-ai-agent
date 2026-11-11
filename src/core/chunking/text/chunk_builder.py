"""Build parser chunks and attach the shared chunk metadata."""

from typing import Any

from core.chunking.config import ChunkingConfig
from core.chunking.text.router import split_text


def section_context(metadata: dict[str, Any]) -> str:
    """Keep ancestor headings in table content, with the leaf title as fallback."""
    path = metadata.get("section_path")
    if metadata.get("element_type") == "table" and isinstance(path, list):
        headings = [value.strip() for value in path if isinstance(value, str) and value.strip()]
        if headings:
            return " > ".join(headings)
    return str(metadata.get("section_title") or "").strip()


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
    section_title = section_context(metadata)
    if section_title:
        heading = f"Section: {section_title}"
        lines = text.splitlines()
        first_line = lines[0].strip() if lines else ""
        if first_line != heading and first_line.strip("#* ") != section_title:
            text = f"{heading}\n{text}"
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
