"""Small process-local cache for retrying invoice extraction after provider failures."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import threading
import time
from typing import Any


class InvoiceDoclingCache:
    """Keep a few bounded, short-lived Docling results for identical invoice inputs."""

    def __init__(
        self,
        *,
        max_entries: int = 4,
        max_entry_bytes: int = 2 * 1024 * 1024,
        max_bytes: int = 8 * 1024 * 1024,
        ttl_seconds: float = 15 * 60,
        clock=time.monotonic,
    ) -> None:
        self.max_entries = max_entries
        self.max_entry_bytes = max_entry_bytes
        self.max_bytes = max_bytes
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, int, dict[str, Any]]] = OrderedDict()
        self._bytes = 0
        self._lock = threading.RLock()

    @staticmethod
    def key(content: bytes, source_format: str, config: dict[str, Any]) -> str:
        config_hash = hashlib.sha256(
            json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        source_hash = hashlib.sha256(content).hexdigest()
        return f"{source_format.lower()}:{source_hash}:{config_hash}"

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            self._purge_expired(self._clock())
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return deepcopy(entry[2])

    def put(self, key: str, result: dict[str, Any]) -> bool:
        # Invoice mode does not request page previews. Avoid retaining image bytes
        # if a caller changes that setting later.
        if result.get("page_previews"):
            return False
        try:
            size = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        except (TypeError, ValueError):
            return False
        if size > self.max_entry_bytes or size > self.max_bytes:
            return False

        stored = deepcopy(result)
        with self._lock:
            now = self._clock()
            self._purge_expired(now)
            previous = self._entries.pop(key, None)
            if previous is not None:
                self._bytes -= previous[1]
            while self._entries and (
                len(self._entries) >= self.max_entries
                or self._bytes + size > self.max_bytes
            ):
                _, (_, removed_size, _) = self._entries.popitem(last=False)
                self._bytes -= removed_size
            self._entries[key] = (now, size, stored)
            self._bytes += size
        return True

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._bytes = 0

    def _purge_expired(self, now: float) -> None:
        expired = [
            key for key, (created, _, _) in self._entries.items()
            if now - created >= self.ttl_seconds
        ]
        for key in expired:
            _, size, _ = self._entries.pop(key)
            self._bytes -= size


invoice_docling_cache = InvoiceDoclingCache()
