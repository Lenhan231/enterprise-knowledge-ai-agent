"""Shared metric implementations used by layer and pipeline evaluators."""


def page_key(row: dict) -> tuple[str, int]:
    """Return the canonical (document, one-based page) key used by predictions."""
    return row["document_id"], int(row["source_page_number_1based"])
