"""Bounded process-local context; prior turns are never source evidence."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


@dataclass
class _Conversation:
    fingerprint: tuple
    touched: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    history: list[dict[str, str]] = field(default_factory=list)
    users: int = 0


class ConversationStore:
    def __init__(self, *, capacity=100, ttl=1800, max_chars=12_000, clock=time.monotonic):
        self.entries = OrderedDict()
        self.capacity, self.ttl, self.max_chars, self.clock = capacity, ttl, max_chars, clock

    @asynccontextmanager
    async def session(self, request):
        identity = request.identity
        if identity is None or not request.conversation_id:
            yield []
            return
        now = self.clock()
        key = (identity.subject, request.conversation_id)
        fingerprint = (tuple(sorted(identity.permissions)), tuple(sorted(identity.document_roles)))
        for candidate, entry in list(self.entries.items()):
            if not entry.users and now - entry.touched >= self.ttl:
                del self.entries[candidate]
        if key not in self.entries:
            if len(self.entries) >= self.capacity:
                victim = next((k for k, v in self.entries.items() if not v.users), None)
                if victim is None:
                    raise RuntimeError('Conversation service is busy')
                del self.entries[victim]
            self.entries[key] = _Conversation(fingerprint, now)
        entry = self.entries[key]
        if entry.users >= 8:
            raise RuntimeError('Conversation is busy')
        entry.users += 1
        try:
            async with entry.lock:
                if entry.fingerprint != fingerprint:
                    entry.history.clear()
                    entry.fingerprint = fingerprint
                yield entry.history
        finally:
            entry.users -= 1
            entry.touched = self.clock()
            entry.history[:] = entry.history[-6:]
            while entry.history and sum(len(v) for turn in entry.history for v in turn.values()) > self.max_chars:
                entry.history.pop(0)
            self.entries.move_to_end(key)
