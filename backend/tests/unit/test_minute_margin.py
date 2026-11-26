# SPDX-License-Identifier: AGPL-3.0-only
"""D83: signs that could differ within the birth time's own margin; I4: the house lord in the other chart."""

import dataclasses
import json
from datetime import date, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pranix.ephemeris import angles
from pranix.ephemeris.master import WINDOW_MIN, BirthInput, canonical_json, compute
from pranix.ephemeris.ruleset import load_ruleset
from pranix.insight.inspect_text import minute_note, with_text
from pranix.insight.validators import check_text
from pranix.jyotish import build_set
from pranix.jyotish.bundle import MayChange

AS_OF = date(2026, 11, 14)
SAMPLE = BirthInput(datetime(1984, 12, 8, 0, 20), "Asia/Kolkata", 18.5204, 73.8567)  # invented, not a person
RS = load_ruleset()


def at(acc: str | None) -> dict:
    return compute(dataclasses.replace(SAMPLE, time_accuracy=acc), AS_OF)  # type: ignore[arg-type]


def test_windows_are_the_owners_choice() -> None:
    assert WINDOW_MIN == {"exact": 2, "approx_5m": 5, "approx_30m": 30, "approx_1h": 60}


def test_sample_exact_flags_the_d9_rising_sign_only() -> None:
    m = at(None)  # not stated counts as exact
    assert m["flags"]["minute_window"] == 2
    assert m["flags"]["minute_sensitive"] == [{"fact_id": "d9.lagna.sign", "values": ["Virgo", "Libra"]}]
    assert m["d9"]["lagna"]["sign"] == "Libra"  # the value shown never changes, only the note


def test_an_hour_flags_the_rising_sign_and_lists_every_option() -> None:
    f = at("approx_1h")["flags"]
    assert f["minute_window"] == 60
    by = {x["fact_id"]: x["values"] for x in f["minute_sensitive"]}
    assert by["lagna.sign"] == ["Leo", "Virgo"]
    assert by["d9.lagna.sign"][0] == "Taurus" and by["d9.lagna.sign"][-1] == "Aquarius"
    assert len(by["d9.lagna.sign"]) == len(set(by["d9.lagna.sign"])) == 10  # in time order, no repeats


def test_values_are_identical_whatever_the_stated_accuracy() -> None:
    a, b = at("exact"), at("approx_1h")
    for k in ("d1", "d9", "nakshatra", "dasha", "colors", "days"):
        assert a[k] == b[k]


def test_deterministic_and_absent_without_a_birth_time() -> None:
    assert canonical_json(at("approx_30m")) == canonical_json(at("approx_30m"))
    u = compute(dataclasses.replace(SAMPLE, birth_time_known=False), AS_OF)
    assert u["flags"]["minute_window"] is None and u["flags"]["minute_sensitive"] == []


@settings(max_examples=25, deadline=None)
@given(
    minutes=st.integers(min_value=0, max_value=60 * 24 * 365 * 40),
    acc=st.sampled_from(["exact", "approx_5m", "approx_30m", "approx_1h"]),
)
def test_every_option_list_contains_the_shown_value_and_matches_the_ends(minutes: int, acc: str) -> None:
    when = datetime(1960, 1, 1, 0, 0) + timedelta(minutes=minutes)
    inp = dataclasses.replace(SAMPLE, local_datetime=when, time_accuracy=acc)  # type: ignore[arg-type]
    m = compute(inp, AS_OF)
    shown = {"lagna.sign": m["d1"]["lagna"]["sign"], "d9.lagna.sign": m["d9"]["lagna"]["sign"]}
    shown |= {f"d9.{p['id'].lower()}.sign": p["sign"] for p in m["d9"]["planets"]}
    for item in m["flags"]["minute_sensitive"]:
        assert item["values"][0] != item["values"][-1] or len(item["values"]) > 2
        assert shown[item["fact_id"]] in item["values"]  # the chart we show is always one of the options


def test_a_sign_edge_inside_the_margin_is_caught() -> None:
    """Walk the sample forward a minute at a time until the D9 rising sign changes: just before and
    just after that minute, the flag must name both signs."""
    base = at("exact")["d9"]["lagna"]["sign"]
    for step in range(1, 30):
        m = compute(dataclasses.replace(SAMPLE, local_datetime=SAMPLE.local_datetime + timedelta(minutes=step)), AS_OF)
        if m["d9"]["lagna"]["sign"] != base:
            before = compute(
                dataclasses.replace(SAMPLE, local_datetime=SAMPLE.local_datetime + timedelta(minutes=step - 1)), AS_OF
            )
            for chart in (m, before):
                d9 = {x["fact_id"]: x["values"] for x in chart["flags"]["minute_sensitive"]}["d9.lagna.sign"]
                assert base in d9 and m["d9"]["lagna"]["sign"] in d9
            return
    pytest.fail("no D9 rising change within half an hour")  # the rising degree moves ~1° every 4 minutes


def test_angles_agree_with_the_flag_definition() -> None:
    assert angles.d9_sign_index(140.295) == 6 and angles.d9_sign_index(139.9) == 5  # Libra / Virgo (rule 7)


# ---------- the Inspector ----------


def test_inspector_carries_the_note_on_every_panel() -> None:
    s = with_text(build_set(at(None), "d1", RS))
    assert s.minute_window == 2
    assert s.may_change == [MayChange(what="rising", chart="d9", options=["Virgo", "Libra"])]
    assert s.minute_note == (
        "Within your birth time's margin, your D9 rising sign could be Virgo or Libra, which would move the D9 houses."
    )
    assert all(b.may_change == [] for b in s.bundles.values())  # no planet's own D9 sign is in doubt here


def test_planet_note_and_many_options_wording() -> None:
    m = at("exact")
    m = json.loads(json.dumps(m))
    m["flags"]["minute_sensitive"].append({"fact_id": "d9.moon.sign", "values": ["Aries", "Taurus"]})
    s = with_text(build_set(m, "d9", RS))
    assert (
        s.bundles["planet:Moon"].minute_note
        == "Within your birth time's margin, Moon's D9 sign could be Aries or Taurus."
    )
    note = minute_note([MayChange(what="rising", chart="d1", options=["Leo", "Virgo", "Libra"])])
    assert note == (
        "Within your birth time's margin, your rising sign could be any of several signs from Leo to Libra, "
        "which would move every house."
    )
    for text in (s.minute_note, s.bundles["planet:Moon"].minute_note, note):
        check_text("minute_note", text)  # no numerals, calm wording (rules 2 and 13)


def test_old_cached_charts_without_the_flag_still_inspect() -> None:
    m = json.loads(json.dumps(at(None)))
    del m["flags"]["minute_sensitive"], m["flags"]["minute_window"]
    s = build_set(m, "d1", RS)
    assert s.may_change == [] and s.minute_window is None


@pytest.mark.parametrize("chart", ["d1", "d9"])
def test_every_house_names_where_its_lord_sits_in_the_other_chart(chart: str) -> None:
    m = at(None)
    other = "d9" if chart == "d1" else "d1"
    planets = {p["id"]: p for p in m[other]["planets"]}
    s = build_set(m, chart, RS)  # type: ignore[arg-type]
    for h in range(1, 13):
        b = s.bundles[f"house:{h}"]
        assert b.lord is not None and b.lord_other_chart is not None
        o = planets[b.lord.planet]
        assert (b.lord_other_chart.planet, b.lord_other_chart.sign, b.lord_other_chart.house) == (
            b.lord.planet,
            o["sign"],
            o["house"],
        )
