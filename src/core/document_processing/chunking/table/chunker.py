"""Turn structured tables into row-preserving chunks."""

from typing import Any

from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.chunking.text.chunk_builder import build_text_chunk


def build_table_chunks(
    table: dict[str, Any],
    config: ChunkingConfig,
    *,
    metadata: dict[str, Any] | None = None,
    title: str = "",
) -> list[dict[str, Any]]:
    """Chunk structured tables by whole rows, repeating title and headers."""
    title = title.strip() or str(
        (table.get("context") or {}).get("table_title")
        or (table.get("metadata") or {}).get("table_title")
        or ""
    ).strip()
    columns = [
        str(column or f"column_{index + 1}").strip()
        for index, column in enumerate(table.get("columns", []))
    ]
    rows = table.get("rows", [])
    if not columns and rows:
        columns = list(dict.fromkeys(str(key) for row in rows for key in row))
    if not columns:
        return []

    section_title = str((metadata or {}).get("section_title") or "").strip()
    prefix = ([f"Section: {section_title}"] if section_title else [])
    prefix.extend(([f"Table: {title}"] if title else []) + ["Columns: " + " | ".join(columns)])
    row_lines = [
        (row_index, (
            f"Row {row_index}: " + " | ".join(
                f"{column}: {str(row.get(column) if row.get(column) is not None else '').strip()}"
                for column in columns
            )
        ))
        for row_index, row in enumerate(rows, start=1)
        if any(row.get(column) not in (None, "") for column in columns)
    ]
    table_metadata = {
        **(table.get("metadata") or {}),
        **(metadata or {}),
        "page_number": table.get("page_number") or (metadata or {}).get("page_number"),
        "element_type": "table",
        "layout_type": "table",
        "table_index": table.get("table_index"),
    }
    if title:
        table_metadata["table_title"] = title
    chunks: list[dict[str, Any]] = []
    if not row_lines:
        chunk = build_text_chunk("\n".join(prefix), table_metadata, config, index=0)
        chunk["metadata"].update({
            "chunking_method": "table_row_groups",
            "chunk_overlap_chars": 0,
            "table_row_start": None,
            "table_row_end": None,
            "table_fragment_index": 0,
            "table_fragment_count": 1,
        })
        return [chunk]

    current_lines = list(prefix)
    row_start: int | None = None
    row_end: int | None = None

    def flush() -> None:
        chunk = build_text_chunk(
            "\n".join(current_lines), table_metadata, config, index=len(chunks),
        )
        chunk["metadata"].update({
            "chunking_method": "table_row_groups",
            "chunk_overlap_chars": 0,
            "table_row_start": row_start,
            "table_row_end": row_end,
        })
        chunks.append(chunk)

    for row_index, row_line in row_lines:
        candidate = "\n".join([*current_lines, row_line])
        if row_start is not None and len(candidate) > config.size:
            flush()
            current_lines = list(prefix)
            row_start = row_end = None
        current_lines.append(row_line)
        row_start = row_index if row_start is None else row_start
        row_end = row_index
    flush()

    for index, chunk in enumerate(chunks):
        chunk["metadata"].update({
            "table_fragment_index": index,
            "table_fragment_count": len(chunks),
        })
    return chunks
