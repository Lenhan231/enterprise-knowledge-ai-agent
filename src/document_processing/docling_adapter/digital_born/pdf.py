"""Detect PDFs with native text on every page."""

from __future__ import annotations

from pathlib import Path


def has_native_text_on_every_page(source: bytes | str | Path) -> bool:
    """Use native PDF text only when each page has meaningful selectable text."""
    try:
        import fitz

        if isinstance(source, bytes):
            pdf = fitz.open(stream=source, filetype="pdf")
        else:
            pdf = fitz.open(source)
        with pdf:
            if not pdf.page_count:
                return False
            for page in pdf:
                text = page.get_text("text")
                if sum(not char.isspace() for char in text) < 100:
                    return False
        return True
    except Exception:
        # If classification fails, retain the OCR path so scanned text is not lost.
        return False


def has_embedded_raster_images(source: bytes | str | Path) -> bool:
    """Return whether a PDF contains raster images that may need OCR."""
    try:
        import fitz

        if isinstance(source, bytes):
            pdf = fitz.open(stream=source, filetype="pdf")
        else:
            pdf = fitz.open(source)
        with pdf:
            return any(page.get_images(full=True) for page in pdf)
    except Exception:
        return False
