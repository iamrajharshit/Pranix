# SPDX-License-Identifier: AGPL-3.0-only
"""Chart Inspector data (I1): relations checked against the reference the owner verified (D81),
unknown-time rules (D56), wording (rule 2, D81 §3) and determinism (rule 4)."""

import json
from pathlib import Path

import pytest

from pranix.ephemeris.ruleset import Table, load_ruleset, load_table
from pranix.insight.inspect_text import with_text
from pranix.insight.validators import check_text
from pranix.jyotish import build_set
from pranix.jyotish.bundle import canonical
from pranix.jyotish.context import step

ROOT = Path(__file__).resolve().parents[3]
FIX = ROOT / "web" / "src" / "__fixtures__"
KNOWN = json.loads((FIX / "sample_1984.json").read_text())
UNKNOWN = json.loads((FIX / "sample_1984_unknown_time.json").read_text())
# Built independently in Python for the prototype and matched by the owner (42 rows, 26 Nov 2026).
REF = json.loads((Path(__file__).parents[1] / "golden" / "inspect_ref_1984.json").read_text())
RS = load_ruleset()
PLANETS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]


@pytest.mark.parametrize("chart", ["d1", "d9"])
@pytest.mark.parametrize("planet", PLANETS)
def test_relations_match_the_verified_reference(chart: str, planet: str) -> None:
    b = build_set(KNOWN, chart, RS).bundles[f"planet:{planet}"]  # type: ignore[arg-type]
    r = REF[f"{chart}|planet|{planet}"]
    assert b.placement is not None and b.dispositor is not None
    if planet in ("Rahu", "Ketu"):
        assert b.houses_ruled == [] and b.acts_through == r["Dispositor chain"][1]
    else:
        assert [h.house for h in b.houses_ruled or []] == r["Houses it rules"]  # sorted by house (D81)
    assert b.sits_with == r["Sits with"]
    assert b.dispositor.steps == r["Dispositor chain"]
    assert b.dispositor.end == r["end"]
    if r["end"] == "cycle":
        assert b.dispositor.cycle_members == r["members"]  # the whole loop (D81 §4.2)
    h = b.placement.house
    assert b.either_side is not None and h is not None
    assert b.house is None and b.lord is None  # planet target
    assert [b.either_side.before.house, b.either_side.after.house] == [step(h, 12), step(h, 2)]
    assert [a.house for a in b.aspects_out or []] == r["Looks at"]  # I3: offset order from the approved table
    assert b.aspects_in == r["Looked at by"] and b.aspects_out_signs is None


def test_houses_ruled_carry_their_occupants() -> None:
    jup = build_set(KNOWN, "d1", RS).bundles["planet:Jupiter"]
    assert [(h.house, h.sign, h.occupants) for h in jup.houses_ruled or []] == [
        (5, "Sagittarius", ["Mercury", "Jupiter"]),
        (8, "Pisces", []),
    ]


def test_bridge_uses_engine_values() -> None:
    s = build_set(KNOWN, "d1", RS)
    mars, moon = s.bundles["planet:Mars"], s.bundles["planet:Moon"]
    assert mars.other_chart and (mars.other_chart.sign, mars.other_chart.dignity, mars.other_chart.change) == (
        "Cancer",
        "debilitated",
        "changed",
    )
    assert moon.placement.vargottama is True  # the engine's field, not recomputed (A3)
    assert s.bundles["planet:Rahu"].other_chart and s.bundles["planet:Rahu"].other_chart.change == "none"
    d9 = build_set(KNOWN, "d9", RS)
    assert d9.bundles["planet:Mars"].placement.deg_in_sign is None  # degrees belong to D1 only
    assert d9.bundles["planet:Moon"].placement.vargottama is True


def test_unknown_time_is_sign_level_and_never_guesses() -> None:
    s = build_set(UNKNOWN, "d1", RS)
    assert s.level == "sign" and len(s.bundles) == 9  # planets only: houses need a birth time (D56)
    assert not any(k.startswith("house:") for k in s.bundles)
    for b in s.bundles.values():
        p = b.placement
        assert p is not None
        assert p.house is None and p.deg_in_sign is None and p.vargottama is None
        assert b.houses_ruled is None and b.other_chart is None and b.either_side is None
        assert {u.what for u in b.unavailable} >= {"house", "houses_ruled", "degree", "d9"}
        assert b.aspects_out is None  # houses need a birth time; aspects are read by sign instead
    moon = s.bundles["planet:Moon"]
    assert moon.placement.nakshatra is None and moon.placement.nakshatra_options == ["Rohini", "Mrigashira"]
    assert moon.sits_with == ["Rahu"]  # same sign at sign level
    assert moon.aspects_out_signs == ["Scorpio"] and moon.aspects_in == ["Sun", "Ketu"]  # by sign (D81 4)
    with pytest.raises(ValueError):
        build_set(UNKNOWN, "d9", RS)


def test_sign_change_during_the_day_stops_the_chain() -> None:
    m = json.loads(json.dumps(UNKNOWN))
    for p in m["d1"]["planets"]:
        if p["id"] == "Moon":
            p["sign"], p["dignity"] = None, None
    m["flags"]["time_sensitive"].append({"fact_id": "moon.sign", "values": ["Taurus", "Gemini"]})
    s = build_set(m, "d1", RS)
    moon = s.bundles["planet:Moon"]
    assert moon.placement.sign_options == ["Taurus", "Gemini"] and moon.sits_with == []
    assert moon.dispositor.end == "stops_uncertain"
    assert "Moon" not in s.bundles["planet:Rahu"].sits_with  # an uncertain sign is never a companion
    assert moon.aspects_out_signs is None and moon.aspects_in is None  # nothing guessed for an uncertain sign
    assert not any("Moon" in (b.aspects_in or []) for b in s.bundles.values())  # nor credited as a looker
    assert {u.what for u in moon.unavailable} >= {"sign", "dignity"}


def test_wording_is_approved_and_digit_free() -> None:
    for master, charts in ((KNOWN, ("d1", "d9")), (UNKNOWN, ("d1",))):
        for chart in charts:
            for b in with_text(build_set(master, chart, RS)).bundles.values():  # type: ignore[arg-type]
                assert b.summary
                check_text("summary", b.summary)  # NO_NUMERALS, fear and medical lists
                if b.placement and b.placement.dignity_gloss:
                    check_text("gloss", b.placement.dignity_gloss)
    s = with_text(build_set(KNOWN, "d1", RS))
    assert s.bundles["planet:Jupiter"].summary == "Jupiter in your fifth house, in Sagittarius, its own sign."
    rahu, jup = s.bundles["planet:Rahu"].placement, s.bundles["planet:Jupiter"].placement
    assert rahu and rahu.dignity_gloss == "Shadow node: read through the lord of its sign."
    assert jup and jup.dignity_gloss is None
    mars_p = with_text(build_set(KNOWN, "d9", RS)).bundles["planet:Mars"].placement
    mars9 = mars_p.dignity_gloss if mars_p else None
    assert mars9 and "alongside the D1" in mars9  # names the other chart


def test_deterministic_bytes_and_etag() -> None:
    a, b = build_set(KNOWN, "d1", RS), build_set(json.loads(json.dumps(KNOWN)), "d1", RS)
    assert canonical(a) == canonical(b) and a.etag() == b.etag()
    assert a.etag() != build_set(KNOWN, "d9", RS).etag()


@pytest.mark.parametrize("chart", ["d1", "d9"])
@pytest.mark.parametrize("house", range(1, 13))
def test_house_panels_match_the_verified_reference(chart: str, house: int) -> None:
    """I2: every house, empty ones too, is read through its occupants and its lord."""
    s = build_set(KNOWN, chart, RS)  # type: ignore[arg-type]
    b = s.bundles[f"house:{house}"]
    r = REF[f"{chart}|house|{house}"]
    assert b.placement is None and b.dispositor is None  # house target
    assert b.house is not None and b.lord is not None and b.either_side is not None
    assert (b.house.house, b.house.sign, b.house.occupants) == (house, r["sign"], r["Occupants"])
    assert (b.lord.planet, b.lord.house) == (r["Its lord"][0], r["lordHouse"])
    assert [b.either_side.before.house, b.either_side.after.house] == r["Either side"]
    other = "d9" if chart == "d1" else "d1"
    o = REF[f"{other}|house|{house}"]
    assert b.same_house_other_chart and (b.same_house_other_chart.sign, b.same_house_other_chart.occupants) == (
        o["sign"],
        o["Occupants"],
    )
    assert b.aspects_in == r["Looked at by"]  # I3


def test_house_wording() -> None:
    s = with_text(build_set(KNOWN, "d1", RS))
    assert s.bundles["house:1"].summary == (
        "Your rising sign. House one is Leo. "
        "It is empty, so it is read through its lord and the planets that look at it."
    )
    assert s.bundles["house:5"].summary == "House five is Sagittarius, with Mercury and Jupiter."
    seven = "House seven is Aquarius. It is empty, so it is read through its lord."
    assert s.bundles["house:7"].summary == seven  # no planet looks at house seven, so none is promised
    for b in s.bundles.values():
        assert b.summary
        check_text("summary", b.summary)


def test_aspects_follow_the_approved_table_and_record_it() -> None:
    """The set names the jyotish-core table it used, so a table change changes the ETag (FR-REV-05)."""
    s = build_set(KNOWN, "d1", RS)
    assert s.rules.id == "jyotish-core" and s.rules.version == 1 and len(s.rules.hash) == 16
    mars = s.bundles["planet:Mars"]
    h = mars.placement.house if mars.placement else None
    assert h is not None and [a.house for a in mars.aspects_out or []] == [step(h, n) for n in (4, 7, 8)]
    other = load_table("jyotish-core@1")
    edited = Table(other.id, other.version, "0" * 16, other.data)
    assert build_set(KNOWN, "d1", RS, edited).etag() != s.etag()


def test_no_planet_looks_at_itself() -> None:
    for chart in ("d1", "d9"):
        for key, b in build_set(KNOWN, chart, RS).bundles.items():  # type: ignore[arg-type]
            if key.startswith("planet:"):
                assert key.split(":")[1] not in (b.aspects_in or [])
