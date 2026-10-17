"""Validate Office archives and route DOCX, PPTX, and XLSX parsing."""

from __future__ import annotations

import io
import zipfile
from typing import Any
from xml.etree import ElementTree

from .docx.digital_born.processor import DocxProcessor
from .pptx.digital_born.processor import PptxProcessor
from .xlsx.digital_born.processor import XlsxProcessor

_MAX_OFFICE_ARCHIVE_ENTRIES = 10_000
_MAX_OFFICE_MEMBER_BYTES = 100 * 1024 * 1024
_MAX_OFFICE_TOTAL_BYTES = 200 * 1024 * 1024
_MAX_OFFICE_COMPRESSION_RATIO = 200


def _validate_office_archive(archive: zipfile.ZipFile) -> None:
    """Reject Office packages whose declared expansion could exhaust app resources."""
    members = archive.infolist()
    if len(members) > _MAX_OFFICE_ARCHIVE_ENTRIES:
        raise ValueError("Office document contains too many archive entries")

    total_size = 0
    for member in members:
        if member.is_dir():
            continue
        if member.file_size > _MAX_OFFICE_MEMBER_BYTES:
            raise ValueError(f"Office archive member is too large: {member.filename}")
        total_size += member.file_size
        if total_size > _MAX_OFFICE_TOTAL_BYTES:
            raise ValueError("Office document expands beyond the 200 MiB processing limit")
        if member.file_size and member.compress_size == 0:
            raise ValueError(f"Office archive member has an invalid compressed size: {member.filename}")
        if member.compress_size and member.file_size / member.compress_size > _MAX_OFFICE_COMPRESSION_RATIO:
            raise ValueError(f"Office archive member has a suspicious compression ratio: {member.filename}")


class OfficeProcessor:
    """Route validated Office documents to their format-specific processor."""

    _PROCESSORS = {
        ".docx": DocxProcessor,
        ".pptx": PptxProcessor,
        ".xlsx": XlsxProcessor,
    }

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def process(self, suffix: str, content: bytes, metadata: dict[str, Any]) -> dict[str, list[dict]]:
        processor_class = self._PROCESSORS.get(suffix)
        if processor_class is None:
            raise ValueError(f"Unsupported Office format: {suffix}")

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                _validate_office_archive(archive)
                return processor_class(self.config).process(archive, metadata)
        except (zipfile.BadZipFile, ElementTree.ParseError) as error:
            raise ValueError("Invalid Office archive or XML document") from error
