"""HTML source downloader."""

from .base import SourceDownloader


class HTMLDownloader(SourceDownloader):
    extension = ".html"

    def validate(self, header: bytes, url: str) -> None:
        normalized = header.lower()
        if b"<!doctype html" not in normalized and b"<html" not in normalized:
            raise ValueError(f"Downloaded content is not HTML: {url}")
