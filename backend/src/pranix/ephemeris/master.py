# SPDX-License-Identifier: AGPL-3.0-only
"""Master JSON builder: meta, identity, nakshatra, naming, d1, d9, purpose, ishta_devta, colors,
days, elements, doshas, chakras, dasha, facts, flags.

Unknown birth time follows the certain-only rule (D56): the chart is computed at the start
(00:00:00) and end (23:59:59) of the local birth day; a value is published only when both
agree. Signs and nakshatras that change are listed in flags.time_sensitive with both values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from fractions import Fraction
from typing import Any, Literal

from .. import __version__
from . import allies, angles, charts, dasha, facts, heuristics, swe
from .ruleset import Ruleset, load_ruleset, load_table
from .timeconv import julian_day_ut, to_utc

SCHEMA_VERSION = "1.0.0"
NEAR_TOL = 0.01
NEAR_TOL_LAGNA = 0.25


@dataclass(frozen=True)
class BirthInput:
    local_datetime: datetime  # naive local wall time
    tz: str  # IANA id, resolved server-side
    lat: float
    lon: float
    birth_time_known: bool = True
    time_accuracy: Literal["exact", "approx_5m", "approx_30m", "approx_1h"] | None = None
    disambiguation: Literal["earlier", "later"] | None = None
    ruleset: str = "vedic-core@1"

    def canonical(self) -> BirthInput:
        """FR-INP-06: 4 dp coordinates, whole seconds; unknown time -> noon, accuracy dropped."""
        t = self.local_datetime.replace(microsecond=0)
        if not self.birth_time_known:
            t = datetime.combine(t.date(), time(12, 0, 0))
        return BirthInput(
            local_datetime=t,
            tz=self.tz,
            lat=round(self.lat, 4),
            lon=round(self.lon, 4),
            birth_time_known=self.birth_time_known,
            time_accuracy=self.time_accuracy if self.birth_time_known else None,
            disambiguation=self.disambiguation,
            ruleset=self.ruleset,
        )


@dataclass(frozen=True)
class _Snapshot:
    utc: datetime
    jd: float
    bodies: list[swe.Body]
    asc: float


def _snap(inp: BirthInput, local: datetime) -> _Snapshot:
    r = to_utc(local, inp.tz, inp.disambiguation)
    jd = julian_day_ut(r.utc)
    return _Snapshot(r.utc, jd, swe.bodies(jd), swe.ascendant(jd, inp.lat, inp.lon))


def _as_of_instant(as_of: date) -> datetime:
    return datetime.combine(as_of, time(0, 0, 0), tzinfo=UTC)


def compute(inp: BirthInput, as_of: date) -> dict[str, Any]:
    inp = inp.canonical()
    rs = load_ruleset(inp.ruleset)
    mode = swe.init()
    if inp.birth_time_known:
        return _known(rs, inp, as_of, mode)
    return _unknown(rs, inp, as_of, mode)


def _meta(rs: Ruleset, inp: BirthInput, snap: _Snapshot, mode: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "engine_version": __version__,
        "swisseph_version": swe.library_version(),
        "ruleset": {"id": rs.id, "version": rs.version, "hash": rs.hash},
        "rulesets": [
            {"id": t.id, "version": t.version, "hash": t.hash}
            for t in (load_table(r) for r in (allies.ISHTA, allies.COLORS, allies.DAYS, allies.NAMING))
        ],
        "ayanamsa": "lahiri",
        "ayanamsa_value": swe.ayanamsa(snap.jd),
        "node_type": "mean",
        "house_system": "whole_sign",
        "dasha_year_days": float(rs.dasha_year_days),
        "ephemeris_mode": mode,
        "birth_time_known": inp.birth_time_known,
    }


def _moon_nakshatra(rs: Ruleset, lon: float, with_pada: bool) -> dict[str, Any]:
    i = angles.nakshatra_index(lon)
    n = rs.nakshatras[i]
    return {
        "number": i + 1,
        "name": n.name,
        "pada": angles.pada(lon) if with_pada else None,
        "lord": n.lord,
        "deity": n.deity,
        "symbol": n.symbol,
    }


def _body(snap: _Snapshot, pid: str) -> swe.Body:
    return next(b for b in snap.bodies if b.id == pid)


def _chain(rs: Ruleset, snap: _Snapshot, as_of: date, depth: int) -> list[dict[str, Any]]:
    at = dasha.instant(_as_of_instant(as_of))
    chain = dasha.active_chain(rs, _body(snap, "Moon").longitude, dasha.instant(snap.utc), at, depth)
    return [p.to_dict(now=at) for p in chain]


def _near(snap: _Snapshot) -> list[str]:
    out = [f"{b.id.lower()}.longitude" for b in snap.bodies if angles.near_boundary(b.longitude, NEAR_TOL)]
    if angles.near_boundary(snap.asc, NEAR_TOL_LAGNA):
        out.insert(0, "lagna.longitude")
    return out


def _identity(rs: Ruleset, moon: swe.Body, sun: swe.Body, lagna: float | None) -> dict[str, Any]:
    def part(lon: float, with_deg: bool) -> dict[str, Any]:
        s = angles.sign_index(lon)
        d: dict[str, Any] = {"sign": rs.signs[s], "lord": rs.sign_lords[s]}
        if with_deg:
            d["deg_in_sign"] = angles.deg_in_sign(lon)
            if lagna is not None:
                d["house"] = angles.whole_sign_house(s, angles.sign_index(lagna))
        return d

    known = lagna is not None
    return {
        "lagna": part(lagna, True) if lagna is not None else None,
        "moon": part(moon.longitude, known),
        "sun": part(sun.longitude, known),
    }


def _known(rs: Ruleset, inp: BirthInput, as_of: date, mode: str) -> dict[str, Any]:
    snap = _snap(inp, inp.local_datetime)
    moon, sun = _body(snap, "Moon"), _body(snap, "Sun")
    ak = charts.atmakaraka(snap.bodies)
    rahu = _body(snap, "Rahu")
    lagna_sign = angles.sign_index(snap.asc)
    r_house = angles.whole_sign_house(angles.sign_index(rahu.longitude), lagna_sign)
    ishta = allies.ishta_devta(rs, snap.bodies)
    # Deity depends on exact degrees: flag it if it differs at either end of the birth day (FR-CAL-05).
    day = inp.local_datetime.date()
    ends = [_snap(inp, datetime.combine(day, t)) for t in (time(0, 0, 0), time(23, 59, 59))]
    ishta["time_sensitive"] = any(allies.ishta_devta(rs, e.bodies)["main"] != ishta["main"] for e in ends)
    m = {
        "meta": _meta(rs, inp, snap, mode),
        "identity": _identity(rs, moon, sun, snap.asc),
        "nakshatra": _moon_nakshatra(rs, moon.longitude, True),
        "naming": allies.naming(moon.longitude, True),
        "d1": charts.build_d1(rs, snap.bodies, snap.asc),
        "d9": charts.build_d9(rs, snap.bodies, snap.asc),
        "purpose": {"atmakaraka": ak, "rahu_ketu_axis": {"rahu_house": r_house, "ketu_house": (r_house + 5) % 12 + 1}},
        "ishta_devta": ishta,
        "colors": allies.colors(rs, snap.bodies, snap.asc),
        "days": allies.days(rs, snap.bodies, snap.asc),
        "elements": heuristics.elements(rs, snap.bodies, snap.asc),
        "doshas": heuristics.doshas(rs, snap.bodies, snap.asc),
        "chakras": heuristics.chakras(rs, snap.bodies),
        "dasha": {"as_of": as_of.isoformat(), "active_chain": _chain(rs, snap, as_of, dasha.MAX_DEPTH)},
        "flags": {"near_boundary": _near(snap), "time_sensitive": []},
    }
    m["facts"] = facts.build(m)
    return m


def _unknown(rs: Ruleset, inp: BirthInput, as_of: date, mode: str) -> dict[str, Any]:
    day = inp.local_datetime.date()
    a = _snap(inp, datetime.combine(day, time(0, 0, 0)))
    b = _snap(inp, datetime.combine(day, time(23, 59, 59)))
    noon = _snap(inp, inp.local_datetime)
    ts: list[dict[str, Any]] = []
    planets = []
    for pa, pb in zip(a.bodies, b.bodies, strict=False):
        sa, sb = angles.sign_index(pa.longitude), angles.sign_index(pb.longitude)
        na, nb = angles.nakshatra_index(pa.longitude), angles.nakshatra_index(pb.longitude)
        key = pa.id.lower()
        if sa != sb:
            ts.append({"fact_id": f"{key}.sign", "values": [rs.signs[sa], rs.signs[sb]]})
        if na != nb:
            ts.append({"fact_id": f"{key}.nakshatra", "values": [rs.nakshatras[na].name, rs.nakshatras[nb].name]})
        da, db = charts.dignity(rs, pa.id, sa), charts.dignity(rs, pb.id, sb)
        planets.append(
            {
                "id": pa.id,
                "longitude": None,
                "deg_in_sign": None,
                "house": None,
                "pada": None,
                "vargottama": None,
                "sign": rs.signs[sa] if sa == sb else None,
                "nakshatra": rs.nakshatras[na].name if na == nb else None,
                "dignity": da if da == db else None,
                "retrograde": pa.retrograde if pa.retrograde == pb.retrograde else None,
                "speed": None,
            }
        )

    def same(fa: Any, fb: Any) -> Any:
        return fa if fa == fb else None

    ak_a, ak_b = charts.atmakaraka(a.bodies), charts.atmakaraka(b.bodies)
    if ak_a != ak_b:
        ts.append({"fact_id": "ak.planet", "values": [ak_a, ak_b]})

    moon_a, moon_b = _body(a, "Moon"), _body(b, "Moon")
    nak = (
        _moon_nakshatra(rs, moon_a.longitude, False)
        if angles.nakshatra_index(moon_a.longitude) == angles.nakshatra_index(moon_b.longitude)
        else None
    )

    ca, cb = _chain(rs, a, as_of, 2), _chain(rs, b, as_of, 2)
    lords_same = [p["lord"] for p in ca] == [p["lord"] for p in cb]
    if not lords_same:
        ts.append(
            {"fact_id": "dasha.antar", "values": ["-".join(p["lord"] for p in ca), "-".join(p["lord"] for p in cb)]}
        )

    ident_a = _identity(rs, moon_a, _body(a, "Sun"), None)
    ident_b = _identity(rs, moon_b, _body(b, "Sun"), None)

    na, nb = angles.nakshatra_index(moon_a.longitude), angles.nakshatra_index(moon_b.longitude)
    naming = allies.naming(moon_a.longitude, False)
    if na != nb:  # star changes during the day: both rows, never a guess (D56)
        naming["alternatives"] = [allies.naming_for(nb)]
    col = same(allies.colors(rs, a.bodies, None), allies.colors(rs, b.bodies, None))
    dys = same(allies.days(rs, a.bodies, None), allies.days(rs, b.bodies, None))
    m = {
        "meta": _meta(rs, inp, noon, mode),
        "identity": {
            "lagna": None,
            "moon": same(ident_a["moon"], ident_b["moon"]),
            "sun": same(ident_a["sun"], ident_b["sun"]),
        },
        "nakshatra": nak,
        "naming": naming,
        "d1": {"lagna": None, "houses": None, "planets": planets},
        "d9": None,
        "purpose": {"atmakaraka": same(ak_a, ak_b), "rahu_ketu_axis": None},
        "ishta_devta": None,  # needs D9, so a birth time (D56)
        "colors": col,
        "days": dys,
        "elements": same(heuristics.elements(rs, a.bodies, None), heuristics.elements(rs, b.bodies, None)),
        "doshas": same(heuristics.doshas(rs, a.bodies, None), heuristics.doshas(rs, b.bodies, None)),
        "chakras": same(heuristics.chakras(rs, a.bodies), heuristics.chakras(rs, b.bodies)),
        "dasha": {"as_of": as_of.isoformat(), "active_chain": _chain(rs, noon, as_of, 2) if lords_same else None},
        "flags": {"near_boundary": [], "time_sensitive": ts},
    }
    m["facts"] = facts.build(m)
    return m


def dasha_seed(inp: BirthInput) -> tuple[float, Fraction]:
    """(Moon longitude, birth instant) for lazy Dasha timelines. Unknown time uses local noon,
    which is only served when the active chain is the same all day (D56)."""
    inp = inp.canonical()
    swe.init()
    snap = _snap(inp, inp.local_datetime)
    return _body(snap, "Moon").longitude, dasha.instant(snap.utc)


def canonical_json(master: dict[str, Any]) -> bytes:
    """Byte-identical output for identical input (ENG-11)."""
    return json.dumps(master, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
