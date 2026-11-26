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

from ..jyotish.bundle import InspectionBundle, InspectionSet


@cache
def _copy(locale: str = "en") -> dict[str, Any]:
    raw = yaml.safe_load(resources.files("pranix.library").joinpath(locale, "inspect.yaml").read_text("utf-8"))
    if raw.get("status") != "approved":
        raise ValueError("inspect wording is not approved")
    return dict(raw)


def summary(b: InspectionBundle, locale: str = "en") -> str:
    c = _copy(locale)
    p = b.placement
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
    g = _copy(locale)["glosses"]
    if b.target.ref in ("Rahu", "Ketu"):
        return str(g["node"])
    if b.placement.dignity == "debilitated":
        # D81 §3 wording names the other chart: the D9 on a D1 panel, the D1 on a D9 panel; no chart at sign level
        if b.level == "sign":
            return str(g["debilitated_sign_level"])
        return str(g["debilitated"]).format(other="D9" if b.chart == "d1" else "D1")
    return str(g[b.placement.dignity]) if b.placement.dignity in g else None


def with_text(s: InspectionSet, locale: str = "en") -> InspectionSet:
    bundles = {
        k: b.model_copy(
            update={
                "summary": summary(b, locale),
                "placement": b.placement.model_copy(update={"dignity_gloss": gloss(b, locale)}),
            }
        )
        for k, b in s.bundles.items()
    }
    return s.model_copy(update={"bundles": bundles})
