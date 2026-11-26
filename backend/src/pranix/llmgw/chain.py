# SPDX-License-Identifier: AGPL-3.0-only
"""Fixed-priority chain with per-provider token buckets and circuit breakers (FR-LLM-02..05, -12).

A 429 opens the breaker until Retry-After; repeated failures open it for a cooldown, then one
probe is allowed (half-open). No hedged duplicate calls. When nothing can serve, the caller
falls back to the curated library (FR-LLM-16).

G1 (D82): a call names its `Task`. The chain skips any provider that doesn't accept the task's data
class (typed text never reaches Gemini free, D32), and draws from the provider's budget share for the
task's chain, so readings can't use up the Groq quota that chat needs.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import structlog

from ..util.tokenbucket import TokenBucket
from .providers import Provider, ProviderError, Usage
from .tasks import FACTS_ONLY, Task

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
    shares: dict[str, TokenBucket] = field(default_factory=dict)  # per-chain budget ("chat", "reading")


@dataclass
class Result:
    text: str
    provider: str
    model: str
    usage: Usage
    latency_ms: float
    depth: int


@dataclass
class Stream:
    """A started answer: which provider is speaking, and the rest of its pieces (first one included)."""

    provider: str
    model: str
    depth: int
    pieces: Iterator[str]


class Chain:
    def __init__(self, links: list[Link], clock: Callable[[], float] = time.monotonic) -> None:
        self.links, self.clock = links, clock
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.links)

    def _ready(self, link: Link, task: Task | None, module: str) -> bool:
        """The guard, then the breaker, then the budget share, then the provider's own bucket."""
        accepts = getattr(link.provider, "accepts", FACTS_ONLY)  # undeclared = facts only (the safe side)
        if task is not None and task.data_class not in accepts:
            log.warning("llm.refused", provider=link.provider.name, task=task.id, data_class=task.data_class)
            return False
        with self._lock:
            if not link.breaker.available(self.clock()):
                return False
            share = link.shares.get(task.chain) if task is not None else None
            if share is not None and share.take("chain") is not None:
                return False
            return link.bucket.take("chain") is None

    def _failed(self, link: Link, e: ProviderError, module: str, depth: int, started: float) -> None:
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

    def stream(self, system: str, user: str, *, task: Task, module: str) -> Stream | None:
        """Chat (V1). Falls through to the next provider only until the first piece arrives; after that
        the answer belongs to that provider, and a later error reaches the caller (it shows Retry)."""
        for depth, link in enumerate(self.links):
            start = getattr(link.provider, "stream", None)
            if start is None or not self._ready(link, task, module):
                continue
            started = time.perf_counter()
            it: Iterator[str] = start(system, user, link.timeout or task.timeout_s)
            try:
                first = next(it)
            except StopIteration:
                self._failed(link, ProviderError("bad_output"), module, depth, started)
                continue
            except ProviderError as e:
                self._failed(link, e, module, depth, started)
                continue
            with self._lock:
                link.breaker.success()
            log.info(
                "llm.stream",
                provider=link.provider.name,
                model=link.provider.model,
                module=module,
                task=task.id,
                fallback_depth=depth,
                first_piece_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            return Stream(link.provider.name, link.provider.model, depth, _prepend(first, it))
        return None

    def generate(
        self,
        system: str,
        user: str,
        *,
        module: str,
        timeout: float | None = None,
        accept: Callable[[str], bool] = lambda _: True,
        task: Task | None = None,
    ) -> Result | None:
        timeout = timeout if timeout is not None else (task.timeout_s if task is not None else 8.0)
        for depth, link in enumerate(self.links):
            if not self._ready(link, task, module):
                continue
            started = time.perf_counter()
            try:
                text, usage = link.provider.generate(system, user, link.timeout or timeout)
                if not accept(text):
                    raise ProviderError("bad_output")
            except ProviderError as e:
                self._failed(link, e, module, depth, started)
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


def _prepend(first: str, rest: Iterator[str]) -> Iterator[str]:
    yield first
    yield from rest
