# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only lookups over one chart of the Master JSON (plan §4.1). No ephemeris calls.

`level` is "house" when the birth time is known and "sign" when it isn't (D56): at sign level a
planet may have no certain sign (sign is None, both options in flags.time_sensitive).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ..ephemeris.ruleset import Ruleset

Chart = Literal["d1", "d9"]
Level = Literal["house", "sign"]


def step(house: int, nth: int) -> int:
    """The nth house from `house`, counting inclusively (the 1st is the house itself, the 7th is opposite)."""
    return ((house - 1 + nth - 1) % 12) + 1


@dataclass(frozen=True)
class PlanetFacts:
    id: str
    sign: str | None
    house: int | None
    dignity: str | None
    deg_in_sign: float | None
    nakshatra: str | None
    retrograde: bool | None
    vargottama: bool | None


@dataclass(frozen=True)
class ChartContext:
    chart: Chart
    level: Level
    rs: Ruleset
    order: tuple[str, ...]  # planet ids in the engine's order (Sun ... Ketu)
    planets: Mapping[str, PlanetFacts]
    first_sign: str | None  # house one's sign; None at sign level
    options: Mapping[str, tuple[str, ...]]  # fact_id -> values that change during the day

    @classmethod
    def from_master(cls, master: Mapping[str, Any], chart: Chart, rs: Ruleset) -> ChartContext:
        known = bool(master["meta"]["birth_time_known"])
        block = master[chart]
        if block is None:
            raise ValueError("chart not available")  # the D9 needs a birth time (D56)
        planets = {}
        for p in block["planets"]:
            planets[p["id"]] = PlanetFacts(
                id=p["id"],
                sign=p.get("sign"),
                house=p.get("house") if known else None,
                dignity=p.get("dignity"),
                deg_in_sign=p.get("deg_in_sign"),
                nakshatra=p.get("nakshatra"),
                retrograde=p.get("retrograde"),
                vargottama=p.get("vargottama"),
            )
        lagna = block.get("lagna")
        options = {t["fact_id"]: tuple(t["values"]) for t in master["flags"]["time_sensitive"]}
        return cls(
            chart,
            "house" if known else "sign",
            rs,
            tuple(p["id"] for p in block["planets"]),
            planets,
            lagna["sign"] if (known and lagna) else None,
            options,
        )

    # --- signs and houses -------------------------------------------------------------------------
    def sign_index(self, sign: str) -> int:
        return self.rs.signs.index(sign)

    def lord_of(self, sign: str) -> str:
        return self.rs.sign_lords[self.sign_index(sign)]

    def house_sign(self, house: int) -> str:
        assert self.first_sign is not None
        return self.rs.signs[(self.sign_index(self.first_sign) + house - 1) % 12]

    def house_of_sign(self, sign: str) -> int:
        assert self.first_sign is not None
        return (self.sign_index(sign) - self.sign_index(self.first_sign)) % 12 + 1

    def occupants(self, house: int) -> list[str]:
        return [p for p in self.order if self.planets[p].house == house]

    def same_sign(self, sign: str) -> list[str]:
        return [p for p in self.order if self.planets[p].sign == sign]

    def sign_options(self, planet: str) -> tuple[str, ...] | None:
        return self.options.get(f"{planet.lower()}.sign")

    def nakshatra_options(self, planet: str) -> tuple[str, ...] | None:
        return self.options.get(f"{planet.lower()}.nakshatra")
