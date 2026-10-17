"""Shared heading context fields for parser chunks."""


def section_metadata(title: str | None, level: int | None) -> dict[str, str | int | None]:
    """Return the common section fields while preserving source-specific detection."""
    return {"section_title": title, "heading_level": level}
