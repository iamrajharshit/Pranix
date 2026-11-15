# SPDX-License-Identifier: AGPL-3.0-only
"""Curated card builders for the twelve dashboard modules (FR-INS-07, FR-DASH).

Text comes only from library entries and engine facts; there are no numerals in any text
(numbers on screen come from the Master JSON). Every card passes the same validators as
AI-phrased text. Unknown birth time follows the certain-only rule (D56).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .library import Library, LibraryGap

MODULES = (
    "identity",
    "birthstar",
    "nameletter",
    "elements",
    "doshas",
    "chakras",
    "motive",
    "season",
    "growth",
    "deity",
    "colors",
    "days",
)
DETERMINISTIC = frozenset({"birthstar", "nameletter", "deity", "colors", "days"})
SYNTHESIS = frozenset(MODULES) - DETERMINISTIC
PROMPT_VERSION = "library@1"
ORDINAL = {1: "first", 2: "second", 3: "third", 4: "fourth"}
Master = Mapping[str, Any]


def _card(
    module: str,
    headline: str,
    summary: str,
    detail: str,
    sections: list[dict[str, Any]],
    fact_ids: list[str],
    master: Master,
    entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    card: dict[str, Any] = {
        "module_id": module,
        "headline": headline,
        "summary": summary,
        "detail": detail,
        "sections": [s for s in sections if s["items"]][:4],
        "badge": "curated",
        "fact_ids": [f for f in fact_ids if f in master["facts"]],
        "state": "ready",
        "reason": None,
        "degraded": False,
        "prompt_version": PROMPT_VERSION,
    }
    if entries is not None:
        card["entries"] = entries[:4]
    return card


def unavailable(module: str, headline: str) -> dict[str, Any]:
    return {
        "module_id": module,
        "headline": headline,
        "summary": "This card needs your birth time to be accurate, so we have left it out.",
        "detail": "",
        "sections": [],
        "badge": "curated",
        "fact_ids": [],
        "state": "unavailable",
        "reason": "BIRTH_TIME_REQUIRED",
        "degraded": False,
        "prompt_version": PROMPT_VERSION,
    }


def error_card(module: str) -> dict[str, Any]:
    return {
        "module_id": module,
        "headline": "This card did not load",
        "summary": "We could not prepare this reading just now.",
        "detail": "",
        "sections": [],
        "badge": "curated",
        "fact_ids": [],
        "state": "error",
        "reason": None,
        "degraded": True,
        "prompt_version": PROMPT_VERSION,
    }


def _ts(master: Master, fact_id: str) -> list[str] | None:
    for t in master["flags"]["time_sensitive"]:
        if t["fact_id"] == fact_id:
            return list(t["values"])
    return None


def _join(*parts: str) -> str:
    return " ".join(p.strip() for p in parts if p and p.strip())


def _planet(p: str) -> str:
    return f"the {p}" if p in ("Sun", "Moon") else p


def _list(items: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _sec(kind: str, items: list[str]) -> dict[str, Any]:
    return {"kind": kind, "items": [i for i in items if i][:3]}


# ---------- Constellation I: who you are ----------


def identity(m: Master, lib: Library) -> dict[str, Any]:
    known = m["meta"]["birth_time_known"]
    moon_sign = m["identity"]["moon"]["sign"] if m["identity"]["moon"] else None
    sun_sign = m["identity"]["sun"]["sign"] if m["identity"]["sun"] else None
    moon_opts = _ts(m, "moon.sign")
    moon_label = moon_sign or " or ".join(moon_opts or [])
    moon_e = lib.get("signs", moon_sign) if moon_sign else None
    sun_e = lib.get("signs", sun_sign) if sun_sign else None
    if known:
        lagna = m["identity"]["lagna"]["sign"]
        le = lib.get("signs", lagna)
        headline = f"{lagna} rising, Moon in {moon_label}"
        summary = _join(le["rising"], moon_e["moon"] if moon_e else "")
        detail = _join(
            le["rising"],
            moon_e["moon"] if moon_e else "",
            sun_e["sun"] if sun_e else "",
            "Together these three describe how you meet the world, what you need inside, and the energy at your core.",
        )
        strengths = list(le["strengths"])
    else:
        headline = f"Moon in {moon_label}, Sun in {sun_sign or 'two signs'}"
        summary = _join(
            moon_e["moon"] if moon_e else "Your Moon changed sign during your birth day.", sun_e["sun"] if sun_e else ""
        )
        detail = _join(summary, "Your rising sign needs a birth time, so this reading leaves it out.")
        strengths = list(moon_e["strengths"]) if moon_e else []
    sections = [
        _sec("strengths", strengths),
        _sec("watch_points", list(moon_e["watch"])[:2] if moon_e else []),
        _sec("try_this", list(sun_e["try"])[:2] if sun_e else []),
    ]
    return _card("identity", headline, summary, detail, sections, ["lagna.sign", "moon.sign", "sun.sign"], m)


def birthstar(m: Master, lib: Library) -> dict[str, Any]:
    n = m["nakshatra"]
    if n is None:
        a, b = _ts(m, "moon.nakshatra") or ["", ""]
        ea, eb = lib.get("nakshatras", a), lib.get("nakshatras", b)
        return _card(
            "birthstar",
            f"{a} or {b}",
            f"The Moon moved from {a} into {b} on your birth day, so both stars are shown.",
            _join(ea["essence"], eb["essence"], "A birth time would tell us which one is yours."),
            [_sec("about_star", [f"{a}: {ea['strength']}", f"{b}: {eb['strength']}"])],
            [],
            m,
        )
    e = lib.get("nakshatras", n["name"])
    quarter = f" You were born in its {ORDINAL[n['pada']]} quarter." if n["pada"] else ""
    detail = _join(
        e["essence"],
        f"Its symbol is the {n['symbol'].lower()}, its deity is {n['deity']}, "
        f"and its ruling planet is {n['lord']}.{quarter}",
        f"At its best it shows up as: {e['strength'].lower()}. It can also mean: {e['watch'].lower()}.",
    )
    sections = [
        _sec("about_star", [f"Symbol: {n['symbol']}", f"Deity: {n['deity']}", f"Ruling planet: {n['lord']}"]),
        _sec("strengths", [e["strength"]]),
        _sec("watch_points", [e["watch"]]),
    ]
    return _card(
        "birthstar", f"Born under {n['name']}", e["essence"], detail, sections, ["moon.nakshatra", "naming.pada"], m
    )


def nameletter(m: Master, lib: Library) -> dict[str, Any]:
    nm = m["naming"]
    text = lib.get("naming")
    if nm["pada"]:
        state = text["known"]
    elif nm["alternatives"]:
        state = text["changed"]
    else:
        state = text["unknown"]
    entries = []
    for s in nm["syllables"]:
        mine = nm["pada"] == s["pada"]
        entries.append(
            {
                "ref": f"pada:{s['pada']}",
                "title": f"{s['latin']} ({s['deva']})",
                "text": f"The {ORDINAL[s['pada']]} quarter of {nm['nakshatra']}."
                + (" This is your quarter." if mine else ""),
                "tags": ["yours"] if mine else [],
            }
        )
    sections = [_sec("tradition", [text["intro"]])]
    for alt in nm["alternatives"]:
        sections.append(
            _sec(
                "variant",
                [f"{alt['nakshatra']}: " + ", ".join(f"{s['latin']} ({s['deva']})" for s in alt["syllables"])],
            )
        )
    head = f"Sounds of {nm['nakshatra']}"
    return _card(
        "nameletter",
        head,
        _join(text["intro"], state),
        _join(text["intro"], state),
        sections,
        ["naming.pada", "moon.nakshatra"],
        m,
        entries,
    )


# ---------- Constellation II: your nature ----------


def elements(m: Master, lib: Library) -> dict[str, Any]:
    if m["elements"] is None:
        return unavailable("elements", "Your elements")
    pct = m["elements"]["percent"]
    ranked = sorted(pct, key=lambda k: (-pct[k], k))
    top, low = ranked[0], ranked[-1]
    te, le = lib.get("nature", "elements", top), lib.get("nature", "elements", low)
    second = lib.get("nature", "elements", ranked[1])
    detail = _join(
        te["high"],
        second["high"].replace("runs strong", "also runs well"),
        le["low"],
        "These proportions are our own way of summarising the chart, not a classical measure.",
    )
    return _card(
        "elements",
        f"{top} leads your elements",
        _join(te["high"], le["low"]),
        detail,
        [
            _sec("strengths", [f"{top} energy", f"{ranked[1]} support"]),
            _sec("try_this", [f"Bring a little more {low.lower()} into your week"]),
        ],
        [],
        m,
    )


def doshas(m: Master, lib: Library) -> dict[str, Any]:
    if m["doshas"] is None:
        return unavailable("doshas", "Body-mind tendencies")
    d = m["doshas"]
    lead = d["dominant"]
    head = (
        f"{lead[0]} leads"
        if d["label"] == "mono"
        else (f"{lead[0]} and {lead[1]} share the lead" if d["label"] == "dual" else "A balanced mix")
    )
    entries = [lib.get("nature", "doshas", x) for x in lead]
    label = lib.raw("nature", "doshas", "labels", d["label"])
    detail = _join(
        label,
        *[e["nature"] for e in entries],
        *[e["balance"] for e in entries],
        "These describe tendencies for reflection, not health advice.",
    )
    return _card(
        "doshas",
        head,
        _join(label, entries[0]["nature"]),
        detail,
        [_sec("try_this", [e["balance"] for e in entries])],
        [],
        m,
    )


def chakras(m: Master, lib: Library) -> dict[str, Any]:
    if m["chakras"] is None:
        return unavailable("chakras", "Energy centres")
    states = lib.raw("nature", "chakra_states")
    names = {c["id"]: lib.get("nature", "chakras", c["id"]) for c in m["chakras"]}
    dom = [names[c["id"]]["name"] for c in m["chakras"] if c["class"] == "dominant"]
    quiet = [names[c["id"]] for c in m["chakras"] if c["class"] == "low_activity"]
    lines = [f"{names[c['id']]['name']} ({names[c['id']]['about']}) {states[c['class']]}." for c in m["chakras"]]
    head = f"Strong {_list(dom[:2])}" if dom else "Steady energy centres"
    summary = f"Your {_list(dom).lower()} centres flow strongly." if dom else "Your energy centres are fairly even."
    if quiet:
        plural = "centres" if len(quiet) > 1 else "centre"
        summary += f" Your {_list([q['name'].lower() for q in quiet])} {plural} may welcome attention."
    return _card(
        "chakras",
        head[:60],
        summary,
        _join(*lines),
        [_sec("strengths", dom), _sec("try_this", [f"Give some time to {q['about']}" for q in quiet])],
        [],
        m,
    )


# ---------- Constellation III: your path ----------


def motive(m: Master, lib: Library) -> dict[str, Any]:
    ak = m["purpose"]["atmakaraka"]
    if ak is None:
        return unavailable("motive", "Core motive")
    p = lib.get("planets", ak)
    axis = m["purpose"]["rahu_ketu_axis"]
    grow = lib.get("axis", f"house_{axis['rahu_house']}") if axis else None
    summary = _join(
        f"Your soul planet is {ak}, pointing to a deep pull toward {p['motive']}.", grow["grow"] if grow else ""
    )
    detail = _join(
        summary,
        f"Its gift is {p['gift'].lower()}; its challenge can be {p['edge'].lower()}.",
        grow["natural"] if grow else "",
    )
    return _card(
        "motive",
        f"Soul planet: {ak}",
        summary,
        detail,
        [_sec("strengths", [p["gift"]]), _sec("watch_points", [p["edge"]])],
        ["ak.planet", "rahu.house", "ketu.house"],
        m,
    )


def season(m: Master, lib: Library) -> dict[str, Any]:
    chain = m["dasha"]["active_chain"]
    if not chain:
        return unavailable("season", "Your life season now")
    maha, antar = chain[0]["lord"], chain[1]["lord"] if len(chain) > 1 else None
    pm = lib.get("planets", maha)
    pa = lib.get("planets", antar) if antar else None
    head = f"{maha} period, {antar} sub-period" if antar else f"{maha} period"
    summary = _join(
        f"You are in a {maha} period.", pm["period"], f"Within it, {antar} adds its own note." if antar else ""
    )
    detail = _join(
        summary, pa["period"] if pa else "", "Periods describe themes to work with, not events that will happen."
    )
    return _card(
        "season",
        head,
        summary,
        detail,
        [_sec("this_season", [pm["gift"], pa["gift"] if pa else ""])],
        ["dasha.maha", "dasha.antar"],
        m,
    )


def growth(m: Master, lib: Library) -> dict[str, Any]:
    items: list[str] = []
    if m["chakras"]:
        for c in m["chakras"]:
            if c["class"] == "low_activity":
                items.append(f"Give time to {lib.get('nature', 'chakras', c['id'])['about']}")
    axis = m["purpose"]["rahu_ketu_axis"]
    grow = lib.get("axis", f"house_{axis['rahu_house']}")["grow"] if axis else ""
    ak = m["purpose"]["atmakaraka"]
    edge = lib.get("planets", ak)["edge"] if ak else ""
    if not (items or grow or edge):
        return unavailable("growth", "Growth edges")
    summary = _join(grow, f"A gentle edge to watch is {edge.lower()}." if edge else "")
    return _card(
        "growth",
        "Your growth edges",
        summary or "Small, steady steps help you grow.",
        _join(summary, "Growth edges are invitations, not faults."),
        [_sec("try_this", items or ["Try one small new habit this week"])],
        ["rahu.house", "ak.planet"],
        m,
    )


# ---------- Constellation IV: your allies ----------


def deity(m: Master, lib: Library) -> dict[str, Any]:
    d = m["ishta_devta"]
    if d is None:
        return unavailable("deity", "Your deity")
    e = lib.get("deities", d["main"].split(" ")[0])
    detail = _join(
        e["essence"],
        f"In this tradition it is found through your soul planet and its place in "
        f"your Navamsa chart, which points here through {_planet(d['deciding_planet'])}.",
        "This depends on your exact birth time." if d["time_sensitive"] else "",
        "Traditions differ; choose the form that draws your mind.",
    )
    sections = [
        _sec("qualities_to_grow", list(e["qualities"])),
        _sec("practice", [e["practice"]]),
        _sec("other_forms", [", ".join(d["others"])] if d["others"] else []),
    ]
    return _card("deity", f"Your deity: {d['main']}", e["essence"], detail, sections, ["deity.planet", "ak.planet"], m)


def _role_line(lib: Library, roles: list[str]) -> str:
    who = [lib.get("allies", "roles", r)["who"] for r in roles]
    return "Chosen through " + " and ".join(who) + "."


def colors(m: Master, lib: Library) -> dict[str, Any]:
    if m["colors"] is None:
        return unavailable("colors", "Power colours")
    sw = m["colors"]["swatches"]
    entries, ideas = [], []
    for s in sw:
        c = lib.get("allies", "colours", s["name"])
        entries.append(
            {
                "ref": s["name"],
                "title": s["name"],
                "text": _join(c["text"], _role_line(lib, s["roles"]))[:400],
                "tags": list(c["tags"]),
            }
        )
        ideas.append(c["ideas"][0])
    names = ", ".join(s["name"] for s in sw)
    return _card(
        "colors",
        f"Your colours: {names}"[:60],
        f"{names}: traditional colours linked with the planets that guide your chart.",
        "These are traditional associations to use for reflection and mood, not guarantees.",
        [_sec("how_to_use", ideas)],
        [f"colors.swatch_{i}" for i in range(1, len(sw) + 1)],
        m,
        entries,
    )


def days(m: Master, lib: Library) -> dict[str, Any]:
    if m["days"] is None:
        return unavailable("days", "Power days")
    items = m["days"]["items"]
    entries, ideas = [], []
    for d in items:
        w = lib.get("allies", "weekdays", d["weekday"])
        entries.append(
            {
                "ref": d["weekday"],
                "title": d["weekday"],
                "text": _join(w["text"], _role_line(lib, d["roles"]))[:400],
                "tags": list(w["tags"]),
            }
        )
        ideas.append(w["ideas"][0])
    names = ", ".join(d["weekday"] for d in items)
    return _card(
        "days",
        f"Supportive days: {names}"[:60],
        f"{names}: days traditionally linked with the planets that guide your chart.",
        "Use them for things that matter to you. They are supportive days, not rules.",
        [_sec("ideas_for_the_day", ideas)],
        [f"days.item_{i}" for i in range(1, len(items) + 1)],
        m,
        entries,
    )


BUILDERS: dict[str, Callable[[Master, Library], dict[str, Any]]] = {
    "identity": identity,
    "birthstar": birthstar,
    "nameletter": nameletter,
    "elements": elements,
    "doshas": doshas,
    "chakras": chakras,
    "motive": motive,
    "season": season,
    "growth": growth,
    "deity": deity,
    "colors": colors,
    "days": days,
}


def build(module: str, master: Master, lib: Library) -> dict[str, Any]:
    """Curated card for one module; raises LibraryGap if an entry is missing or unapproved."""
    try:
        return BUILDERS[module](master, lib)
    except KeyError as e:
        raise LibraryGap(str(e)) from e
