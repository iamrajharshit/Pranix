# SPDX-License-Identifier: AGPL-3.0-only
"""InspectionSet / InspectionBundle: the data container of GET /v1/profiles/{id}/inspect/{chart}.

Built by plain functions from the Master JSON and the approved vedic-core@1 tables (sign lords, dignity).
Contract: docs/design/Inspector_data_contract_and_modules.md §4; order and labels per D81.

Planet targets (I1): placement, houses ruled, sits with, the other chart, the dispositor chain, either side.
House targets (I2): the house with its occupants, its lord and where the lord sits, the same house in the
other chart, either side. Houses exist only when the birth time is known (D56).
Aspects (I3): graha drishti from the owner-approved jyotish-core@1 table (26 Nov 2026), whole-house,
read in D1 and inside D9; at sign level (no birth time) the same counts apply by sign (D81 4).
None always means "not available", never "none" (an empty list means none).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ..ephemeris.ruleset import Ruleset, Table, load_table
from .context import Chart, ChartContext, Level, step

Dignity = Literal["exalted", "own", "friend", "neutral", "enemy", "debilitated"]
SCHEMA_VERSION: Literal["1"] = "1"
NODES = ("Rahu", "Ketu")
MAX_CHAIN = 9


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Target(_Model):
    kind: Literal["planet", "house"]
    ref: str


class Placement(_Model):
    sign: str | None
    sign_options: list[str] | None
    house: int | None
    dignity: Dignity | None
    dignity_gloss: str | None = None  # approved calm wording (D81 §3), added by insight.inspect_text
    vargottama: bool | None
    deg_in_sign: float | None  # the engine's value; the UI truncates it with dm() (rule 6)
    nakshatra: str | None
    nakshatra_options: list[str] | None
    retrograde: bool | None


class HouseRef(_Model):
    house: int
    sign: str
    occupants: list[str]


class OtherChart(_Model):
    chart: Chart
    sign: str
    house: int
    dignity: Dignity | None
    change: Literal["same", "changed", "none"]


class Dispositor(_Model):
    steps: list[str]
    end: Literal["final", "exchange", "cycle", "stops_uncertain"]
    pair: list[str] | None
    cycle_members: list[str] | None


class EitherSide(_Model):
    before: HouseRef
    after: HouseRef
    kartari: None = None  # reserved for V2 (D81 §5)


class HouseLord(_Model):
    planet: str
    house: int
    sign: str
    dignity: Dignity | None


class Unavailable(_Model):
    what: Literal["house", "houses_ruled", "degree", "d9", "aspects", "sign", "nakshatra", "dignity", "retrograde"]
    reason: Literal["BIRTH_TIME_REQUIRED", "CHANGES_DURING_DAY"]


class InspectionBundle(_Model):
    schema_version: Literal["1"] = SCHEMA_VERSION
    target: Target
    chart: Chart
    level: Level
    summary: str | None = None  # approved template, no numerals; added by insight.inspect_text
    # planet targets (None on a house target)
    placement: Placement | None = None
    houses_ruled: list[HouseRef] | None = None
    acts_through: str | None = None
    sits_with: list[str] = []
    aspects_out: list[HouseRef] | None = None  # houses this planet looks at, in offset order (house level)
    aspects_out_signs: list[str] | None = None  # signs it looks at (sign level, no birth time)
    aspects_in: list[str] | None = None  # planets that look at this planet's house, or at this house
    other_chart: OtherChart | None = None
    dispositor: Dispositor | None = None
    # house targets (None on a planet target)
    house: HouseRef | None = None
    lord: HouseLord | None = None
    same_house_other_chart: HouseRef | None = None
    # both
    either_side: EitherSide | None
    top_signals: list[str] = []  # reserved for the I1+ resolver (D81 §5)
    modifiers: list[str] = []  # reserved for V2 (neechabhanga, combustion, ...)
    unavailable: list[Unavailable]
    fact_ids: list[str]


class RulesetRef(_Model):
    id: str
    version: int
    hash: str


class InspectionSet(_Model):
    chart: Chart
    level: Level
    ruleset: RulesetRef
    rules: RulesetRef  # jyotish-core (the aspect table)
    bundles: dict[str, InspectionBundle]  # keys "planet:Jupiter" and, with a birth time, "house:7"

    def etag(self) -> str:
        return '"' + hashlib.sha256(canonical(self).encode()).hexdigest()[:32] + '"'


def canonical(model: BaseModel) -> str:
    """Byte-stable JSON (rule 4): same Master JSON + ruleset gives the same text."""
    return json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# --- relations --------------------------------------------------------------------------------------


def dispositor(ctx: ChartContext, planet: str) -> Dispositor:
    """Lord of the sign it occupies, then that lord's sign lord... until final, an exchange or a loop."""
    steps = [planet]
    for _ in range(MAX_CHAIN):
        sign = ctx.planets[steps[-1]].sign
        if sign is None:
            return Dispositor(steps=steps, end="stops_uncertain", pair=None, cycle_members=None)
        lord = ctx.lord_of(sign)
        if lord == steps[-1]:
            return Dispositor(steps=steps, end="final", pair=None, cycle_members=None)
        if lord in steps:
            at = steps.index(lord)
            members = steps[at:]
            kind: Literal["exchange", "cycle"] = "exchange" if len(members) == 2 else "cycle"
            return Dispositor(steps=steps, end=kind, pair=[steps[-1], lord], cycle_members=members)
        steps.append(lord)
    return Dispositor(steps=steps, end="cycle", pair=None, cycle_members=None)  # unreachable with nine planets


def offsets(rules: Table, planet: str) -> list[int]:
    return list(rules.data["tables"]["graha_drishti"][planet])


def looks_at(ctx: ChartContext, rules: Table, planet: str) -> list[int]:
    """Houses a planet looks at, in the table's order (Mars: 4th, 7th, 8th from itself)."""
    h = ctx.planets[planet].house
    return [] if h is None else [step(h, n) for n in offsets(rules, planet)]


def looked_at_by(ctx: ChartContext, rules: Table, house: int, exclude: str | None = None) -> list[str]:
    return [p for p in ctx.order if p != exclude and house in looks_at(ctx, rules, p)]


def looks_at_signs(ctx: ChartContext, rules: Table, planet: str) -> list[str] | None:
    sign = ctx.planets[planet].sign
    if sign is None:
        return None
    i = ctx.sign_index(sign)
    return [ctx.rs.signs[(i + n - 1) % 12] for n in offsets(rules, planet)]


def looked_at_by_sign(ctx: ChartContext, rules: Table, sign: str, exclude: str) -> list[str]:
    return [p for p in ctx.order if p != exclude and sign in (looks_at_signs(ctx, rules, p) or [])]


def _house_ref(ctx: ChartContext, house: int) -> HouseRef:
    return HouseRef(house=house, sign=ctx.house_sign(house), occupants=ctx.occupants(house))


def planet_bundle(
    ctx: ChartContext, other: ChartContext | None, d1_varg: bool | None, planet: str, rules: Table
) -> InspectionBundle:
    f = ctx.planets[planet]
    node = planet in NODES
    house_level = ctx.level == "house"
    unavailable: list[Unavailable] = []
    if not house_level:
        unavailable += [
            Unavailable(what=w, reason="BIRTH_TIME_REQUIRED") for w in ("house", "houses_ruled", "degree", "d9")
        ]
        if f.sign is None:
            unavailable.append(Unavailable(what="sign", reason="CHANGES_DURING_DAY"))
        if f.nakshatra is None and ctx.nakshatra_options(planet):
            unavailable.append(Unavailable(what="nakshatra", reason="CHANGES_DURING_DAY"))
        if f.dignity is None and not node:
            unavailable.append(Unavailable(what="dignity", reason="CHANGES_DURING_DAY"))
        if f.retrograde is None:
            unavailable.append(Unavailable(what="retrograde", reason="CHANGES_DURING_DAY"))

    placement = Placement(
        sign=f.sign,
        sign_options=(list(ctx.sign_options(planet) or []) or None) if f.sign is None else None,
        house=f.house,
        dignity=f.dignity,  # type: ignore[arg-type]
        vargottama=d1_varg if house_level else None,
        deg_in_sign=f.deg_in_sign if (house_level and ctx.chart == "d1") else None,
        nakshatra=f.nakshatra if ctx.chart == "d1" else None,
        nakshatra_options=(list(ctx.nakshatra_options(planet) or []) or None)
        if (ctx.chart == "d1" and f.nakshatra is None)
        else None,
        retrograde=f.retrograde,
    )

    if house_level and f.house is not None:
        ruled = (
            []
            if node
            else sorted(  # nodes rule no sign: they act through their sign lord
                (
                    _house_ref(ctx, ctx.house_of_sign(s))
                    for s, lord in zip(ctx.rs.signs, ctx.rs.sign_lords, strict=True)
                    if lord == planet
                ),
                key=lambda r: r.house,
            )
        )
        sits = [p for p in ctx.occupants(f.house) if p != planet]
        either = EitherSide(before=_house_ref(ctx, step(f.house, 12)), after=_house_ref(ctx, step(f.house, 2)))
        a_out: list[HouseRef] | None = [_house_ref(ctx, h) for h in looks_at(ctx, rules, planet)]
        a_signs: list[str] | None = None
        a_in: list[str] | None = looked_at_by(ctx, rules, f.house, exclude=planet)
    else:
        ruled = None
        sits = [p for p in ctx.same_sign(f.sign) if p != planet] if f.sign else []
        either = None
        a_out = None
        a_signs = looks_at_signs(ctx, rules, planet)  # None when its own sign changes that day
        a_in = looked_at_by_sign(ctx, rules, f.sign, exclude=planet) if f.sign else None

    other_chart = None
    if other is not None and house_level:
        o = other.planets[planet]
        assert o.sign is not None and o.house is not None
        change: Literal["same", "changed", "none"] = (
            "none" if node else ("same" if o.dignity == f.dignity else "changed")
        )
        other_chart = OtherChart(chart=other.chart, sign=o.sign, house=o.house, dignity=o.dignity, change=change)  # type: ignore[arg-type]

    key = f"{ctx.chart}.{planet.lower()}"
    facts = [f"{key}.placement", f"{key}.dispositor"]
    if ruled is not None:
        facts.append(f"{key}.houses_ruled")
    if house_level:
        facts += [f"{key}.sits_with", f"{key}.aspects", f"{key}.either_side", f"{key}.other_chart"]
    else:
        facts.append(f"{key}.same_sign")
        if a_signs is not None:
            facts.append(f"{key}.aspects_by_sign")

    return InspectionBundle(
        target=Target(kind="planet", ref=planet),
        chart=ctx.chart,
        level=ctx.level,
        placement=placement,
        houses_ruled=ruled,
        acts_through=ctx.lord_of(f.sign) if (node and f.sign) else None,
        sits_with=sits,
        aspects_out=a_out,
        aspects_out_signs=a_signs,
        aspects_in=a_in,
        other_chart=other_chart,
        dispositor=dispositor(ctx, planet),
        either_side=either,
        unavailable=unavailable,
        fact_ids=facts,
    )


def house_bundle(ctx: ChartContext, other: ChartContext, house: int, rules: Table) -> InspectionBundle:
    """A house is read through its occupants, its lord and where that lord sits; empty houses too (plan §4.8)."""
    sign = ctx.house_sign(house)
    lord = ctx.lord_of(sign)
    lf = ctx.planets[lord]
    assert lf.house is not None and lf.sign is not None
    key = f"{ctx.chart}.house_{house}"
    return InspectionBundle(
        target=Target(kind="house", ref=str(house)),
        chart=ctx.chart,
        level=ctx.level,
        house=_house_ref(ctx, house),
        lord=HouseLord(planet=lord, house=lf.house, sign=lf.sign, dignity=lf.dignity),  # type: ignore[arg-type]
        aspects_in=looked_at_by(ctx, rules, house),
        same_house_other_chart=_house_ref(other, house),
        either_side=EitherSide(before=_house_ref(ctx, step(house, 12)), after=_house_ref(ctx, step(house, 2))),
        unavailable=[],
        fact_ids=[f"{key}.occupants", f"{key}.lord", f"{key}.aspects", f"{key}.other_chart", f"{key}.either_side"],
    )


ASPECT_RULES = "jyotish-core@1"


def build_set(master: Mapping[str, Any], chart: Chart, rs: Ruleset, rules: Table | None = None) -> InspectionSet:
    """Every target of one chart. Raises ValueError when the chart needs a birth time (D9, D56)."""
    rules = rules or load_table(ASPECT_RULES)
    ctx = ChartContext.from_master(master, chart, rs)
    other = None
    if ctx.level == "house":
        other_chart: Chart = "d9" if chart == "d1" else "d1"
        other = ChartContext.from_master(master, other_chart, rs)
    varg = {p["id"]: p.get("vargottama") for p in master["d1"]["planets"]}
    bundles = {f"planet:{p}": planet_bundle(ctx, other, varg.get(p), p, rules) for p in ctx.order}
    if other is not None:  # houses need a rising sign, so a birth time (D56)
        bundles.update({f"house:{h}": house_bundle(ctx, other, h, rules) for h in range(1, 13)})
    return InspectionSet(
        chart=chart,
        level=ctx.level,
        ruleset=RulesetRef(id=rs.id, version=rs.version, hash=rs.hash),
        rules=RulesetRef(id=rules.id, version=rules.version, hash=rules.hash),
        bundles=bundles,
    )
