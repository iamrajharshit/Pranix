# SPDX-License-Identifier: AGPL-3.0-only
"""CacheStore: a small key → JSON store with a time to live (D70).

Keys are hashes of *meaning* (module or target + facts + prompt, schema and library versions),
never of a person, so one AI call serves every chart with the same placements and the store
holds no personal data.

- `MemoryCacheStore`: in-process LRU (tests, and the fallback).
- `SQLiteCacheStore`: one file on the server's disk; survives restarts; WAL mode for readers.

A cache must never take the app down: any SQLite error (locked, corrupt, read-only, disk full)
is logged once per kind and the call behaves like a miss / a skipped write.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import structlog

log = structlog.get_logger("pranix.store.cache")

Clock = Callable[[], float]


class CacheStore(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...

    def put(self, key: str, value: dict[str, Any], ttl: float) -> None: ...

    def purge_expired(self) -> int: ...

    def size(self) -> int: ...


class MemoryCacheStore:
    def __init__(self, max_items: int = 5_000, clock: Clock = time.time) -> None:
        self.max_items, self.clock = max_items, clock
        self._d: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            v = self._d.get(key)
            if v is None or v[0] <= self.clock():
                self._d.pop(key, None)
                return None
            self._d.move_to_end(key)
            return v[1]

    def put(self, key: str, value: dict[str, Any], ttl: float) -> None:
        with self._lock:
            self._d[key] = (self.clock() + ttl, value)
            self._d.move_to_end(key)
            while len(self._d) > self.max_items:
                self._d.popitem(last=False)

    def purge_expired(self) -> int:
        now = self.clock()
        with self._lock:
            dead = [k for k, (exp, _) in self._d.items() if exp <= now]
            for k in dead:
                del self._d[k]
        return len(dead)

    def size(self) -> int:
        with self._lock:
            return len(self._d)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS cache_expires ON cache(expires_at);
"""


class SQLiteCacheStore:
    """Thread-safe: one connection per thread; SQLite serialises writers, WAL lets readers run."""

    def __init__(self, path: str | Path, max_items: int = 200_000, clock: Clock = time.time) -> None:
        self.path, self.max_items, self.clock = str(path), max_items, clock
        self._local = threading.local()
        self._warned: set[str] = set()
        self._ok = True
        try:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            con = self._con()
            if con is not None:
                con.executescript(_SCHEMA)
        except (sqlite3.Error, OSError) as e:
            self._fail("init", e)

    def _con(self) -> sqlite3.Connection | None:
        con: sqlite3.Connection | None = getattr(self._local, "con", None)
        if con is None:
            try:
                con = sqlite3.connect(self.path, timeout=0.5, isolation_level=None, check_same_thread=False)
                con.execute("PRAGMA journal_mode=WAL")
                con.execute("PRAGMA synchronous=NORMAL")
                self._local.con = con
            except sqlite3.Error as e:
                self._fail("connect", e)
                return None
        return con

    def _fail(self, op: str, e: Exception) -> None:
        kind = f"{op}:{type(e).__name__}"
        if kind not in self._warned:  # once per kind: never flood the logs
            self._warned.add(kind)
            log.warning("cache.degraded", op=op, error=type(e).__name__)
        self._local.con = None

    def get(self, key: str) -> dict[str, Any] | None:
        con = self._con()
        if con is None:
            return None
        try:
            row = con.execute("SELECT value, expires_at FROM cache WHERE key = ?", (key,)).fetchone()
            if row is None or row[1] <= self.clock():
                return None
            value: dict[str, Any] = json.loads(row[0])
            return value
        except (sqlite3.Error, ValueError) as e:
            self._fail("get", e)
            return None

    def put(self, key: str, value: dict[str, Any], ttl: float) -> None:
        con = self._con()
        if con is None:
            return
        try:
            con.execute(
                "INSERT INTO cache(key, value, expires_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, expires_at = excluded.expires_at",
                (key, json.dumps(value, ensure_ascii=False, sort_keys=True), self.clock() + ttl),
            )
        except sqlite3.Error as e:
            self._fail("put", e)

    def purge_expired(self) -> int:
        """Delete expired rows, then the soonest-expiring rows above `max_items`."""
        con = self._con()
        if con is None:
            return 0
        try:
            n = con.execute("DELETE FROM cache WHERE expires_at <= ?", (self.clock(),)).rowcount
            over = self.size() - self.max_items
            if over > 0:
                n += con.execute(
                    "DELETE FROM cache WHERE key IN (SELECT key FROM cache ORDER BY expires_at LIMIT ?)", (over,)
                ).rowcount
            return int(n)
        except sqlite3.Error as e:
            self._fail("purge", e)
            return 0

    def size(self) -> int:
        con = self._con()
        if con is None:
            return 0
        try:
            return int(con.execute("SELECT count(*) FROM cache").fetchone()[0])
        except sqlite3.Error as e:
            self._fail("size", e)
            return 0


def open_cache(path: str, clock: Clock = time.time) -> CacheStore:
    """SQLite when a path is configured, else memory (tests and minimal setups)."""
    return SQLiteCacheStore(path, clock=clock) if path else MemoryCacheStore(clock=clock)


def start_purger(cache: CacheStore, every_seconds: float = 3600.0) -> Callable[[], None]:
    """Purge expired entries on a daemon thread; returns a stop function (called at shutdown)."""
    stop = threading.Event()

    def run() -> None:
        while not stop.wait(every_seconds):
            n = cache.purge_expired()
            log.info("cache.purged", entries=n, remaining=cache.size())

    threading.Thread(target=run, name="cache-purger", daemon=True).start()
    return stop.set
