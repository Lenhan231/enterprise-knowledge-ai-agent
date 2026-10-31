"""Resolve table markers without losing their original reading position."""

from typing import Any


def resolve_table_references(
    elements: list[dict[str, Any]], tables: list[dict[str, Any]],
) -> dict[int, tuple[int, dict[str, Any]]]:
    """Keep the first marker; accept duplicates only with compatible context."""
    referenced: dict[int, tuple[int, dict[str, Any]]] = {}
    context_keys = ("section_title", "section_path", "heading_level")
    location_keys = ("page_number", "sheet_name", "slide_number", "bbox")
    for index, element in enumerate(elements):
        metadata = dict(element.get("metadata") or {})
        kind = metadata.get("element_type") or metadata.get("layout_type") or element.get("element_type")
        if "table_ref" not in element and kind != "table":
            continue
        ref = element.get("table_ref")
        if type(ref) is not int or not 0 <= ref < len(tables):
            raise ValueError("Table references must be valid integer indexes")
        path = metadata.get("section_path")
        if not metadata.get("section_title") and isinstance(path, list) and path:
            metadata["section_title"] = path[-1]
        metadata.update(element_type="table", layout_type="table")
        if ref not in referenced:
            referenced[ref] = (index, metadata)
            continue
        _, first = referenced[ref]
        for key in (*context_keys, *location_keys):
            if first.get(key) and metadata.get(key) and first[key] != metadata[key]:
                raise ValueError(f"Conflicting table references for table_ref={ref}: {key}")
        for key in context_keys:
            if not first.get(key) and metadata.get(key):
                first[key] = metadata[key]
    return referenced
