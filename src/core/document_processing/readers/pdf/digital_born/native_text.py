"""Read native text from one digital-born PDF page."""

from __future__ import annotations

import fitz


def extract_native_page_text(page: fitz.Page, *, preserve_layout: bool = True) -> str:
    """Extract the page's embedded text, preserving columns when requested."""
    return page.get_text("text") if preserve_layout else page.get_text()
