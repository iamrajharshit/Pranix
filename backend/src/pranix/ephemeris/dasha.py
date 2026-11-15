# SPDX-License-Identifier: AGPL-3.0-only
"""Vimshottari Dasha with exact arithmetic (FR-DSH-01..04, ENG-04).

Instants are Fractions of seconds since the Unix epoch (UTC). Nothing is rounded until
output, where instants are rounded to whole seconds. Sub-periods of a period therefore
sum to exactly the parent's length.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

from . import angles
from .ruleset import Ruleset

ABBR = {
    "Sun": "Su",
    "Moon": "Mo",
    "Mars": "Ma",
    "Mercury": "Me",
    "Jupiter": "Ju",
    "Venus": "Ve",
    "Saturn": "Sa",
    "Rahu": "Ra",
    "Ketu": "Ke",
}
FROM_ABBR = {v: k for k, v in ABBR.items()}
MAX_DEPTH = 5  # Maha, Antar, Pratyantar, Sookshma, Prana


@dataclass(frozen=True)
class Period:
    lord: str
    level: int
    start: Fraction
    end: Fraction
    path: str
    full_start: Fraction  # start before clipping to the birth instant
    from_birth: bool = False

    @property
    def length(self) -> Fraction:
        return self.end - self.full_start

    def contains(self, t: Fraction) -> bool:
        return self.start <= t < self.end

    def to_dict(self, now: Fraction | None = None) -> dict[str, Any]:
        d: dict[str, Any] = {
            "lord": self.lord,
            "level": self.level,
            "start": iso(self.start),
            "end": iso(self.end),
            "path": self.path,
        }
        if self.from_birth:
            d["from_birth"] = True
        if now is not None:
            d["contains_now"] = self.contains(now)
        return d


def iso(t: Fraction) -> str:
    """Round to the nearest whole second only here (output)."""
    secs = round(t)
    return datetime.fromtimestamp(secs, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def instant(dt: datetime) -> Fraction:
    if dt.tzinfo is None:
        raise ValueError("aware datetime required")
    td = dt - datetime(1970, 1, 1, tzinfo=UTC)  # exact integer parts, no float
    return Fraction(td.days * 86400 + td.seconds) + Fraction(td.microseconds, 1_000_000)


def year_seconds(rs: Ruleset) -> Fraction:
    return rs.dasha_year_days * 86400  # 365.25 d = 31,557,600 s exactly


def _sequence_from(rs: Ruleset, lord: str) -> list[str]:
    i = rs.dasha_order.index(lord)
    return [rs.dasha_order[(i + k) % 9] for k in range(9)]


def mahadashas(rs: Ruleset, moon_lon: float, birth: Fraction) -> list[Period]:
    """The nine Mahadashas of the cycle running at birth; the first is clipped to birth."""
    q = Fraction(angles.normalize(moon_lon))
    n = int(q // angles.NAKSHATRA)
    elapsed_fraction = (q - n * angles.NAKSHATRA) / angles.NAKSHATRA
    first = rs.nakshatras[n].lord
    y = year_seconds(rs)
    start = birth - elapsed_fraction * rs.dasha_years[first] * y
    out: list[Period] = []
    for i, lord in enumerate(_sequence_from(rs, first)):
        end = start + rs.dasha_years[lord] * y
        out.append(Period(lord, 1, birth if i == 0 else start, end, ABBR[lord], start, from_birth=(i == 0)))
        start = end
    return out


def children(rs: Ruleset, parent: Period) -> list[Period]:
    """Nine sub-periods, starting from the parent's own lord, proportional to its years."""
    if parent.level >= MAX_DEPTH:
        raise ValueError("deepest level reached")
    total = sum(rs.dasha_years.values())  # 120
    start = parent.full_start
    out: list[Period] = []
    for lord in _sequence_from(rs, parent.lord):
        end = start + parent.length * Fraction(rs.dasha_years[lord], total)
        out.append(Period(lord, parent.level + 1, start, end, f"{parent.path}>{ABBR[lord]}", start))
        start = end
    assert out[-1].end == parent.end  # exact by construction
    return out


def active_chain(rs: Ruleset, moon_lon: float, birth: Fraction, at: Fraction, depth: int = MAX_DEPTH) -> list[Period]:
    level = mahadashas(rs, moon_lon, birth)
    chain: list[Period] = []
    while True:
        current = next((p for p in level if p.full_start <= at < p.end), None)
        if current is None:
            return chain
        chain.append(current)
        if len(chain) >= depth:
            return chain
        level = children(rs, current)


def periods_at_path(rs: Ruleset, moon_lon: float, birth: Fraction, path: str | None) -> list[Period]:
    """Timeline endpoint (FR-DSH-03): no path -> Mahadashas; 'Ju>Ve' -> its nine children."""
    level = mahadashas(rs, moon_lon, birth)
    if not path:
        return level
    parts = path.split(">")
    if len(parts) >= MAX_DEPTH or any(p not in FROM_ABBR for p in parts):
        raise ValueError("invalid path")
    node: Period | None = None
    for part in parts:
        node = next((p for p in level if p.lord == FROM_ABBR[part]), None)
        if node is None:
            raise ValueError("invalid path")
        level = children(rs, node)
    return level
