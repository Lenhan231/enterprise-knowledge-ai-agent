"""Create shared text and table chunks from normalized parser output."""

from __future__ import annotations

from typing import Any

from core.chunking.config import ChunkingConfig
from core.chunking.table.chunker import build_table_chunks
from core.chunking.text.chunk_builder import build_text_chunks


class ChunkingProcessor:
    """Downstream chunking stage shared by production and Upload Test."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.chunking = ChunkingConfig.from_config(self.config)

    def process(self, parsed: dict[str, Any]) -> dict[str, Any]:
        elements = parsed.get("elements", [])
        tables = parsed.get("tables", [])
        ordered_chunks: list[tuple[int, int, dict[str, Any]]] = []

        for source_order, text, metadata in self._text_groups(elements):
            for index, chunk in enumerate(build_text_chunks(text, metadata, self.chunking)):
                ordered_chunks.append((source_order, index, chunk))

        for source_order, table, metadata in self._table_entries(elements, tables):
            for index, chunk in enumerate(build_table_chunks(
                table, self.chunking, metadata=metadata,
            )):
                ordered_chunks.append((source_order, index, chunk))

        ordered_chunks.sort(key=lambda item: (item[0], item[1]))
        chunks = self._merge_short_text_chunks([item[2] for item in ordered_chunks])
        for index, chunk in enumerate(chunks):
            chunk["text"] = str(chunk.get("text") or "").strip()
            chunk["metadata"].update({
                "chunk_index": index,
                "actual_char_count": len(chunk["text"]),
            })

        output = dict(parsed)
        output["chunks"] = chunks
        return output

    @staticmethod
    def _text_groups(elements: list[dict[str, Any]]):
        groups: list[tuple[int, str, dict[str, Any]]] = []
        pending_text = ""
        pending_metadata: dict[str, Any] | None = None
        pending_key: tuple[Any, ...] | None = None
        pending_order = 0

        def flush() -> None:
            nonlocal pending_text, pending_metadata, pending_key
            if pending_text and pending_metadata is not None:
                groups.append((pending_order, pending_text, pending_metadata))
            pending_text = ""
            pending_metadata = None
            pending_key = None

        for source_order, element in enumerate(elements):
            metadata = dict(element.get("metadata") or {})
            element_type = str(metadata.get("element_type") or metadata.get("layout_type") or "text").lower()
            if element_type == "table":
                flush()
                continue
            text = str(element.get("text") or "").strip()
            if not text:
                continue
            path = metadata.get("section_path")
            section = tuple(path) if isinstance(path, list) else (str(metadata.get("section_title") or ""),)
            key = (
                metadata.get("page_number"), metadata.get("sheet_name"),
                metadata.get("slide_number"), metadata.get("paragraph_index"),
                section, element_type,
            )
            if pending_text and key == pending_key:
                pending_text += "\n\n" + text
                if metadata.get("source_elements"):
                    pending_metadata["source_elements"] = [
                        *pending_metadata.get("source_elements", []), *metadata["source_elements"],
                    ]
            else:
                flush()
                pending_text = text
                pending_metadata = metadata
                pending_key = key
                pending_order = source_order
        flush()
        return groups

    @staticmethod
    def _table_entries(elements: list[dict[str, Any]], tables: list[dict[str, Any]]):
        referenced: dict[int, tuple[int, dict[str, Any]]] = {}
        for source_order, element in enumerate(elements):
            metadata = dict(element.get("metadata") or {})
            if str(metadata.get("element_type") or metadata.get("layout_type") or "").lower() != "table":
                continue
            table_ref = element.get("table_ref")
            if isinstance(table_ref, int) and 0 <= table_ref < len(tables):
                metadata.setdefault("table_index", tables[table_ref].get("table_index", table_ref))
                referenced[table_ref] = (source_order, metadata)

        entries = []
        for table_ref, table in enumerate(tables):
            if table_ref in referenced:
                source_order, metadata = referenced[table_ref]
            else:
                source_order = len(elements) + table_ref
                metadata = dict(table.get("metadata") or {})
                metadata.setdefault("table_index", table.get("table_index", table_ref))
            metadata.update({"element_type": "table", "layout_type": "table"})
            entries.append((source_order, table, metadata))
        return entries

    def _merge_short_text_chunks(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge heading-only fragments into nearby prose before downstream indexing."""
        merged: list[dict[str, Any]] = []

        def retain_sources(target: dict, source: dict) -> None:
            if source.get("source_elements"):
                values = list(target.get("source_elements", []))
                values.extend(item for item in source["source_elements"] if item not in values)
                target["source_elements"] = values

        def location(metadata: dict[str, Any]) -> tuple[Any, ...]:
            path = metadata.get("section_path")
            section = tuple(path) if isinstance(path, list) else (str(metadata.get("section_title") or ""),)
            return (metadata.get("page_number"), metadata.get("sheet_name"), metadata.get("slide_number"), section)

        def join_text(left: str, right: str, metadata: dict[str, Any]) -> str:
            title = str(metadata.get("section_title") or "").strip()
            prefix = f"Section: {title}" if title else ""
            parts = []
            for value in (left.strip(), right.strip()):
                if prefix and value.startswith(prefix + "\n"):
                    value = value[len(prefix):].lstrip("\n")
                if value:
                    parts.append(value)
            body = "\n\n".join(parts)
            return f"{prefix}\n{body}" if prefix and body else body

        for index, chunk in enumerate(chunks):
            text = str(chunk.get("text") or "").strip()
            metadata = chunk.get("metadata") or {}
            element = str(metadata.get("element_type") or metadata.get("layout_type") or "text").lower()
            if index + 1 < len(chunks):
                next_metadata = chunks[index + 1].get("metadata") or {}
                title = str(metadata.get("section_title") or "").strip()
                heading = text.splitlines()[0].strip().strip("#* ") if text else ""
                if title and location(metadata) == location(next_metadata) and heading == title and str(next_metadata.get("section_title") or "").strip() == title:
                    retain_sources(next_metadata, metadata)
                    continue
            if element in {"text", "title", "paragraph"} and 0 < len(text) < 80 and index + 1 < len(chunks):
                following = chunks[index + 1]
                following_metadata = following.get("metadata") or {}
                following_type = str(following_metadata.get("element_type") or following_metadata.get("layout_type") or "text").lower()
                following_text = str(following.get("text") or "")
                if (
                    following_type in {"text", "paragraph"}
                    and location(metadata) == location(following_metadata)
                    and len(text) + len(following_text) + 2 <= self.chunking.size
                ):
                    following["text"] = join_text(text, following_text, following_metadata)
                    retain_sources(following_metadata, metadata)
                    continue
            if element in {"text", "title", "paragraph"} and 0 < len(text) < 80 and merged:
                previous = merged[-1]
                previous_metadata = previous.get("metadata") or {}
                previous_type = str(previous_metadata.get("element_type") or previous_metadata.get("layout_type") or "text").lower()
                previous_text = str(previous.get("text") or "")
                if (
                    previous_type in {"text", "paragraph"}
                    and location(metadata) == location(previous_metadata)
                    and len(previous_text) + len(text) + 2 <= self.chunking.size
                ):
                    previous["text"] = join_text(previous_text, text, previous_metadata)
                    retain_sources(previous_metadata, metadata)
                    continue
            merged.append(chunk)
        return merged
