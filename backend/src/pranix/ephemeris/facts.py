# SPDX-License-Identifier: AGPL-3.0-only
"""Master.facts: semantic, chart-independent IDs for evidence chips (FR-CAL-15, D52).

IDs never depend on the chart (`moon.nakshatra`, not `fact_17`), so cached insight text
that cites them stays valid for every chart sharing its cache key. A fact is emitted
only when its target exists in this chart (no houses or D9 without a birth time).
"""

from __future__ import annotations

from typing import Any

ORD = {1: "1st", 2: "2nd", 3: "3rd"}


def _ord(n: int) -> str:
    return ORD.get(n, f"{n}th")


def _f(label: str, kind: str, ref: str, chart: str) -> dict[str, Any]:
    return {"label": label, "target": {"kind": kind, "ref": ref, "chart": chart}}


def build(m: dict[str, Any]) -> dict[str, dict[str, Any]]:
    known = m["meta"]["birth_time_known"]
    chart = "d1" if known else "none"
    f: dict[str, dict[str, Any]] = {}
    if known:
        lg = m["d1"]["lagna"]
        f["lagna.sign"] = _f(f"{lg['sign']} rising", "lagna", lg["sign"], "d1")
    for p in m["d1"]["planets"]:
        if p["sign"]:
            f[f"{p['id'].lower()}.sign"] = _f(f"{p['id']} in {p['sign']}", "planet", p["id"], chart)
        if known:
            f[f"{p['id'].lower()}.house"] = _f(
                f"{p['id']} in the {_ord(p['house'])} house", "house", str(p["house"]), "d1"
            )
    if m["nakshatra"]:
        n = m["nakshatra"]["name"]
        f["moon.nakshatra"] = _f(f"Moon in {n}", "nakshatra", n, chart)
    naming = m.get("naming")
    if naming and naming["pada"]:
        f["naming.pada"] = _f(
            f"{naming['nakshatra']}, quarter {naming['pada']}", "syllable", f"pada:{naming['pada']}", "none"
        )
    if m["purpose"]["atmakaraka"]:
        ak = m["purpose"]["atmakaraka"]
        f["ak.planet"] = _f(f"Soul planet {ak}", "planet", ak, chart)
    if m.get("ishta_devta"):
        d = m["ishta_devta"]
        f["deity.planet"] = _f(f"{d['deciding_planet']} points to {d['main']}", "planet", d["deciding_planet"], "d9")
    if m.get("colors"):
        for i, s in enumerate(m["colors"]["swatches"], 1):
            f[f"colors.swatch_{i}"] = _f(s["name"], "colour", s["name"], "none")
    if m.get("days"):
        for i, d in enumerate(m["days"]["items"], 1):
            f[f"days.item_{i}"] = _f(d["weekday"], "weekday", d["weekday"], "none")
    chain = m["dasha"]["active_chain"]
    if chain:
        f["dasha.maha"] = _f(f"{chain[0]['lord']} period", "dasha", chain[0]["path"], "none")
        if len(chain) > 1:
            f["dasha.antar"] = _f(f"{chain[1]['lord']} sub-period", "dasha", chain[1]["path"], "none")
    return dict(sorted(f.items()))
