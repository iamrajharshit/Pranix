# SPDX-License-Identifier: AGPL-3.0-only
"""D1 (rasi) and D9 (navamsa) charts, dignity, Atmakaraka (FR-CAL-01..05, FR-CAL-17)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from . import angles
from .ruleset import Ruleset
from .swe import Body

Dignity = Literal["exalted", "own", "friend", "neutral", "enemy", "debilitated"]
SEVEN = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")


def dignity(rs: Ruleset, planet: str, sign: int) -> Dignity | None:
    """Sign-based dignity with natural friendship only (D38). Nodes have none."""
    if planet not in SEVEN:
        return None
    if rs.exalted[planet] == sign:
        return "exalted"
    if rs.debilitated[planet] == sign:
        return "debilitated"
    if sign in rs.own[planet]:
        return "own"
    lord = rs.sign_lords[sign]
    rel = rs.friendship[planet]
    if lord in rel["friends"]:
        return "friend"
    if lord in rel["neutral"]:
        return "neutral"
    return "enemy"


@dataclass(frozen=True)
class D1Planet:
    id: str
    longitude: float
    sign: str
    deg_in_sign: float
    house: int
    retrograde: bool
    speed: float
    dignity: Dignity | None
    nakshatra: str
    pada: int
    vargottama: bool


@dataclass(frozen=True)
class Lagna:
    longitude: float
    sign: str
    deg_in_sign: float
    nakshatra: str
    pada: int
    vargottama: bool


@dataclass(frozen=True)
class D9Planet:
    id: str
    sign: str
    house: int
    retrograde: bool
    dignity: Dignity | None


def _lagna(rs: Ruleset, asc: float) -> Lagna:
    s = angles.sign_index(asc)
    return Lagna(
        longitude=asc,
        sign=rs.signs[s],
        deg_in_sign=angles.deg_in_sign(asc),
        nakshatra=rs.nakshatras[angles.nakshatra_index(asc)].name,
        pada=angles.pada(asc),
        vargottama=s == angles.d9_sign_index(asc),
    )


def build_d1(rs: Ruleset, bodies: list[Body], asc: float) -> dict[str, Any]:
    lagna_sign = angles.sign_index(asc)
    planets = []
    for b in bodies:
        s = angles.sign_index(b.longitude)
        planets.append(
            D1Planet(
                id=b.id,
                longitude=b.longitude,
                sign=rs.signs[s],
                deg_in_sign=angles.deg_in_sign(b.longitude),
                house=angles.whole_sign_house(s, lagna_sign),
                retrograde=b.retrograde,
                speed=b.speed,
                dignity=dignity(rs, b.id, s),
                nakshatra=rs.nakshatras[angles.nakshatra_index(b.longitude)].name,
                pada=angles.pada(b.longitude),
                vargottama=s == angles.d9_sign_index(b.longitude),
            )
        )
    return {
        "lagna": asdict(_lagna(rs, asc)),
        "houses": [{"house": h + 1, "sign": rs.signs[(lagna_sign + h) % 12]} for h in range(12)],
        "planets": [asdict(p) for p in planets],
    }


def build_d9(rs: Ruleset, bodies: list[Body], asc: float) -> dict[str, Any]:
    lagna9 = angles.d9_sign_index(asc)
    planets = []
    for b in bodies:
        s9 = angles.d9_sign_index(b.longitude)
        planets.append(
            D9Planet(
                id=b.id,
                sign=rs.signs[s9],
                house=angles.whole_sign_house(s9, lagna9),
                retrograde=b.retrograde,
                dignity=dignity(rs, b.id, s9),
            )
        )
    return {
        "lagna": {"sign": rs.signs[lagna9]},
        "houses": [{"house": h + 1, "sign": rs.signs[(lagna9 + h) % 12]} for h in range(12)],
        "planets": [asdict(p) for p in planets],
    }


def atmakaraka(bodies: list[Body]) -> str:
    """7-karaka scheme: highest degree-in-sign among Sun..Saturn (FR-CAL-04)."""
    seven = [b for b in bodies if b.id in SEVEN]
    return max(seven, key=lambda b: angles.deg_in_sign(b.longitude)).id
