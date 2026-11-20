# SPDX-License-Identifier: AGPL-3.0-only
"""Elements %, doshas % and chakra classes (Requirements §6.4–6.6). HEURISTIC, disclosed as ours.

Arithmetic is exact (Fractions); percentages are integers that always sum to 100
(largest-remainder rounding).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from . import angles
from .charts import dignity
from .ruleset import Ruleset
from .swe import Body


def percentages(scores: dict[str, Fraction]) -> dict[str, int]:
    total = sum(scores.values())
    if total == 0:
        raise ValueError("no weight")
    exact = {k: v * 100 / total for k, v in scores.items()}
    floors = {k: int(v) for k, v in exact.items()}
    left = 100 - sum(floors.values())
    # Largest remainder; ties broken by key order for determinism.
    for k in sorted(exact, key=lambda k: (-(exact[k] - floors[k]), k))[:left]:
        floors[k] += 1
    return floors


def _pos(bodies: list[Body]) -> dict[str, float]:
    return {b.id: b.longitude for b in bodies}


def elements(rs: Ruleset, bodies: list[Body], asc: float | None) -> dict[str, Any]:
    cfg = rs.raw["elements"]
    sign_el: list[str] = cfg["sign_element"]
    planet_el: dict[str, str] = cfg["planet_element"]
    w = cfg["weights"]
    factor = {k: Fraction(v) for k, v in cfg["dignity_factor"].items()}
    t: dict[str, Fraction] = {e: Fraction(0) for e in ("Fire", "Earth", "Air", "Water", "Ether")}
    contributions: list[dict[str, Any]] = []
    if asc is not None:  # unknown time (B5.2): no Lagna term
        el = sign_el[angles.sign_index(asc) % 4]
        t[el] += w["lagna"]
        contributions.append({"source": "lagna", "element": el, "weight": str(Fraction(w["lagna"]))})
    pos = _pos(bodies)
    for p, own_el in planet_el.items():
        s = angles.sign_index(pos[p])
        wt = Fraction(w.get(p, w["default"]))
        d = dignity(rs, p, s)
        assert d is not None
        a = wt / 2
        b = wt / 2 * factor[d]
        t[sign_el[s % 4]] += a
        t[own_el] += b
        contributions.append({"source": p, "element": sign_el[s % 4], "weight": str(a)})
        contributions.append({"source": p, "element": own_el, "weight": str(b), "dignity": d})
    return {"percent": percentages(t), "contributions": contributions}


def doshas(rs: Ruleset, bodies: list[Body], asc: float | None) -> dict[str, Any]:
    cfg = rs.raw["doshas"]
    sign_el: list[str] = rs.raw["elements"]["sign_element"]
    weights = cfg["body_weights_known"] if asc is not None else cfg["body_weights_unknown"]
    share = Fraction(cfg["sign_lord_share"])
    t: dict[str, Fraction] = {"Vata": Fraction(0), "Pitta": Fraction(0), "Kapha": Fraction(0)}
    pos = _pos(bodies)
    for body, wv in weights.items():
        w = Fraction(wv)
        lon = asc if body == "lagna" else pos[body]
        assert lon is not None
        s = angles.sign_index(lon)
        for dosha, part in cfg["sign_element_dosha"][sign_el[s % 4]].items():
            t[dosha] += w * Fraction(part)
        lord = rs.sign_lords[s]
        if lord in cfg["tridoshic"]:
            for k in t:
                t[k] += w * share / 3
        else:
            t[cfg["planet_dosha"][lord]] += w * share
    pct = percentages(t)
    ranked = sorted(pct.items(), key=lambda kv: (-kv[1], kv[0]))
    label = dosha_label([v for _, v in ranked], cfg["label"])
    return {"percent": pct, "label": label, "dominant": [k for k, _ in ranked[: 1 if label == "mono" else 2]]}


def dosha_label(ranked: list[int], lab: dict[str, Any]) -> str:
    """Percentages high to low. mono: top >= mono_min and leads by mono_gap. dual (D67, owner 20 Nov 2026):
    the second leads the third by the same gap. Otherwise tridoshic, e.g. 35/35/30 or 40/35/25."""
    if ranked[0] >= lab["mono_min"] and ranked[0] - ranked[1] >= lab["mono_gap"]:
        return "mono"
    if ranked[1] - ranked[2] >= lab["mono_gap"]:
        return "dual"
    return "tridoshic"


def chakras(rs: Ruleset, bodies: list[Body]) -> list[dict[str, Any]]:
    pos = _pos(bodies)
    out = []
    for c in rs.raw["chakras"]:
        d = dignity(rs, c["planet"], angles.sign_index(pos[c["planet"]]))
        assert d is not None
        out.append({"id": c["id"], "planet": c["planet"], "dignity": d, "class": rs.raw["chakra_class"][d]})
    return out
