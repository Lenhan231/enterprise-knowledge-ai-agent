"""Small document-ranking metrics for the labelled corpus evaluation set."""

from __future__ import annotations

import math
from collections.abc import Sequence


def precision_at_k(relevant: set[str], ranked: Sequence[str], k: int) -> float:
    _validate_k(k)
    return sum(item in relevant for item in ranked[:k]) / k


def recall_at_k(relevant: set[str], ranked: Sequence[str], k: int) -> float:
    _validate_k(k)
    return sum(item in relevant for item in ranked[:k]) / len(relevant) if relevant else 0.0


def reciprocal_rank(relevant: set[str], ranked: Sequence[str]) -> float:
    return next((1.0 / rank for rank, item in enumerate(ranked, 1) if item in relevant), 0.0)


def ndcg_at_k(relevant: set[str], ranked: Sequence[str], k: int) -> float:
    _validate_k(k)
    dcg = sum(1.0 / math.log2(rank + 1) for rank, item in enumerate(ranked[:k], 1) if item in relevant)
    ideal_hits = min(len(relevant), k)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / ideal if ideal else 0.0


def _validate_k(k: int) -> None:
    if k < 1:
        raise ValueError("k must be positive")
