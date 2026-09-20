"""Raster and SVG image source downloader."""

from __future__ import annotations

from .base import SourceDownloader


IMAGE_EXTENSIONS = {
    "JPEG": ".jpg",
    "JPG": ".jpg",
    "PNG": ".png",
    "GIF": ".gif",
    "WEBP": ".webp",
    "TIFF": ".tiff",
    "TIF": ".tiff",
    "SVG": ".svg",
    "IMAGE": ".img",
    "IMG": ".img",
}


class ImageDownloader(SourceDownloader):
    def __init__(self, extension: str) -> None:
        self.extension = extension

    def validate(self, header: bytes, url: str) -> None:
        normalized = header.lower()
        signatures = (
            header.startswith(b"\xff\xd8\xff"),
            header.startswith(b"\x89PNG\r\n\x1a\n"),
            header.startswith((b"GIF87a", b"GIF89a")),
            header.startswith((b"II*\x00", b"MM\x00*")),
            header.startswith(b"RIFF") and b"WEBP" in header[:16],
            b"<svg" in normalized,
        )
        if not any(signatures):
            raise ValueError(f"Downloaded content is not a supported image: {url}")
