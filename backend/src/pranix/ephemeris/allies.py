# SPDX-License-Identifier: AGPL-3.0-only
"""Deity (Ishta Devta), power colours, power days and naming syllables.

FR-CAL-05, FR-CAL-12, FR-CAL-13, FR-CAL-14; decisions D34–D37, D40, D54.
All deterministic from the chart; no LLM.
"""

from __future__ import annotations

from typing import Any

from . import angles
from .charts import SEVEN, atmakaraka, dignity
from .ruleset import Ruleset, load_table
from .swe import Body

ISHTA = "ishta-core@1"
COLORS = "colors-core@1"
DAYS = "days-core@1"
NAMING = "naming-core@1"


def _lon(bodies: list[Body], pid: str) -> float:
    return next(b.longitude for b in bodies if b.id == pid)


# ---------- Deity (Jaimini, D34–D36) ----------


def ishta_devta(rs: Ruleset, bodies: list[Body]) -> dict[str, Any]:
    """AK -> its D9 sign (Karakamsa) -> 12th sign from it -> occupants in D9, else that sign's lord."""
    t = load_table(ISHTA).data
    ak = atmakaraka(bodies)
    karakamsa = angles.d9_sign_index(_lon(bodies, ak))
    twelfth = (karakamsa + 11) % 12
    occupants = [b.id for b in bodies if angles.d9_sign_index(b.longitude) == twelfth]
    rank = {d: i for i, d in enumerate(t["dignity_rank"])}
    tie = {p: i for i, p in enumerate(t["tie_order"])}

    def strength(pid: str) -> tuple[int, int]:
        # Nodes have no dignity: they rank as neutral, then the fixed tie list (D68, owner 20 Nov 2026).
        d = dignity(rs, pid, twelfth) or t["node_dignity"]
        return rank[d], tie[pid]

    if occupants:
        deciding = min(occupants, key=strength)
        branch = "occupant" if len(occupants) == 1 else "strongest_occupant"
    else:
        deciding = rs.sign_lords[twelfth]
        branch = "sign_lord"
    entry = t["deities"][deciding]
    return {
        "main": entry["main"],
        "others": list(entry["others"][: t["others_shown"]]),
        "deciding_planet": deciding,
        "working": {
            "atmakaraka": ak,
            "karakamsa": rs.signs[karakamsa],
            "twelfth": rs.signs[twelfth],
            "occupants": occupants,
            "branch": branch,
        },
    }


# ---------- Colours and days (D37, D40, D54) ----------


def deciding_planets(rs: Ruleset, bodies: list[Body], asc: float | None) -> list[tuple[str, list[str]]]:
    """Ordered distinct planets with the roles that brought them in."""
    roles: list[tuple[str, str]] = []
    if asc is not None:
        roles.append(("lagna_lord", rs.sign_lords[angles.sign_index(asc)]))
    roles.append(("moon_sign_lord", rs.sign_lords[angles.sign_index(_lon(bodies, "Moon"))]))
    if asc is None:
        roles.append(("sun_sign_lord", rs.sign_lords[angles.sign_index(_lon(bodies, "Sun"))]))
    roles.append(("atmakaraka", atmakaraka(bodies)))
    out: list[tuple[str, list[str]]] = []
    for role, planet in roles:
        assert planet in SEVEN  # sign lords and the 7-karaka AK are never nodes
        for p, rl in out:
            if p == planet:
                rl.append(role)
                break
        else:
            out.append((planet, [role]))
    return out


def colors(rs: Ruleset, bodies: list[Body], asc: float | None) -> dict[str, Any]:
    t = load_table(COLORS).data
    planets = deciding_planets(rs, bodies, asc)
    swatches: list[dict[str, Any]] = []

    def add(name: str, planet: str, roles: list[str], kind: str) -> None:
        for s in swatches:
            if s["name"] == name:  # duplicate name: keep the first, list every planet
                if planet not in s["planets"]:
                    s["planets"].append(planet)
                s["roles"].extend(r for r in roles if r not in s["roles"])
                return
        swatches.append(
            {
                "name": name,
                "hex": t["hex"][name],
                "planets": [planet],
                "roles": list(roles),
                "kind": kind,
                "dark": name in t["dark"],
            }
        )

    for p, rl in planets:
        add(t["planets"][p]["main"][0], p, rl, "main")
    # Fallback (§3a): next main colour of the first planet, then of the next planets, then a variant.
    if len(swatches) < t["min"]:
        for p, rl in planets:
            for name in t["planets"][p]["main"][1:]:
                if len(swatches) < t["min"] and all(s["name"] != name for s in swatches):
                    add(name, p, rl, "main")
    if len(swatches) < t["min"]:
        p, rl = planets[0]
        for name in t["planets"][p]["variants"]:
            if len(swatches) < t["min"] and all(s["name"] != name for s in swatches):
                add(name, p, rl, "variant")
    return {"swatches": swatches[: t["max"]]}


def days(rs: Ruleset, bodies: list[Body], asc: float | None) -> dict[str, Any]:
    t = load_table(DAYS).data
    items = [{"weekday": t["weekday"][p], "planets": [p], "roles": rl} for p, rl in deciding_planets(rs, bodies, asc)]
    return {"items": items}


# ---------- Naming syllables (D47, D54) ----------


def naming_for(nak_index: int) -> dict[str, Any]:
    row = load_table(NAMING).data["nakshatras"][nak_index]
    return {
        "nakshatra": row["nakshatra"],
        "nakshatra_number": row["number"],
        "syllables": [dict(s) for s in row["syllables"]],
    }


def naming(moon_lon: float, with_pada: bool) -> dict[str, Any]:
    out = naming_for(angles.nakshatra_index(moon_lon))
    out["pada"] = angles.pada(moon_lon) if with_pada else None
    out["variant"] = NAMING
    out["alternatives"] = []
    return out
