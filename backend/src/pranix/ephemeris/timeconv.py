# SPDX-License-Identifier: AGPL-3.0-only
"""Local civil time -> UTC with historical tz rules (FR-INP-01/02)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

UTC = UTC
MIN_YEAR, MAX_YEAR = 1800, 2399  # ephemeris coverage (FR-INP-03)


class BirthTimeError(ValueError):
    """Maps to a 422 problem code."""

    def __init__(self, code: str, options: list[dict[str, str]] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.options = options or []


@dataclass(frozen=True)
class ResolvedInstant:
    utc: datetime
    tz: str
    utc_offset_seconds: int


def to_utc(
    local: datetime,
    tz: str,
    disambiguation: Literal["earlier", "later"] | None = None,
) -> ResolvedInstant:
    """Convert a naive local datetime in `tz` to UTC.

    Raises BirthTimeError("AMBIGUOUS_LOCAL_TIME", options) on a DST fold without a choice,
    and BirthTimeError("NONEXISTENT_LOCAL_TIME") inside a DST gap.
    """
    if local.tzinfo is not None:
        raise ValueError("local datetime must be naive")
    if not MIN_YEAR <= local.year <= MAX_YEAR:
        raise BirthTimeError("OUT_OF_RANGE")
    zone = ZoneInfo(tz)
    a = local.replace(tzinfo=zone, fold=0)
    b = local.replace(tzinfo=zone, fold=1)
    off_a, off_b = a.utcoffset(), b.utcoffset()
    assert off_a is not None and off_b is not None

    # Gap: the wall time never existed, so it does not survive a round trip.
    if a.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != local:
        raise BirthTimeError("NONEXISTENT_LOCAL_TIME")

    if off_a != off_b:  # fold: the wall time happened twice
        if disambiguation is None:
            raise BirthTimeError(
                "AMBIGUOUS_LOCAL_TIME",
                [
                    {"disambiguation": "earlier", "utc": a.astimezone(UTC).isoformat()},
                    {"disambiguation": "later", "utc": b.astimezone(UTC).isoformat()},
                ],
            )
        chosen = a if disambiguation == "earlier" else b
    else:
        chosen = a
    off = chosen.utcoffset() or timedelta(0)
    return ResolvedInstant(chosen.astimezone(UTC), tz, int(off.total_seconds()))


def julian_day_ut(utc: datetime) -> float:
    """Julian day (UT) from an aware UTC datetime, without calling Swiss Ephemeris."""
    if utc.tzinfo is None:
        raise ValueError("utc datetime must be aware")
    u = utc.astimezone(UTC)
    epoch = datetime(2000, 1, 1, 12, tzinfo=UTC)  # J2000.0 = JD 2451545.0
    return 2451545.0 + (u - epoch).total_seconds() / 86400.0
