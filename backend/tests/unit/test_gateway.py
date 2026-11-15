# SPDX-License-Identifier: AGPL-3.0-only
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from pranix.config.settings import get_settings
from pranix.gateway.app import create_app


@pytest.fixture(scope="module")
def c() -> Iterator[TestClient]:
    with TestClient(create_app()) as client:
        yield client


def test_health_ready_version(c: TestClient) -> None:
    assert c.get("/healthz").json() == {"status": "ok"}
    assert c.get("/readyz").status_code == 200
    v = c.get("/version").json()
    assert v["ruleset"]["id"] == "vedic-core" and v["feature_flags"]["chat"] is False


def test_places(c: TestClient) -> None:
    r = c.get("/v1/places", params={"q": "pun"})
    assert r.status_code == 200 and [p["name"] for p in r.json()] == ["Pune", "Punalur"]
    assert r.json()[0] == {
        "place_id": "geonames:100001",
        "name": "Pune",
        "admin1": "Maharashtra",
        "country": "India",
        "lat": 18.5204,
        "lon": 73.8567,
        "tz": "Asia/Kolkata",
    }
    assert c.get("/v1/places", params={"q": "zzzz"}).json() == []


def test_invalid_query_is_a_problem_without_echo(c: TestClient) -> None:
    r = c.get("/v1/places", params={"q": "P"})
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "INVALID_REQUEST" and "q" in body["message"] and body["request_id"]
    r = c.get("/v1/places/nearest", params={"lat": "18.987654", "lon": "999"})
    assert r.status_code == 422 and "18.987654" not in r.text and "999" not in r.text


def test_nearest(c: TestClient) -> None:
    r = c.get("/v1/places/nearest", params={"lat": 18.55, "lon": 73.85}).json()
    assert r["place"]["name"] == "Pune" and r["tz"] == "Asia/Kolkata" and r["distance_km"] == 3
    far = c.get("/v1/places/nearest", params={"lat": 23.0, "lon": 10.0}).json()  # Sahara: land, no town
    assert far["place"] is None and far["distance_km"] is None and far["tz"].startswith("Africa/")
    sea = c.get("/v1/places/nearest", params={"lat": 15.0, "lon": 70.0})
    assert sea.status_code == 422 and sea.json()["code"] == "OCEAN_OR_NO_TZ"


def test_not_found_is_a_problem(c: TestClient) -> None:
    r = c.get("/nope")
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"


def test_missing_geo_index_means_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRANIX_GEO_DB_PATH", "/nonexistent/geonames.sqlite")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            r = client.get("/readyz")
            assert r.status_code == 503 and "geo_index_missing" in r.json()["failures"]
            p = client.get("/v1/places", params={"q": "pune"})
            assert p.status_code == 503 and p.json()["code"] == "SERVICE_NOT_READY" and p.headers["Retry-After"] == "30"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
