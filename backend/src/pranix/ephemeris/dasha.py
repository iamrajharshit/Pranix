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
    cycle: int = 1  # D84: the 120-year sequence starts again; 2 = the second run, and so on

    @property
    def length(self) -> Fraction:
        return self.end - self.full_start

    def contains(self, t: Fraction) -> bool:
        return self.start <= t < self.end

    def public_dict(self, now: Fraction | None = None) -> dict[str, Any]:
        """For the browser (D86 C1): the period running at birth has no `start` (that would be the
        birth instant); `period_start`, when that period itself began before birth, lets the
        screen draw the life bar. It says nothing about the person."""
        d = self.to_dict(now)
        if self.from_birth:
            d["start"] = None
        return d

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
            d["period_start"] = iso(self.full_start)  # when the period itself began, before birth (D86 C1)
        if self.cycle > 1:  # only then, so every first-cycle answer stays byte-identical
            d["cycle"] = self.cycle
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


MAX_CYCLE = 6  # births from 1800 to an as-of date before 2400 never need more


def cycle_seconds(rs: Ruleset) -> Fraction:
    return sum(rs.dasha_years.values()) * year_seconds(rs)  # 120 years, exactly


def mahadashas(rs: Ruleset, moon_lon: float, birth: Fraction, cycle: int = 1) -> list[Period]:
    """The nine Mahadashas of one run of the sequence. Cycle one is the run going on at birth (its
    first period is clipped to birth); cycle k is the same run moved on by (k - 1) x 120 years (D84)."""
    if not 1 <= cycle <= MAX_CYCLE:
        raise ValueError("invalid cycle")
    q = Fraction(angles.normalize(moon_lon))
    n = int(q // angles.NAKSHATRA)
    elapsed_fraction = (q - n * angles.NAKSHATRA) / angles.NAKSHATRA
    first = rs.nakshatras[n].lord
    y = year_seconds(rs)
    start = birth - elapsed_fraction * rs.dasha_years[first] * y + (cycle - 1) * cycle_seconds(rs)
    out: list[Period] = []
    for i, lord in enumerate(_sequence_from(rs, first)):
        end = start + rs.dasha_years[lord] * y
        clip = cycle == 1 and i == 0
        out.append(Period(lord, 1, birth if clip else start, end, ABBR[lord], start, from_birth=clip, cycle=cycle))
        start = end
    return out


def cycle_at(rs: Ruleset, moon_lon: float, birth: Fraction, at: Fraction) -> int:
    """Which run of the sequence contains the instant `at` (1 before or during the first)."""
    first = mahadashas(rs, moon_lon, birth)
    if at < first[-1].end:
        return 1
    return min(MAX_CYCLE, 1 + int((at - first[0].full_start) // cycle_seconds(rs)))


def children(rs: Ruleset, parent: Period) -> list[Period]:
    """Nine sub-periods, starting from the parent's own lord, proportional to its years."""
    if parent.level >= MAX_DEPTH:
        raise ValueError("deepest level reached")
    total = sum(rs.dasha_years.values())  # 120
    start = parent.full_start
    out: list[Period] = []
    for lord in _sequence_from(rs, parent.lord):
        end = start + parent.length * Fraction(rs.dasha_years[lord], total)
        out.append(Period(lord, parent.level + 1, start, end, f"{parent.path}>{ABBR[lord]}", start, cycle=parent.cycle))
        start = end
    assert out[-1].end == parent.end  # exact by construction
    return out


def active_chain(rs: Ruleset, moon_lon: float, birth: Fraction, at: Fraction, depth: int = MAX_DEPTH) -> list[Period]:
    level = mahadashas(rs, moon_lon, birth, cycle_at(rs, moon_lon, birth, at))
    chain: list[Period] = []
    while True:
        current = next((p for p in level if p.full_start <= at < p.end), None)
        if current is None:
            return chain
        chain.append(current)
        if len(chain) >= depth:
            return chain
        level = children(rs, current)


def periods_at_path(rs: Ruleset, moon_lon: float, birth: Fraction, path: str | None, cycle: int = 1) -> list[Period]:
    """Timeline endpoint (FR-DSH-03): no path -> Mahadashas; 'Ju>Ve' -> its nine children (in `cycle`)."""
    level = mahadashas(rs, moon_lon, birth, cycle)
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
