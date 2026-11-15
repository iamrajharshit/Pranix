# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path

import pytest

from pranix.geo.index import GeoIndex, haversine_km
from pranix.geo.tz import tz_at


@pytest.fixture(scope="module")
def g(geo_db: Path) -> GeoIndex:
    return GeoIndex(geo_db)


@pytest.mark.parametrize(
    ("q", "first"),
    [
        ("pun", "Pune"),
        ("Poona", "Pune"),
        ("bogota", "Bogotá"),
        ("new y", "New York City"),
        ("Pune, India", "Pune"),
        ("paris france", "Paris"),
        ("MUMBAI", "Mumbai"),
    ],
)
def test_search(g: GeoIndex, q: str, first: str) -> None:
    assert g.search(q)[0].name == first


def test_search_ranks_by_population_and_respects_limit(g: GeoIndex) -> None:
    assert [p.name for p in g.search("pun")] == ["Pune", "Punalur"]
    assert len(g.search("india", limit=2)) == 2


def test_search_handles_junk_safely(g: GeoIndex) -> None:
    # Punctuation and digits never reach the FTS query; injection attempts just find nothing.
    for q in ["zz", "12345", '") OR 1=1 --', "*", "NEAR(a b)", "a" * 80]:
        assert g.search(q) == []


def test_place_fields(g: GeoIndex) -> None:
    p = g.search("pune")[0]
    assert (p.admin1, p.country, p.tz, p.place_id) == ("Maharashtra", "India", "Asia/Kolkata", "geonames:100001")
    assert g.get("geonames:100001") == p and g.get("geonames:999") is None and g.get("bad") is None


def test_nearest(g: GeoIndex) -> None:
    hit = g.nearest(18.55, 73.85)
    assert hit is not None and hit[0].name == "Pune" and 3 < hit[1] < 4
    assert g.nearest(15.0, 70.0) is None  # sea, nothing within 50 km


def test_haversine() -> None:
    assert abs(haversine_km(18.5204, 73.8567, 19.0760, 72.8777) - 120) < 5  # Pune to Mumbai


def test_tz_from_coordinates() -> None:
    assert tz_at(18.5204, 73.8567) == "Asia/Kolkata"
    assert tz_at(48.8566, 2.3522) == "Europe/Paris"
    assert tz_at(15.0, 70.0) is None  # Arabian Sea
    with pytest.raises(ValueError):
        tz_at(95, 0)
