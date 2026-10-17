"""Parse CSV using MinerU's native Flash document parser."""

from __future__ import annotations

from typing import Any


def process(runtime: Any, content: bytes, document: dict[str, Any]) -> dict[str, Any]:
    return runtime.parse_flash(content, "csv", document)
