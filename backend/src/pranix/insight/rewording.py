# SPDX-License-Identifier: AGPL-3.0-only
"""Background re-wording (D77, plan §8.3).

When a reading is served as curated text because no provider could answer (quota out, Gemma busy,
an answer refused), the same request is offered here. One in-process worker thread asks the local
model (Gemma) for it later, one at a time, and puts the answer in the meaning cache. The next reader
with the same facts gets the AI text at once. Nothing is promised to the reader who saw curated text.

Deliberately small: a bounded in-memory list, no message queue, no retries beyond one, nothing
persisted. A restart forgets pending work; the next curated serve offers it again.

Privacy (rule 3): a job holds only what the live call would send, the de-identified payload (module,
facts, draft, reviewed knowledge), plus the fact ids the guardrails check against. Logs carry the
module name and counts, never the payload or the answer.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()

MAX_ATTEMPTS = 2  # a busy or refused job gets one more turn at the back of the line, then is dropped


@dataclass
class Job:
    module: str
    key: str
    user: str  # the de-identified payload, exactly as the live call sent it
    given: str  # names the AI may use (the entity check)
    curated: dict[str, Any]
    fact_ids: tuple[str, ...]
    attempts: int = 0


@dataclass
class Stats:
    pending: int = 0
    done: int = 0
    failed: int = 0
    dropped: int = 0


@dataclass
class Rewording:
    """`run(job)` returns the AI fields or None; `store(job, fields)` caches them.
    `gap_s` paces the model (60 / its requests per minute) so live chart requests keep the CPU."""

    run: Callable[[Job], dict[str, Any] | None]
    store: Callable[[Job, dict[str, Any]], None]
    is_cached: Callable[[str], bool]
    max_pending: int = 200
    gap_s: float = 10.0
    autostart: bool = True  # False: nothing runs until run_pending() (tests, tools)
    _q: deque[Job] = field(default_factory=deque, init=False, repr=False)
    _keys: set[str] = field(default_factory=set, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _wake: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    stats: Stats = field(default_factory=Stats, init=False)

    def offer(self, job: Job) -> bool:
        """Add a job unless the same reading is already waiting or the list is full."""
        with self._lock:
            if job.key in self._keys:
                return False
            if len(self._q) >= self.max_pending:
                self.stats.dropped += 1
                log.info("insight.reword", outcome="dropped_full", module=job.module)
                return False
            self._q.append(job)
            self._keys.add(job.key)
            self.stats.pending = len(self._q)
        log.info("insight.reword", outcome="queued", module=job.module, pending=self.stats.pending)
        if self.autostart:
            self._ensure_worker()
            self._wake.set()
        return True

    def run_pending(self, limit: int | None = None) -> int:
        """Work through waiting jobs now, on this thread (tests and tools). Returns how many ran."""
        n = 0
        while (limit is None or n < limit) and self._step():
            n += 1
        return n

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="pranix-reword", daemon=True)
                self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self._step():
                self._wake.wait(timeout=30.0)
                self._wake.clear()
                continue
            self._stop.wait(self.gap_s)

    def _step(self) -> bool:
        with self._lock:
            if not self._q:
                return False
            job = self._q.popleft()
            self.stats.pending = len(self._q)
        started = time.perf_counter()
        try:
            out = None if self.is_cached(job.key) else self.run(job)
            already = out is None and self.is_cached(job.key)
        except Exception as e:  # never let one bad job stop the worker; only the error type is logged
            log.warning("insight.reword", outcome="error", module=job.module, error=type(e).__name__)
            out, already = None, False
        ms = round((time.perf_counter() - started) * 1000, 1)
        if out is not None:
            self.store(job, out)
            self._finish(job)
            self.stats.done += 1
            log.info("insight.reword", outcome="ok", module=job.module, latency_ms=ms)
        elif already:  # a live call filled it meanwhile
            self._finish(job)
        elif job.attempts + 1 < MAX_ATTEMPTS:
            job.attempts += 1
            with self._lock:
                self._q.append(job)  # one more turn, at the back
                self.stats.pending = len(self._q)
            log.info("insight.reword", outcome="retry_later", module=job.module, latency_ms=ms)
        else:
            self._finish(job)
            self.stats.failed += 1
            log.info("insight.reword", outcome="gave_up", module=job.module, latency_ms=ms)
        return True

    def _finish(self, job: Job) -> None:
        with self._lock:
            self._keys.discard(job.key)
