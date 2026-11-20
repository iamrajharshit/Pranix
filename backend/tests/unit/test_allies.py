# SPDX-License-Identifier: AGPL-3.0-only
from pranix.ephemeris import allies
from pranix.ephemeris.ruleset import load_ruleset, load_table
from pranix.ephemeris.swe import Body

RS = load_ruleset()


def bodies(**lons: float) -> list[Body]:
    """Synthetic chart: unspecified planets parked at low degrees so they never become Atmakaraka."""
    base = {
        "Sun": 1.0,
        "Moon": 2.0,
        "Mars": 3.0,
        "Mercury": 4.0,
        "Jupiter": 5.0,
        "Venus": 6.0,
        "Saturn": 7.0,
        "Rahu": 100.0,
        "Ketu": 280.0,
    }
    base.update(lons)
    return [Body(k, v, 1.0, k in ("Rahu", "Ketu")) for k, v in base.items()]


def test_all_venus_colour_fallback_gives_white_and_pink() -> None:
    # Lagna Taurus (Venus), Moon in Libra (Venus), Venus has the highest degree (AK).
    b = bodies(Moon=185.0, Venus=29.5)
    planets = allies.deciding_planets(RS, b, asc=40.0)
    assert planets == [("Venus", ["lagna_lord", "moon_sign_lord", "atmakaraka"])]
    sw = allies.colors(RS, b, asc=40.0)["swatches"]
    assert [(s["name"], s["kind"]) for s in sw] == [("White", "main"), ("Pink", "variant")]


def test_duplicate_colour_lists_every_planet() -> None:
    # Moon (White) and Venus (White) both decide: one swatch naming both planets.
    b = bodies(Moon=5.0, Venus=29.0)  # Moon in Aries (Mars), AK Venus
    sw = allies.colors(RS, b, asc=100.0)["swatches"]  # Lagna Cancer (Moon)
    white = next(s for s in sw if s["name"] == "White")
    assert white["planets"] == ["Moon", "Venus"] and 2 <= len(sw) <= 3


def test_days_follow_the_same_deciding_planets() -> None:
    b = bodies(Moon=185.0, Venus=29.5)
    assert [d["weekday"] for d in allies.days(RS, b, asc=40.0)["items"]] == ["Friday"]


def test_deity_from_empty_twelfth_uses_the_sign_lord() -> None:
    # AK Saturn at 29.9° Aries -> D9 index 8 (Sagittarius); 12th from it is Scorpio, ruled by Mars.
    b = bodies(Saturn=29.9)
    d = allies.ishta_devta(RS, b)
    w = d["working"]
    assert w["atmakaraka"] == "Saturn" and w["karakamsa"] == "Sagittarius" and w["twelfth"] == "Scorpio"
    assert w["occupants"] == [] and w["branch"] == "sign_lord"
    assert (
        d["deciding_planet"] == "Mars" and d["main"] == "Skanda (Kartikeya)" and d["others"] == ["Hanuman", "Narasimha"]
    )


def test_equal_dignity_ties_follow_the_fixed_order() -> None:
    # 12th from a Sagittarius Karakamsa is Scorpio (D9 index 7). Put Jupiter and Sun there:
    # both are friends of Mars, so the tie order (Jupiter before Sun) decides.
    d9_scorpio = 7 * 10 / 3 + 0.5  # inside the 8th navamsa slice of the zodiac -> Scorpio
    b = bodies(Saturn=29.9, Jupiter=d9_scorpio, Sun=d9_scorpio + 120)
    d = allies.ishta_devta(RS, b)
    assert set(d["working"]["occupants"]) >= {"Jupiter", "Sun"}
    assert d["deciding_planet"] == "Jupiter" and d["main"] == "Sambasiva"


def test_naming_table_is_complete() -> None:
    rows = load_table(allies.NAMING).data["nakshatras"]
    assert len(rows) == 27 and all(len(r["syllables"]) == 4 for r in rows)
    assert all(s["deva"] and s["latin"] for r in rows for s in r["syllables"])
    assert [r["nakshatra"] for r in rows] == [n.name for n in RS.nakshatras]


def test_single_planet_with_one_traditional_colour_is_not_padded() -> None:
    # Lagna Aries, Moon in Scorpio, AK Mars: Mars has only Red and no variant (D65: shown alone).
    b = bodies(Moon=215.0, Mars=29.5)
    assert allies.deciding_planets(RS, b, asc=10.0) == [("Mars", ["lagna_lord", "moon_sign_lord", "atmakaraka"])]
    assert [s["name"] for s in allies.colors(RS, b, asc=10.0)["swatches"]] == ["Red"]


def test_dual_and_tridoshic_labels_owner_examples() -> None:
    # D67 (owner, 20 Nov 2026): dual when the second leads the third by the mono gap; else tridoshic.
    from pranix.ephemeris.heuristics import dosha_label

    lab = RS.raw["doshas"]["label"]
    assert dosha_label([60, 30, 10], lab) == "mono"
    assert dosha_label([52, 48, 0], lab) == "dual"  # the sample chart
    assert dosha_label([35, 35, 30], lab) == "tridoshic"
    assert dosha_label([40, 35, 25], lab) == "tridoshic"
