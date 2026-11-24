# SPDX-License-Identifier: AGPL-3.0-only
"""Fixed-priority chain with per-provider token buckets and circuit breakers (FR-LLM-02..05, -12).

A 429 opens the breaker until Retry-After; repeated failures open it for a cooldown, then one
probe is allowed (half-open). No hedged duplicate calls. When nothing can serve, the caller
falls back to the curated library (FR-LLM-16).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

from ..util.tokenbucket import TokenBucket
from .providers import Provider, ProviderError, Usage

log = structlog.get_logger()


@dataclass
class Breaker:
    failures: int = 0
    open_until: float = 0.0
    threshold: int = 3
    cooldown: float = 60.0

    def available(self, now: float) -> bool:
        return now >= self.open_until

    def success(self) -> None:
        self.failures, self.open_until = 0, 0.0

    def failure(self, now: float, retry_after: float | None = None) -> None:
        if retry_after:
            self.open_until = now + retry_after
            return
        self.failures += 1
        if self.failures >= self.threshold:
            self.open_until, self.failures = now + self.cooldown, self.threshold - 1  # half-open after cooldown


@dataclass
class Link:
    provider: Provider
    bucket: TokenBucket
    breaker: Breaker = field(default_factory=Breaker)
    timeout: float | None = None  # per-provider override: a CPU-only local model needs longer


@dataclass
class Result:
    text: str
    provider: str
    model: str
    usage: Usage
    latency_ms: float
    depth: int


class Chain:
    def __init__(self, links: list[Link], clock: Callable[[], float] = time.monotonic) -> None:
        self.links, self.clock = links, clock
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.links)

    def generate(
        self,
        system: str,
        user: str,
        *,
        module: str,
        timeout: float = 8.0,
        accept: Callable[[str], bool] = lambda _: True,
    ) -> Result | None:
        for depth, link in enumerate(self.links):
            now = self.clock()
            with self._lock:
                if not link.breaker.available(now) or link.bucket.take("chain") is not None:
                    continue
            started = time.perf_counter()
            try:
                text, usage = link.provider.generate(system, user, link.timeout or timeout)
                if not accept(text):
                    raise ProviderError("bad_output")
            except ProviderError as e:
                if e.kind != "busy":  # busy is normal for a one-slot local model, not a fault
                    with self._lock:
                        link.breaker.failure(self.clock(), e.retry_after)
                log.warning(
                    "llm.call",
                    provider=link.provider.name,
                    model=link.provider.model,
                    module=module,
                    outcome=e.kind,
                    fallback_depth=depth,
                    latency_ms=round((time.perf_counter() - started) * 1000, 1),
                )
                continue
            with self._lock:
                link.breaker.success()
            ms = round((time.perf_counter() - started) * 1000, 1)
            log.info(
                "llm.call",
                provider=link.provider.name,
                model=link.provider.model,
                module=module,
                outcome="ok",
                fallback_depth=depth,
                latency_ms=ms,
                tokens_in=usage.tokens_in,
                tokens_out=usage.tokens_out,
            )
            return Result(text, link.provider.name, link.provider.model, usage, ms, depth)
        return None
