# SPDX-License-Identifier: AGPL-3.0-only
"""Reviewed background knowledge for a card's AI reading (D80).

The engine's facts say *what* a chart has (Moon in Rohini); the reviewed deep library says what
that tends to mean (core nature, gifts, growth edges, work, relationships, a practice). Only
entries the library may serve are included (approved in production), so the AI words its reading
from text the owner has reviewed. Kinds with no approved entries yet are skipped,
and light up on their own once they are reviewed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .facts import facts_for
from .library import Library


def _stars(module: str, m: Mapping[str, Any]) -> list[str]:
    f = facts_for(module, m)
    if module == "birthstar":
        return [f["star"]] if "star" in f else list(f.get("star_options") or [])
    if module == "nameletter":
        return [f["star"], *(f.get("other_star") or [])]
    if module == "identity":
        nk = m.get("nakshatra")
        if nk:
            return [nk["name"]]
        for t in m["flags"]["time_sensitive"]:
            if t["fact_id"] == "moon.nakshatra":
                return list(t["values"])
    return []


def _signs(module: str, m: Mapping[str, Any]) -> list[str]:
    if module != "identity":
        return []
    ident = m["identity"]
    out = [ident["lagna"]["sign"]] if ident.get("lagna") else []
    for body in ("moon", "sun"):
        sign = (ident.get(body) or {}).get("sign")
        if sign:
            out.append(sign)
    return out


def _planets(module: str, m: Mapping[str, Any]) -> list[str]:
    if module in ("motive", "growth"):
        return [m["purpose"]["atmakaraka"]]
    if module == "season":
        return [p["lord"] for p in (m["dasha"]["active_chain"] or [])[:2]]
    if module == "deity" and m.get("ishta_devta"):
        return [m["ishta_devta"]["deciding_planet"]]
    if module in ("colors", "days"):
        key = "swatches" if module == "colors" else "items"
        return sorted({p for item in m[module][key] for p in item["planets"]})
    return []


def knowledge_for(module: str, m: Mapping[str, Any], lib: Library) -> dict[str, dict[str, dict[str, str]]]:
    out: dict[str, dict[str, dict[str, str]]] = {}
    for group, kind, names in (
        ("stars", "nakshatra_deep", _stars(module, m)),
        ("signs", "sign_deep", _signs(module, m)),
        ("planets", "planet_deep", _planets(module, m)),
    ):
        found = {n: e for n in dict.fromkeys(names) if (e := lib.deep(kind, n))}
        if found:
            out[group] = found
    return out
