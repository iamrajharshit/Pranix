# SPDX-License-Identifier: AGPL-3.0-only
"""The public view of the Master JSON (D86 item 3, owner sign-off 28 Nov 2026).

The engine's Master JSON stays whole inside the server (golden tests, caching, the Inspector and
the cards all use it). What leaves for the browser is this view: only what the screens read, and
no more precision than they show. A chart still encodes its birth moment (that is what a chart is),
so the chart id stays the real protection; this keeps the answer as small as the screens allow.
"""

from __future__ import annotations

import copy
from typing import Any

from ..ephemeris.angles import to_arcminute

META_DROP = ("engine_version", "swisseph_version", "rulesets", "node_type", "house_system")  # A6: on /version


def public_master(master: dict[str, Any]) -> dict[str, Any]:
    m = copy.deepcopy(master)
    for chart in ("d1", "d9"):
        c = m.get(chart)
        if not c:
            continue
        for p in c.get("planets") or []:
            p.pop("longitude", None)  # A1
            p.pop("speed", None)  # A2: the screens read `retrograde`
            if "deg_in_sign" in p:
                p["deg_in_sign"] = to_arcminute(p["deg_in_sign"])  # B1
        lagna = c.get("lagna")
        if lagna:
            lagna.pop("longitude", None)
            if "deg_in_sign" in lagna:
                lagna["deg_in_sign"] = to_arcminute(lagna["deg_in_sign"])
    for body in (m.get("identity") or {}).values():
        if isinstance(body, dict) and "deg_in_sign" in body:
            body["deg_in_sign"] = to_arcminute(body["deg_in_sign"])
    (m.get("elements") or {}).pop("contributions", None)  # A3
    if m.get("ishta_devta"):
        m["ishta_devta"].pop("working", None)  # A4
    naming = m.get("naming") or {}
    naming.pop("nakshatra_number", None)  # A5
    for alt in naming.get("alternatives") or []:  # unknown birth time: both possible stars
        alt.pop("nakshatra_number", None)
    meta = m["meta"]
    for k in META_DROP:
        meta.pop(k, None)
    meta["ayanamsa_value"] = to_arcminute(meta.get("ayanamsa_value"))  # B2
    for period in (m.get("dasha") or {}).get("active_chain") or []:
        if period.get("from_birth"):
            period["start"] = None  # C1: never the birth instant; the screen says "from birth"
    return m
