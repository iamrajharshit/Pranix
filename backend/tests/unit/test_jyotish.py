# SPDX-License-Identifier: AGPL-3.0-only
"""Chart Inspector data (I1): relations checked against the reference the owner verified (D81),
unknown-time rules (D56), wording (rule 2, D81 §3) and determinism (rule 4)."""

import json
from pathlib import Path

import pytest

from pranix.ephemeris.ruleset import load_ruleset
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
    assert [b.either_side.before.house, b.either_side.after.house] == [step(h, 12), step(h, 2)]
    assert b.aspects_out is None and b.aspects_in is None  # I3: waits for the jyotish-core@1 aspect table


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
    assert s.level == "sign" and len(s.bundles) == 9
    for b in s.bundles.values():
        p = b.placement
        assert p.house is None and p.deg_in_sign is None and p.vargottama is None
        assert b.houses_ruled is None and b.other_chart is None and b.either_side is None
        assert {u.what for u in b.unavailable} >= {"house", "houses_ruled", "degree", "d9", "aspects"}
    moon = s.bundles["planet:Moon"]
    assert moon.placement.nakshatra is None and moon.placement.nakshatra_options == ["Rohini", "Mrigashira"]
    assert moon.sits_with == ["Rahu"]  # same sign at sign level
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
    assert {u.what for u in moon.unavailable} >= {"sign", "dignity"}


def test_wording_is_approved_and_digit_free() -> None:
    for master, charts in ((KNOWN, ("d1", "d9")), (UNKNOWN, ("d1",))):
        for chart in charts:
            for b in with_text(build_set(master, chart, RS)).bundles.values():  # type: ignore[arg-type]
                assert b.summary
                check_text("summary", b.summary)  # NO_NUMERALS, fear and medical lists
                if b.placement.dignity_gloss:
                    check_text("gloss", b.placement.dignity_gloss)
    s = with_text(build_set(KNOWN, "d1", RS))
    assert s.bundles["planet:Jupiter"].summary == "Jupiter in your fifth house, in Sagittarius, its own sign."
    assert s.bundles["planet:Rahu"].placement.dignity_gloss == "Shadow node: read through the lord of its sign."
    assert s.bundles["planet:Jupiter"].placement.dignity_gloss is None
    mars9 = with_text(build_set(KNOWN, "d9", RS)).bundles["planet:Mars"].placement.dignity_gloss
    assert mars9 and "alongside the D1" in mars9  # names the other chart


def test_deterministic_bytes_and_etag() -> None:
    a, b = build_set(KNOWN, "d1", RS), build_set(json.loads(json.dumps(KNOWN)), "d1", RS)
    assert canonical(a) == canonical(b) and a.etag() == b.etag()
    assert a.etag() != build_set(KNOWN, "d9", RS).etag()
