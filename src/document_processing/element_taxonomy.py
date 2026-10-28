"""Canonical element labels shared by parsing, review, and evaluation."""

ELEMENT_LABELS = (
    "title",
    "title_table",
    "section_header",
    "text",
    "footnote",
    "document_index",
    "formula",
    "table",
    "figure",
    "seal",
    "page_header",
    "page_footer",
)
_LABEL_SET = frozenset(ELEMENT_LABELS)

_SOURCE_LABELS = {
    "table_caption": "title_table",
    "table_title": "title_table",
    "picture": "figure",
    "chart": "figure",
    "graphic": "figure",
    "stamp": "seal",
    "paragraph": "text",
    "list_item": "text",
    "caption": "text",
    "code": "text",
    "form": "text",
    "key_value_region": "text",
    "handwritten_text": "text",
    "checkbox_selected": "text",
    "checkbox_unselected": "text",
    "reference": "text",
    "layout_table": "text",
}


def normalize_element_label(label: object) -> str:
    """Map parser-specific labels into the shared element taxonomy."""
    value = str(label or "text").strip().lower().replace("-", "_").replace(" ", "_")
    if value in _LABEL_SET:
        return value
    return _SOURCE_LABELS.get(value, "text")
