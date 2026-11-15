# SPDX-License-Identifier: AGPL-3.0-only
"""In-memory token buckets per client and route group (NFR-SEC-08, Tier A).

State is per process and resets on restart, which is acceptable on the free tier (Runbook 4.4).
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request

from .problems import ProblemError

MAX_KEYS = 20_000


@dataclass
class _Bucket:
    tokens: float
    at: float


class TokenBucket:
    def __init__(self, per_minute: int, burst: int | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.rate = per_minute / 60.0
        self.capacity = float(burst if burst is not None else per_minute)
        self.clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def take(self, key: str) -> int | None:
        """Consume one token. Returns None if allowed, else seconds to wait (for Retry-After)."""
        now = self.clock()
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                if len(self._buckets) >= MAX_KEYS:
                    self._prune(now)
                b = self._buckets[key] = _Bucket(self.capacity, now)
            b.tokens = min(self.capacity, b.tokens + (now - b.at) * self.rate)
            b.at = now
            if b.tokens >= 1:
                b.tokens -= 1
                return None
            return max(1, math.ceil((1 - b.tokens) / self.rate))

    def _prune(self, now: float) -> None:
        full = [k for k, b in self._buckets.items() if b.tokens + (now - b.at) * self.rate >= self.capacity]
        for k in full:
            del self._buckets[k]
        if len(self._buckets) >= MAX_KEYS:  # still full: drop the oldest half
            for k in sorted(self._buckets, key=lambda k: self._buckets[k].at)[: MAX_KEYS // 2]:
                del self._buckets[k]


def client_key(request: Request, trust_proxy: bool) -> str:
    """Client IP. Behind Render's proxy the first X-Forwarded-For entry is the client."""
    if trust_proxy:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(bucket: TokenBucket, request: Request, trust_proxy: bool) -> None:
    wait = bucket.take(client_key(request, trust_proxy))
    if wait is not None:
        raise ProblemError(
            429, "RATE_LIMITED", "Too many requests. Take a breath and try again shortly.", retry_after=wait
        )
