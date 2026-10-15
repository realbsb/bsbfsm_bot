"""Утилита антифлуда."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from .utils import trace


@dataclass
class Bucket:
    events: deque = field(default_factory=deque)


class AntiFlood:
    @trace
    def __init__(self, rate: int = 10, per_seconds: int = 5) -> None:
        self._rate = rate
        self._per = per_seconds
        self._buckets: dict[int, Bucket] = {}

    @trace
    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        bucket = self._buckets.setdefault(user_id, Bucket())
        while bucket.events and now - bucket.events[0] > self._per:
            bucket.events.popleft()
        if len(bucket.events) >= self._rate:
            return False
        bucket.events.append(now)
        return True

    @trace
    def reset(self, user_id: int) -> None:
        self._buckets.pop(user_id, None)
