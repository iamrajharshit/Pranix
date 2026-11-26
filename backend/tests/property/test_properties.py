# SPDX-License-Identifier: AGPL-3.0-only
"""Property tests (QA-03)."""

from datetime import date, datetime
from fractions import Fraction

from hypothesis import given, settings
from hypothesis import strategies as st

from pranix.ephemeris import angles, dasha
from pranix.ephemeris.master import BirthInput, compute
from pranix.ephemeris.ruleset import load_ruleset
from pranix.insight import cards
from pranix.insight.library import Library
from pranix.insight.validators import check_card

RS = load_ruleset()
lon = st.floats(min_value=0, max_value=359.999999, allow_nan=False)


@given(lon, lon)
def test_nakshatra_is_monotonic(a: float, b: float) -> None:
    lo, hi = sorted((a, b))
    assert angles.nakshatra_index(lo) <= angles.nakshatra_index(hi)


@given(lon)
def test_ranges_and_consistency(x: float) -> None:
    assert 0 <= angles.sign_index(x) < 12
    assert 0 <= angles.nakshatra_index(x) < 27
    assert 1 <= angles.pada(x) <= 4
    assert 0 <= angles.d9_sign_index(x) < 12
    # 9 padas per sign: absolute pada number and navamsa agree
    assert angles.d9_sign_index(x) == (angles.nakshatra_index(x) * 4 + angles.pada(x) - 1) % 12
    d, m = angles.truncate_dm(angles.deg_in_sign(x))
    assert 0 <= d < 30 and 0 <= m < 60


@given(lon, st.integers(min_value=-5_000_000_000, max_value=10_000_000_000))
def test_dasha_contiguous_and_exact(moon: float, birth: int) -> None:
    mahas = dasha.mahadashas(RS, moon, Fraction(birth))
    assert mahas[-1].end - mahas[0].full_start == 120 * dasha.year_seconds(RS)
    kids = dasha.children(RS, mahas[0])
    assert sum((k.end - k.start for k in kids), Fraction(0)) == mahas[0].length


@settings(max_examples=60, deadline=None)
@given(
    st.datetimes(min_value=datetime(1900, 1, 1), max_value=datetime(2020, 12, 31)),
    st.floats(min_value=-60, max_value=60),
    st.floats(min_value=-179, max_value=179),
    st.booleans(),
)
def test_master_invariants(dt: datetime, lat: float, lon_: float, known: bool) -> None:
    m = compute(BirthInput(dt, "UTC", lat, lon_, birth_time_known=known), date(2026, 11, 14))
    if m["elements"] is not None:
        assert sum(m["elements"]["percent"].values()) == 100
    if m["doshas"] is not None:
        assert sum(m["doshas"]["percent"].values()) == 100
    if m["colors"] is not None:
        sw = m["colors"]["swatches"]
        # 2-3 colours, except when every deciding planet is Mars or Mercury, whose tradition gives only
        # one colour and no variant: then one true colour, never an invented one (D65, owner 20 Nov 2026).
        assert 1 <= len(sw) <= 3
        if len(sw) == 1:
            assert sw[0]["planets"] in (["Mars"], ["Mercury"])
        assert len({s["name"] for s in m["colors"]["swatches"]}) == len(m["colors"]["swatches"])
    if m["days"] is not None:
        assert 1 <= len(m["days"]["items"]) <= 3
    for v in m["facts"].values():  # every fact points at something that exists in this chart
        t = v["target"]
        assert t["chart"] in ("d1", "d9", "none")
        if not known:
            assert t["kind"] not in ("house", "lagna") and t["chart"] == "none"
    lib = Library(allow_drafts=False)  # production: approved entries only (FR-LIB-03)
    for module in cards.MODULES:  # no chart can make any card break a guardrail or miss its text
        c = cards.build(module, m, lib)
        check_card(c, m["facts"])
        assert c["state"] != "error", module
    if known:
        assert m["ishta_devta"]["main"] and len(m["ishta_devta"]["others"]) <= 2
        assert m["naming"]["syllables"][m["naming"]["pada"] - 1]["pada"] == m["naming"]["pada"]
        assert len(m["d1"]["planets"]) == 9 and m["d9"] is not None
        assert sorted(p["house"] for p in m["d1"]["houses"]) == list(range(1, 13))
    else:
        assert m["d9"] is None and m["d1"]["lagna"] is None


@settings(max_examples=40, deadline=None)
@given(
    st.datetimes(min_value=datetime(1900, 1, 1), max_value=datetime(2020, 12, 31)),
    st.floats(min_value=-60, max_value=60),
    st.floats(min_value=-179, max_value=179),
    st.booleans(),
)
def test_inspection_set_invariants(dt: datetime, lat: float, lon_: float, known: bool) -> None:
    """I1: on any chart, every planet has a bundle, chains end, houses stay in range, ruled houses
    are sorted, sign level never shows time-dependent data, and the bytes are deterministic."""
    from pranix.insight.inspect_text import with_text
    from pranix.jyotish import build_set
    from pranix.jyotish.bundle import canonical

    m = compute(BirthInput(dt, "UTC", lat, lon_, birth_time_known=known), date(2026, 11, 14))
    for chart in ("d1", "d9") if known else ("d1",):
        s = with_text(build_set(m, chart, RS))  # type: ignore[arg-type]
        assert len(s.bundles) == 9 and canonical(s) == canonical(with_text(build_set(m, chart, RS)))  # type: ignore[arg-type]
        for b in s.bundles.values():
            d = b.dispositor
            assert 1 <= len(d.steps) <= 9 and d.end in ("final", "exchange", "cycle", "stops_uncertain")
            if d.end == "exchange":
                assert d.cycle_members and len(d.cycle_members) == 2
            assert b.summary and not any(ch.isdigit() for ch in b.summary.replace("D1", "").replace("D9", ""))
            if known:
                assert b.placement.house is not None and 1 <= b.placement.house <= 12
                houses = [h.house for h in b.houses_ruled or []]
                assert houses == sorted(houses) and all(1 <= h <= 12 for h in houses)
                assert b.target.ref not in b.sits_with
            else:
                assert b.placement.house is None and b.placement.deg_in_sign is None and b.other_chart is None
