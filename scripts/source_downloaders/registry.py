"""Resolve manifest entries to format-specific downloaders."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from .base import SourceDownloader
from .html import HTMLDownloader
from .image import IMAGE_EXTENSIONS, ImageDownloader
from .pdf import PDFDownloader


def _image_extension(declared_format: str, source_path: str) -> str | None:
    for format_name, extension in IMAGE_EXTENSIONS.items():
        if declared_format == format_name:
            if extension == ".img":
                suffix = Path(source_path).suffix.lower()
                return suffix if suffix in set(IMAGE_EXTENSIONS.values()) else ".img"
            return extension
    suffix = Path(source_path).suffix.lower()
    return suffix if suffix in set(IMAGE_EXTENSIONS.values()) else None


def get_downloader(document: dict[str, str]) -> SourceDownloader:
    """Return the handler matching a manifest row's format and URL."""
    declared_format = document.get("format", "PDF").strip().upper()
    source_path = urlparse(document.get("official_url", "")).path.lower()

    image_extension = _image_extension(declared_format, source_path)
    if image_extension:
        return ImageDownloader(image_extension)
    if declared_format == "HTML" or source_path.endswith((".html", ".htm", ".aspx")):
        return HTMLDownloader()
    if "PDF" in declared_format or source_path.endswith(".pdf"):
        return PDFDownloader()
    raise ValueError(f"Unsupported source format: {declared_format or 'unknown'}")


def source_extension(document: dict[str, str]) -> str:
    return get_downloader(document).extension


def download_source(
    document: dict[str, str],
    url: str,
    destination: Path,
    force: bool = False,
) -> str:
    return get_downloader(document).download(url, destination, force)
