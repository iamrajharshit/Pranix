# SPDX-License-Identifier: AGPL-3.0-only
"""Per-card facts for the AI (D80): richer than before, still de-identified.

Never a name, date, time, place, coordinate, degree or any digit: houses are ordinal words, and
facts that changed during an unknown birth day are passed as options (D56), never chosen.
These facts are also the meaning part of the cache key, so equal facts share one AI answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

Master = Mapping[str, Any]
ORD = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
       "eleventh", "twelfth")  # fmt: skip


def word(n: int | None) -> str | None:
    return ORD[n - 1] if n else None


def _ts(m: Master, fact_id: str) -> list[str] | None:
    for t in m["flags"]["time_sensitive"]:
        if t["fact_id"] == fact_id:
            return list(t["values"])
    return None


def planet(m: Master, pid: str | None) -> dict[str, Any] | None:
    """Sign, dignity and house (as a word) of a planet in D1; only what is certain."""
    if not pid or not m.get("d1"):
        return None
    for p in m["d1"]["planets"]:
        if p["id"] == pid:
            out = {"planet": pid, "sign": p.get("sign"), "dignity": p.get("dignity"), "house": word(p.get("house"))}
            if p.get("retrograde") and pid not in ("Rahu", "Ketu"):
                out["retrograde"] = True
            if p.get("vargottama"):
                out["vargottama"] = True  # same sign in D1 and D9
            return {k: v for k, v in out.items() if v is not None}
    return None


def _identity(m: Master) -> dict[str, Any]:
    ident = m["identity"]
    lagna = ident["lagna"]
    return {
        "rising": lagna["sign"] if lagna else None,
        "rising_lord": planet(m, lagna["lord"]) if lagna else None,
        "moon": planet(m, "Moon") or {"sign_options": _ts(m, "moon.sign")},
        "sun": planet(m, "Sun"),
        "birth_time_known": m["meta"]["birth_time_known"],
    }


def _birthstar(m: Master) -> dict[str, Any]:
    n = m["nakshatra"]
    if n is None:
        return {"star_options": _ts(m, "moon.nakshatra"), "birth_time_known": m["meta"]["birth_time_known"]}
    return {
        "star": n["name"],
        "quarter": word(n["pada"]),
        "symbol": n["symbol"],
        "deity": n["deity"],
        "star_lord": planet(m, n["lord"]) or {"planet": n["lord"]},
        "moon": planet(m, "Moon"),
    }


def _nameletter(m: Master) -> dict[str, Any]:
    nm = m["naming"]
    state = "known" if nm["pada"] else ("changed" if nm["alternatives"] else "unknown")
    mine = next((s["latin"] for s in nm["syllables"] if s["pada"] == nm["pada"]), None)
    return {
        "star": nm["nakshatra"],
        "quarter": word(nm["pada"]),
        "your_sound": mine,
        "sounds": [s["latin"] for s in nm["syllables"]],
        "state": state,
        "other_star": [a["nakshatra"] for a in nm["alternatives"]] or None,
    }


def _elements(m: Master) -> dict[str, Any]:
    pct = m["elements"]["percent"]
    order = sorted(pct, key=lambda k: (-pct[k], k))
    return {"strongest": order[:2], "quietest": order[-1]}


def _motive(m: Master) -> dict[str, Any]:
    axis = m["purpose"]["rahu_ketu_axis"]
    return {
        "soul_planet": planet(m, m["purpose"]["atmakaraka"]) or {"planet": m["purpose"]["atmakaraka"]},
        "growth_house": word(axis["rahu_house"]) if axis else None,
        "natural_house": word(axis["ketu_house"]) if axis else None,
    }


def _season(m: Master) -> dict[str, Any]:
    chain = m["dasha"]["active_chain"] or []
    return {
        "period": (planet(m, chain[0]["lord"]) or {"planet": chain[0]["lord"]}) if chain else None,
        "sub_period": (planet(m, chain[1]["lord"]) or {"planet": chain[1]["lord"]}) if len(chain) > 1 else None,
    }


def _growth(m: Master) -> dict[str, Any]:
    axis = m["purpose"]["rahu_ketu_axis"]
    return {
        "quiet_centres": [c["id"] for c in m["chakras"] or [] if c["class"] == "low_activity"],
        "growth_house": word(axis["rahu_house"]) if axis else None,
        "soul_planet": m["purpose"]["atmakaraka"],
    }


def _deity(m: Master) -> dict[str, Any]:
    d = m["ishta_devta"]
    return {
        "deity": d["main"],
        "other_forms": d["others"],
        "deciding_planet": d["deciding_planet"],
        "soul_planet": m["purpose"]["atmakaraka"],
        "depends_on_exact_time": bool(d["time_sensitive"]),
    }


def _colors(m: Master) -> dict[str, Any]:
    return {
        "colours": [
            {"colour": s["name"], "planets": s["planets"], "roles": s["roles"]} for s in m["colors"]["swatches"]
        ]
    }


def _days(m: Master) -> dict[str, Any]:
    return {"days": [{"day": d["weekday"], "planets": d["planets"], "roles": d["roles"]} for d in m["days"]["items"]]}


def facts_for(module: str, m: Master) -> dict[str, Any]:
    if module == "identity":
        return _identity(m)
    if module == "birthstar":
        return _birthstar(m)
    if module == "nameletter":
        return _nameletter(m)
    if module == "elements":
        return _elements(m)
    if module == "doshas":
        return {"pattern": m["doshas"]["label"], "leading": m["doshas"]["dominant"]}
    if module == "chakras":
        return {c["id"]: c["class"] for c in m["chakras"]}
    if module == "motive":
        return _motive(m)
    if module == "season":
        return _season(m)
    if module == "growth":
        return _growth(m)
    if module == "deity":
        return _deity(m)
    if module == "colors":
        return _colors(m)
    if module == "days":
        return _days(m)
    raise ValueError(module)
