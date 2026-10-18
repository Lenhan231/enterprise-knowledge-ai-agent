"""Shared heading patterns used when normalizing parsed document sections."""

import re

HEADING_PATTERNS = {
    "chapter": re.compile(r"^chapter\s*(?:[ivxlcdm]+|\d+)", re.IGNORECASE),
    "article": re.compile(r"^article\s*\d+(?:\.\d+)*", re.IGNORECASE),
    "subsection": re.compile(r"^(?:\d+(?:\.\d+)+|\([a-z0-9ivx]+\))\s+\S", re.IGNORECASE),
}

HEADING_LEVELS = {"chapter": 1, "article": 2, "subsection": 3}


def heading_level(text: str) -> int | None:
    """Return the level for a numbered structural heading, when recognizable."""
    for kind, pattern in HEADING_PATTERNS.items():
        if pattern.match(text):
            return HEADING_LEVELS[kind]
    return None
