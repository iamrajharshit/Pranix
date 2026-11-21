# SPDX-License-Identifier: AGPL-3.0-only
"""CacheStore (F2, D70): memory and SQLite behave the same, and a broken cache never breaks the app."""

import os
import stat
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from pranix.store.cache import CacheStore, MemoryCacheStore, SQLiteCacheStore, open_cache


class Clock:
    def __init__(self) -> None:
        self.t = 1_000.0

    def __call__(self) -> float:
        return self.t


Factory = Callable[[Path, Clock], CacheStore]
STORES: dict[str, Factory] = {
    "memory": lambda p, c: MemoryCacheStore(clock=c),
    "sqlite": lambda p, c: SQLiteCacheStore(p / "cache.sqlite", clock=c),
}


@pytest.fixture(params=list(STORES))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[CacheStore, Clock]:
    clock = Clock()
    return STORES[request.param](tmp_path, clock), clock


def test_round_trip_overwrite_and_expiry(store: tuple[CacheStore, Clock]) -> None:
    s, clock = store
    assert s.get("k") is None
    s.put("k", {"headline": "Warm Leo", "items": ["a", "b"]}, ttl=60)
    assert s.get("k") == {"headline": "Warm Leo", "items": ["a", "b"]}
    s.put("k", {"headline": "Steady Moon"}, ttl=60)
    assert s.get("k") == {"headline": "Steady Moon"} and s.size() == 1
    clock.t += 61
    assert s.get("k") is None


def test_purge_removes_only_expired(store: tuple[CacheStore, Clock]) -> None:
    s, clock = store
    s.put("old", {"v": 1}, ttl=10)
    s.put("new", {"v": 2}, ttl=100)
    clock.t += 50
    assert s.purge_expired() == 1 and s.size() == 1 and s.get("new") == {"v": 2}


def test_sqlite_survives_a_restart(tmp_path: Path) -> None:
    clock = Clock()
    SQLiteCacheStore(tmp_path / "c.sqlite", clock=clock).put("k", {"v": "kept"}, ttl=60)
    assert SQLiteCacheStore(tmp_path / "c.sqlite", clock=clock).get("k") == {"v": "kept"}


def test_sqlite_caps_its_size(tmp_path: Path) -> None:
    clock = Clock()
    s = SQLiteCacheStore(tmp_path / "c.sqlite", max_items=3, clock=clock)
    for i in range(5):
        s.put(f"k{i}", {"i": i}, ttl=100 + i)
    s.purge_expired()
    assert s.size() == 3 and s.get("k0") is None and s.get("k4") == {"i": 4}


def test_sqlite_is_safe_across_threads(tmp_path: Path) -> None:
    s = SQLiteCacheStore(tmp_path / "c.sqlite")

    def work(n: int) -> None:
        for i in range(50):
            s.put(f"{n}-{i}", {"n": n, "i": i}, ttl=60)
            assert s.get(f"{n}-{i}") == {"n": n, "i": i}

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert s.size() == 400


def test_corrupt_file_degrades_to_misses(tmp_path: Path) -> None:
    path = tmp_path / "c.sqlite"
    path.write_bytes(b"this is not a database" * 100)
    s = SQLiteCacheStore(path)
    s.put("k", {"v": 1}, ttl=60)  # must not raise
    assert s.get("k") is None and s.size() == 0 and s.purge_expired() == 0


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_read_only_directory_degrades_to_misses(tmp_path: Path) -> None:
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        s = SQLiteCacheStore(ro / "c.sqlite")
        s.put("k", {"v": 1}, ttl=60)
        assert s.get("k") is None
    finally:
        ro.chmod(stat.S_IRWXU)


def test_open_cache_picks_the_backend(tmp_path: Path) -> None:
    assert isinstance(open_cache(""), MemoryCacheStore)
    assert isinstance(open_cache(str(tmp_path / "x" / "c.sqlite")), SQLiteCacheStore)
