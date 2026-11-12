"""Shared edit-distance primitives for document-pipeline evaluators.

Callers own text normalization and tokenization so each benchmark can preserve
its documented scoring contract (for example, Vietnamese word or syllable WER).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


def edit_distance(reference: Sequence[T], hypothesis: Sequence[T]) -> int:
    """Return Levenshtein substitutions + deletions + insertions."""
    previous = list(range(len(hypothesis) + 1))
    for i, item in enumerate(reference, 1):
        current = [i]
        for j, other in enumerate(hypothesis, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (item != other),
            ))
        previous = current
    return previous[-1]


def character_error_count(reference: str, hypothesis: str) -> tuple[int, int]:
    """Return (character edits, reference character count)."""
    return edit_distance(reference, hypothesis), len(reference)


def token_error_count(reference: Sequence[T], hypothesis: Sequence[T]) -> tuple[int, int]:
    """Return (token edits, reference token count) for caller-tokenized text."""
    return edit_distance(reference, hypothesis), len(reference)


def error_rate(edits: int, reference_units: int) -> float | None:
    """Return edit rate, or None when the reference denominator is empty."""
    return edits / reference_units if reference_units else None
