"""PDF source downloader."""

from .base import SourceDownloader


class PDFDownloader(SourceDownloader):
    extension = ".pdf"

    def validate(self, header: bytes, url: str) -> None:
        if not header.lower().startswith(b"%pdf-"):
            raise ValueError(f"Downloaded content is not a PDF: {url}")
