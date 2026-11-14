# SPDX-License-Identifier: AGPL-3.0-only
"""Golden sample (invented, not a real person): 8 Dec 1984, 00:20 IST, Pune (QA-01, E3-20, E3-21, E3-23)."""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from pranix.ephemeris import swe
from pranix.ephemeris.angles import format_dm
from pranix.ephemeris.master import BirthInput, canonical_json, compute

HERE = Path(__file__).parent
CHARTS = json.loads((HERE / "sample_1984_charts.json").read_text())
DASHA = json.loads((HERE / "sample_1984_dasha.json").read_text())
IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = date(2026, 11, 14)
KNOWN = BirthInput(datetime(1984, 12, 8, 0, 20), "Asia/Kolkata", 18.5204, 73.8567)
UNKNOWN = BirthInput(datetime(1984, 12, 8, 0, 20), "Asia/Kolkata", 18.5204, 73.8567, birth_time_known=False)
# Degree strings were produced with full precision files; Moshier may differ by a few arc-seconds.
EXACT_DEGREES = swe.mode() == "swieph"


@pytest.fixture(scope="module")
def master() -> dict:
    return compute(KNOWN, AS_OF)


def test_lagna(master: dict) -> None:
    lg = master["d1"]["lagna"]
    assert (lg["sign"], f"{lg['nakshatra']} {lg['pada']}") == (CHARTS["lagna"]["sign"], CHARTS["lagna"]["nak"])
    assert master["d9"]["lagna"]["sign"] == CHARTS["lagna"]["d9"]
    if EXACT_DEGREES:
        assert format_dm(lg["deg_in_sign"]) == CHARTS["lagna"]["deg"]
        assert format_dm(master["meta"]["ayanamsa_value"]) == CHARTS["ayanamsa"]


def test_d1_planets(master: dict) -> None:
    got = {p["id"]: p for p in master["d1"]["planets"]}
    for exp in CHARTS["d1"]["planets"]:
        p = got[exp["id"]]
        assert p["sign"] == exp["sign"] and p["house"] == exp["house"], exp["id"]
        assert f"{p['nakshatra']} {p['pada']}" == exp["nak"], exp["id"]
        assert (p["dignity"] or "") == exp["dignity"], exp["id"]
        assert p["vargottama"] == exp["varg"], exp["id"]
        if exp["id"] not in ("Rahu", "Ketu"):
            assert p["retrograde"] == exp["retro"], exp["id"]
        else:
            assert p["retrograde"] is True  # nodes always retrograde (FR-CAL-01)
        if EXACT_DEGREES:
            assert format_dm(p["deg_in_sign"]) == exp["deg"], exp["id"]


def test_d9_planets(master: dict) -> None:
    got = {p["id"]: p for p in master["d9"]["planets"]}
    for exp in CHARTS["d9"]["planets"]:
        p = got[exp["id"]]
        assert (p["sign"], p["house"], p["dignity"] or "") == (exp["sign"], exp["house"], exp["dignity"]), exp["id"]


def test_purpose_and_heuristics(master: dict) -> None:
    assert master["purpose"]["atmakaraka"] == "Saturn"
    assert master["purpose"]["rahu_ketu_axis"] == {"rahu_house": 10, "ketu_house": 4}
    assert master["elements"]["percent"] == {"Fire": 39, "Earth": 23, "Air": 11, "Water": 21, "Ether": 6}
    assert sum(master["elements"]["percent"].values()) == 100
    assert master["doshas"]["percent"] == {"Vata": 0, "Pitta": 52, "Kapha": 48}
    dominant = {c["id"] for c in master["chakras"] if c["class"] == "dominant"}
    assert dominant == {"muladhara", "svadhisthana", "manipura", "ajna"}


def _ist_date(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(IST).strftime("%d %b %Y")


def test_dasha_chain_matches_reference(master: dict) -> None:
    chain = master["dasha"]["active_chain"]
    assert [p["lord"] for p in chain][:4] == DASHA["cur"]
    assert all(p["contains_now"] for p in chain)
    # Reference dates are Indian local dates.
    assert [_ist_date(chain[0]["start"]), _ist_date(chain[0]["end"])] == DASHA["mahas"][3][1:3]
    assert [_ist_date(chain[1]["start"]), _ist_date(chain[1]["end"])] == DASHA["antars"][4][1:3]
    rahu = next(s for s in DASHA["sook"] if s[0] == "Rahu")
    assert [_ist_date(chain[3]["start"]), _ist_date(chain[3]["end"])] == rahu[1:3]


def test_unknown_time_is_certain_only() -> None:
    m = compute(UNKNOWN, AS_OF)
    ts = {t["fact_id"]: t["values"] for t in m["flags"]["time_sensitive"]}
    assert ts["moon.nakshatra"] == ["Rohini", "Mrigashira"]
    assert ts["mars.nakshatra"] == ["Shravana", "Dhanishta"]
    assert m["d1"]["lagna"] is None and m["d1"]["houses"] is None and m["d9"] is None
    assert all(p["longitude"] is None and p["pada"] is None and p["house"] is None for p in m["d1"]["planets"])
    moon = next(p for p in m["d1"]["planets"] if p["id"] == "Moon")
    assert moon["sign"] == "Taurus" and moon["nakshatra"] is None
    assert m["nakshatra"] is None
    assert m["dasha"]["active_chain"] is None  # chain changes during the day (D56)
    assert m["doshas"]["percent"] == {"Vata": 0, "Pitta": 24, "Kapha": 76}  # B5.2


def test_unknown_time_ignores_the_entered_clock_time() -> None:
    other = BirthInput(
        datetime(1984, 12, 8, 17, 45),
        "Asia/Kolkata",
        18.5204,
        73.8567,
        birth_time_known=False,
        time_accuracy="approx_1h",
    )
    assert canonical_json(compute(other, AS_OF)) == canonical_json(compute(UNKNOWN, AS_OF))


def test_byte_identical_output() -> None:
    assert canonical_json(compute(KNOWN, AS_OF)) == canonical_json(compute(KNOWN, AS_OF))
