# SPDX-License-Identifier: AGPL-3.0-only
"""The words on an Inspector panel: the one-line summary, the calm dignity glosses (D81 §3), the
birth-minute note (D83) and the approved library lines (I5, D78).

The jyotish package returns data only; this layer adds approved wording from library/en/inspect.yaml,
so text people read is reviewed, digit-free (rule 2) and ready for other languages.
"""

from __future__ import annotations

from functools import cache
from importlib import resources
from typing import Any

import yaml

from ..jyotish.bundle import HouseAbout, InspectionBundle, InspectionSet, Line, MayChange


@cache
def _copy(locale: str = "en") -> dict[str, Any]:
    raw = yaml.safe_load(resources.files("pranix.library").joinpath(locale, "inspect.yaml").read_text("utf-8"))
    if raw.get("status") != "approved":
        raise ValueError("inspect wording is not approved")
    return dict(raw)


def _names(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def house_summary(b: InspectionBundle, locale: str = "en") -> str:
    """'House seven is Aquarius. It is empty, so it is read through its lord.' (prototype wording, approved)"""
    c = _copy(locale)
    t = c["summary"]
    assert b.house is not None
    occ = b.house.occupants
    empty = "house_target_empty_looked" if b.aspects_in else "house_target_empty"  # only when a planet looks at it
    rest = str(t["house_target_with"]).format(names=_names(occ)) if occ else str(t[empty])
    rising = str(t["house_target_rising"]) if b.house.house == 1 else ""
    word = c["house_words"][b.house.house - 1]
    return str(t["house_target"]).format(rising=rising, word=word, sign=b.house.sign, occupants=rest)


def summary(b: InspectionBundle, locale: str = "en") -> str:
    if b.target.kind == "house":
        return house_summary(b, locale)
    c = _copy(locale)
    p = b.placement
    assert p is not None
    planet = b.target.ref
    dig = f", {c['dignity_phrase'][p.dignity]}" if p.dignity else ""
    if p.sign is None:
        return str(c["summary"]["sign_uncertain"]).format(planet=planet, options=" or ".join(p.sign_options or []))
    if b.level == "house" and p.house is not None:
        return str(c["summary"]["house"]).format(
            planet=planet, ordinal=c["ordinals"][p.house - 1], sign=p.sign, dignity=dig
        )
    return str(c["summary"]["sign"]).format(planet=planet, sign=p.sign, dignity=dig)


def gloss(b: InspectionBundle, locale: str = "en") -> str | None:
    if b.placement is None:
        return None
    g = _copy(locale)["glosses"]
    if b.target.ref in ("Rahu", "Ketu"):
        return str(g["node"])
    if b.placement.dignity == "debilitated":
        # D81 §3 wording names the other chart: the D9 on a D1 panel, the D1 on a D9 panel; no chart at sign level
        if b.level == "sign":
            return str(g["debilitated_sign_level"])
        return str(g["debilitated"]).format(other="D9" if b.chart == "d1" else "D1")
    return str(g[b.placement.dignity]) if b.placement.dignity in g else None


def _options(opts: list[str], c: dict[str, Any]) -> str:
    m = c["minute"]
    if len(opts) == 2:
        return str(m["two"]).format(a=opts[0], b=opts[1])
    return str(m["many"]).format(first=opts[0], last=opts[-1])


def minute_note(changes: list[MayChange], locale: str = "en") -> str | None:
    """D83: one calm sentence per sign that could differ within the birth time's margin."""
    if not changes:
        return None
    c = _copy(locale)
    m = c["minute"]
    out = []
    for ch in changes:
        opts = _options(ch.options, c)
        if ch.what == "rising":
            out.append(str(m["rising_d1" if ch.chart == "d1" else "rising_d9"]).format(options=opts))
        else:
            out.append(str(m["planet_d9"]).format(planet=ch.ref, options=opts))
    return " ".join(out)


# ---------- I5: the approved Inspector library ----------

INSPECT_KINDS = ("houses", "planet_in_house", "lord_in_house", "signals", "bridge")
NODES = ("Rahu", "Ketu")
# Dignity order for the D1/D9 bridge lines ("gains dignity in the D9"): the classical scale, strongest first.
RANK = {"exalted": 6, "own": 5, "friend": 4, "neutral": 3, "enemy": 2, "debilitated": 1}


@cache
def _inspect_lib(locale: str = "en") -> dict[str, Any]:
    """Loaded on its own, not through insight.Library, so these entries never change the card library's
    version (part of every card's AI cache key)."""
    folder = resources.files("pranix.library").joinpath(locale, "reviewed")
    out: dict[str, Any] = {}
    for name in INSPECT_KINDS:
        f = folder.joinpath(f"{name}.yaml")
        out[name] = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) if f.is_file() else {}
    return out


class _Text:
    def __init__(self, locale: str, allow_drafts: bool) -> None:
        self.lib, self.allow = _inspect_lib(locale), allow_drafts

    def entry(self, *path: str) -> dict[str, Any] | None:
        node: Any = self.lib
        for p in path:
            if not isinstance(node, dict) or p not in node:
                return None
            node = node[p]
        ok = isinstance(node, dict) and (
            node.get("status") == "approved" or (self.allow and node.get("status") == "draft")
        )
        return node if ok else None

    def line(self, out: list[Line], id_: str, group: str, *path: str) -> None:
        e = self.entry(*path)
        if e is not None and isinstance(e.get("text"), str):
            out.append(Line(id=id_, group=group, text=e["text"]))


def _bridge(b: InspectionBundle) -> str | None:
    """Which bridge line fits this planet's D1 and D9 dignities (both panels speak of "the D9")."""
    p, o = b.placement, b.other_chart
    if p is None or o is None:
        return None
    if o.change == "none":
        return "bridge.node"
    if p.vargottama:
        return "bridge.vargottama"
    d1, d9 = (p.dignity, o.dignity) if b.chart == "d1" else (o.dignity, p.dignity)
    if d1 is None or d9 is None:
        return None
    if d9 in ("exalted", "own", "debilitated"):
        return f"bridge.{d9}_in_d9"
    if d1 == "debilitated" and d9 == "friend":
        return "bridge.debilitated_supported"
    if RANK[d9] == RANK[d1]:
        return "bridge.same_dignity"
    return "bridge.stronger_in_d9" if RANK[d9] > RANK[d1] else "bridge.softer_in_d9"


def lines(b: InspectionBundle, t: _Text) -> list[Line]:
    """The approved library lines that apply to this target, each under its Snapshot group. Facts come
    from the bundle (the engine's); only the words come from the library. Missing or unapproved entries
    are simply left out, so a panel never shows unreviewed text."""
    out: list[Line] = []
    sig = "signals"
    if b.target.kind == "house" and b.house is not None and b.lord is not None:
        h = b.house.house
        t.line(out, "lord_in_house", "lord", "lord_in_house", f"lord_{h}", f"house_{b.lord.house}")
        if b.lord_other_chart is not None:
            t.line(out, "bridge.lord_in_other_chart", "lord", "bridge", "bridge.lord_in_other_chart")
        occ = b.house.occupants
        if not occ:
            t.line(out, "house.empty", "occupants", sig, "house.empty")
        elif len(occ) >= 3:
            t.line(out, "house.stellium", "occupants", sig, "house.stellium")
        if b.aspects_in is not None:
            seen = "aspect.looked_at_by" if b.aspects_in else "aspect.none"
            t.line(out, seen, "lookedby", sig, seen)
        return out
    p = b.placement
    if p is None:
        return out
    planet = b.target.ref
    if p.house is not None:
        t.line(out, "planet_in_house", "summary", "planet_in_house", planet, f"house_{p.house}")
    if p.dignity in ("exalted", "own", "friend", "neutral"):  # enemy and debilitated carry the D81 gloss
        t.line(out, f"dignity.{p.dignity}", "placement", sig, f"dignity.{p.dignity}")
    if p.vargottama:
        t.line(out, "vargottama", "placement", sig, "vargottama")
    if p.retrograde and planet not in NODES:  # nodes always move backwards; not a signal
        t.line(out, "retrograde", "placement", sig, "retrograde")
    if b.houses_ruled and any(h.house == 1 for h in b.houses_ruled):
        t.line(out, "lord.rising", "rules", sig, "lord.rising")
    if b.sits_with and b.level == "house":
        t.line(out, "conjunction", "with", sig, "conjunction")
    d = b.dispositor
    if d is not None:
        key = {
            "final": "dispositor.final" if d.steps == [planet] else None,
            "exchange": "dispositor.exchange" if d.pair and planet in d.pair else None,
            "cycle": "dispositor.cycle" if d.cycle_members and planet in d.cycle_members else None,
            "stops_uncertain": "dispositor.stops_uncertain",
        }[d.end]
        if key:
            t.line(out, key, "chain", sig, key)
    link = _bridge(b)
    if link:
        t.line(out, link, "other", "bridge", link)
    return out


def about(b: InspectionBundle, t: _Text) -> HouseAbout | None:
    if b.target.kind != "house" or b.house is None:
        return None
    e = t.entry("houses", f"house_{b.house.house}")
    return HouseAbout(arena=e["arena"], healthy=e["healthy"], growth=e["growth"]) if e else None


def with_text(s: InspectionSet, locale: str = "en", allow_drafts: bool = False) -> InspectionSet:
    t = _Text(locale, allow_drafts)

    def dress(b: InspectionBundle) -> InspectionBundle:
        update: dict[str, object] = {
            "summary": summary(b, locale),
            "minute_note": minute_note(b.may_change, locale),
            "about": about(b, t),
            "lines": lines(b, t),
        }
        if b.placement is not None:
            update["placement"] = b.placement.model_copy(update={"dignity_gloss": gloss(b, locale)})
        return b.model_copy(update=update)

    bundles = {k: dress(b) for k, b in s.bundles.items()}
    return s.model_copy(update={"bundles": bundles, "minute_note": minute_note(s.may_change, locale)})
