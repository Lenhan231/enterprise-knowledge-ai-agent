"""Shared atomic HTTP download behavior."""

from __future__ import annotations

import shutil
import tempfile
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path


class SourceDownloader(ABC):
    """Download one source type and validate it before moving it into place."""

    extension: str

    def download(self, url: str, destination: Path, force: bool = False) -> str:
        if destination.exists() and not force:
            return "exists"

        destination.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "AppleCorpusDownloader/1.0"},
        )
        with urllib.request.urlopen(request, timeout=90) as response, tempfile.NamedTemporaryFile(
            dir=destination.parent, delete=False
        ) as temporary:
            shutil.copyfileobj(response, temporary)
            temporary_path = Path(temporary.name)

        try:
            header = temporary_path.read_bytes()[:4096].lstrip()
            self.validate(header, url)
            temporary_path.replace(destination)
        finally:
            temporary_path.unlink(missing_ok=True)
        return "downloaded"

    @abstractmethod
    def validate(self, header: bytes, url: str) -> None:
        """Raise ValueError when the downloaded bytes are the wrong type."""
