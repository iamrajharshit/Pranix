# SPDX-License-Identifier: AGPL-3.0-only
"""The words on an Inspector panel: the one-line summary and the calm dignity glosses (D81 §3).

The jyotish package returns data only; this layer adds approved wording from library/en/inspect.yaml,
so text people read is reviewed, digit-free (rule 2) and ready for other languages.
"""

from __future__ import annotations

from functools import cache
from importlib import resources
from typing import Any

import yaml

from ..jyotish.bundle import InspectionBundle, InspectionSet, MayChange


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


def with_text(s: InspectionSet, locale: str = "en") -> InspectionSet:
    def dress(b: InspectionBundle) -> InspectionBundle:
        update: dict[str, object] = {"summary": summary(b, locale), "minute_note": minute_note(b.may_change, locale)}
        if b.placement is not None:
            update["placement"] = b.placement.model_copy(update={"dignity_gloss": gloss(b, locale)})
        return b.model_copy(update=update)

    bundles = {k: dress(b) for k, b in s.bundles.items()}
    return s.model_copy(update={"bundles": bundles, "minute_note": minute_note(s.may_change, locale)})
