# SPDX-License-Identifier: AGPL-3.0-only
"""Guest charts in process memory with a TTL and an LRU bound (FR-GST-01).

Only the derived Master JSON and a Dasha seed (Moon longitude, birth instant) are kept,
never the date, place or name as entered. Nothing is written to disk or logged.
Lost on restart: the browser re-POSTs from sessionStorage (410 CHART_EXPIRED handling).
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any


@dataclass(frozen=True)
class GuestChart:
    profile_id: str
    master: dict[str, Any]
    expires_at: float
    chart_key: str
    seed: tuple[float, Fraction] | None = None  # (Moon longitude, birth instant) for the Dasha timeline

    @property
    def expires_iso(self) -> str:
        return datetime.fromtimestamp(self.expires_at, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class GuestStore:
    def __init__(self, ttl_seconds: int, max_items: int = 2_000, clock: Callable[[], float] = time.time) -> None:
        self.ttl, self.max_items, self.clock = ttl_seconds, max_items, clock
        self._items: OrderedDict[str, GuestChart] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, master: dict[str, Any], chart_key: str, seed: tuple[float, Fraction] | None = None) -> GuestChart:
        item = GuestChart(str(uuid.uuid4()), master, self.clock() + self.ttl, chart_key, seed)
        with self._lock:
            self._items[item.profile_id] = item
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)
        return item

    def get(self, profile_id: str) -> GuestChart | None:
        with self._lock:
            item = self._items.get(profile_id)
            if item is None:
                return None
            if item.expires_at <= self.clock():
                del self._items[profile_id]
                return None
            self._items.move_to_end(profile_id)
            return item

    def delete(self, profile_id: str) -> None:
        with self._lock:
            self._items.pop(profile_id, None)

    def __len__(self) -> int:
        return len(self._items)
