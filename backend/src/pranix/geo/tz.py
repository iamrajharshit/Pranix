# SPDX-License-Identifier: AGPL-3.0-only
"""Time zone from coordinates (FR-GEO-03). Offline: timezonefinder with the
timezone-boundary-builder data (ODbL)."""

from __future__ import annotations

import threading
from functools import cache

from timezonefinder import TimezoneFinder

_lock = threading.Lock()


@cache
def _finder() -> TimezoneFinder:
    return TimezoneFinder()


def tz_at(lat: float, lon: float) -> str | None:
    """IANA zone for a point on land; None at sea (nautical Etc/GMT±N zones are not land zones)."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("coordinates out of range")
    with _lock:
        tz = _finder().timezone_at(lng=lon, lat=lat)
    if tz is None or tz.startswith("Etc/"):
        return None
    return str(tz)
