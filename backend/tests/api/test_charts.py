# SPDX-License-Identifier: AGPL-3.0-only
"""Dasha timeline and card image endpoints."""

from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path

import pytest
from spa_client import TestClient

from pranix.cardimg.render import CardImageUnavailable, Renderer
from pranix.config.settings import Settings, get_settings
from pranix.gateway.app import create_app

AGE = {"X-Age-Confirmed": "true"}
KNOWN = {"place": {"place_id": "geonames:100001"}, "local_datetime": "1984-12-08T00:20:00", "birth_time_known": True}
UNKNOWN = {**KNOWN, "birth_time_known": False}


def _images_available() -> bool:
    try:
        Renderer(get_settings().fonts_dir)
        return True
    except CardImageUnavailable:
        return False


needs_images = pytest.mark.skipif(not _images_available(), reason="card-image fonts or Cairo not installed")


@pytest.fixture(scope="module")
def c() -> Iterator[TestClient]:
    with TestClient(create_app(get_settings())) as client:
        yield client


def new(c: TestClient, body: dict) -> str:
    return str(c.post("/v1/profiles", json=body, headers=AGE).json()["profile_id"])


def test_mahadashas(c: TestClient) -> None:
    pid = new(c, KNOWN)
    d = c.get(f"/v1/profiles/{pid}/dasha").json()
    assert len(d) == 9 and d[0]["from_birth"] is True and d[0]["lord"] == "Moon"
    assert [p["lord"] for p in d if p["contains_now"]] in (["Jupiter"], ["Saturn"])  # Jupiter until Aug 2032
    assert all(a["end"] == b["start"] for a, b in pairwise(d))


def test_children_and_depth(c: TestClient) -> None:
    pid = new(c, KNOWN)
    kids = c.get(f"/v1/profiles/{pid}/dasha", params={"path": "Ju>Ve"}).json()
    assert [k["path"] for k in kids][:2] == ["Ju>Ve>Ve", "Ju>Ve>Su"] and len(kids) == 9
    deepest = c.get(f"/v1/profiles/{pid}/dasha", params={"path": "Ju>Ve>Me>Ra"}).json()
    assert len(deepest) == 9 and all(k["level"] == 5 for k in deepest)
    assert c.get(f"/v1/profiles/{pid}/dasha", params={"path": "Ju>Ve>Me>Ra>Ra"}).status_code == 422
    assert c.get(f"/v1/profiles/{pid}/dasha", params={"path": "Xx"}).status_code == 422


def test_unknown_time_timeline_is_withheld_when_it_changes(c: TestClient) -> None:
    r = c.get(f"/v1/profiles/{new(c, UNKNOWN)}/dasha")
    assert r.status_code == 422 and r.json()["code"] == "BIRTH_TIME_REQUIRED"


def test_expired(c: TestClient) -> None:
    r = c.get("/v1/profiles/00000000-0000-0000-0000-000000000000/dasha")
    assert r.status_code == 410


@needs_images
def test_card_image(c: TestClient) -> None:
    pid = new(c, KNOWN)
    r = c.get(f"/v1/profiles/{pid}/cards/birthstar.png")
    assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert r.headers["content-type"] == "image/png" and r.headers["x-card-source"] == "curated"
    assert 'filename="pranix-birthstar.png"' in r.headers["content-disposition"]
    again = c.get(f"/v1/profiles/{pid}/cards/birthstar.png")
    assert again.content == r.content and again.headers["etag"] == r.headers["etag"]
    assert (
        c.get(f"/v1/profiles/{pid}/cards/birthstar.png", headers={"if-none-match": r.headers["etag"]}).status_code
        == 304
    )


@needs_images
def test_card_image_rules(c: TestClient) -> None:
    pid = new(c, UNKNOWN)
    r = c.get(f"/v1/profiles/{pid}/cards/deity.png")  # unavailable without a birth time
    assert r.status_code == 404 and r.json()["code"] == "CARD_NOT_AVAILABLE"
    assert c.get(f"/v1/profiles/{pid}/cards/tarot.png").status_code == 404


def test_images_unavailable_without_fonts(tmp_path: Path) -> None:
    s = Settings(fonts_dir=str(tmp_path), geo_db_path=get_settings().geo_db_path)
    with TestClient(create_app(s)) as client:
        pid = new(client, KNOWN)
        r = client.get(f"/v1/profiles/{pid}/cards/identity.png")
        assert r.status_code == 503 and r.json()["code"] == "SERVICE_NOT_READY"
        assert client.get("/readyz").status_code == 200  # images are optional


def test_an_old_chart_lives_in_the_second_cycle(c: TestClient) -> None:
    """D84: born 1905, so the first 120-year run has ended; the sequence starts again."""
    place = {"lat": 18.5204, "lon": 73.8567}
    body = {"place": place, "local_datetime": "1905-03-10T06:00:00", "birth_time_known": True}
    r = c.post("/v1/profiles", json=body, headers={"X-Age-Confirmed": "true"})
    assert r.status_code == 201
    m, pid = r.json()["master"], r.json()["profile_id"]
    chain = m["dasha"]["active_chain"]
    assert chain and len(chain) == 5 and chain[0]["cycle"] == 2
    now = c.get(f"/v1/profiles/{pid}/dasha").json()
    assert len(now) == 9 and all(p["cycle"] == 2 for p in now) and sum(p["contains_now"] for p in now) == 1
    first = c.get(f"/v1/profiles/{pid}/dasha", params={"cycle": 1}).json()
    assert first[0].get("from_birth") and "cycle" not in first[0] and not any(p["contains_now"] for p in first)
    kids = c.get(f"/v1/profiles/{pid}/dasha", params={"path": now[0]["path"], "cycle": 2}).json()
    assert len(kids) == 9 and all(k["cycle"] == 2 for k in kids)
    assert c.get(f"/v1/profiles/{pid}/dasha", params={"cycle": 99}).status_code == 422
