"""Decode text uploads and create chunks for TXT and Markdown files."""

from __future__ import annotations

import re
from typing import Any

from core.document_processing.chunking.chunk_builder import build_text_chunks
from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.headings import heading_level as structural_heading_level, section_metadata

_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


class TextProcessor:
    """Decode TXT/Markdown files and pass their text to the shared chunker."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.chunking = ChunkingConfig.from_config(self.config)

    def process_file(self, content: bytes, metadata: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Decode a UTF-8 text/Markdown upload and chunk it with source metadata."""
        text = content.decode("utf-8-sig")
        return {"chunks": self._process_sections(text, metadata), "tables": []}

    def process(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        text = document.get("content", document.get("text"))
        if not isinstance(text, str):
            raise ValueError("Document must contain a text or content string")
        return build_text_chunks(text, document.get("metadata", {}), self.chunking)

    def _process_sections(self, text: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        """Keep explicit Markdown and conservative plain-text headings with their sections."""
        is_markdown = str(metadata.get("format", "")).upper() == "MD"
        chunks = []
        section_lines: list[str] = []
        section_context = {**metadata, **section_metadata(None, None)}

        def flush() -> None:
            if section_lines and "".join(section_lines).strip():
                chunks.extend(build_text_chunks("".join(section_lines), section_context, self.chunking))

        for line in text.splitlines(keepends=True):
            heading = _MARKDOWN_HEADING.match(line.strip()) if is_markdown else None
            if heading:
                flush()
                section_lines.clear()
                section_context = {
                    **metadata,
                    **section_metadata(heading.group(2).strip(), len(heading.group(1))),
                }
            elif not is_markdown:
                structural_level = structural_heading_level(line.strip())
                candidate = line.strip()
                plain_title = (
                    2 <= len(candidate) <= 100
                    and candidate.isupper()
                    and any(character.isalpha() for character in candidate)
                    and not candidate.endswith((".", ",", ";", ":"))
                )
                if structural_level or (plain_title and len(line.split()) <= 12):
                    flush()
                    section_lines.clear()
                    section_context = {
                        **metadata,
                        **section_metadata(candidate, structural_level or 1),
                    }
            section_lines.append(line)
        flush()
        return chunks
