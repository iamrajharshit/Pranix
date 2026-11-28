# SPDX-License-Identifier: AGPL-3.0-only
"""D85 (CSRF enforced) and D86 (no API map in production; the 503 says what is missing)."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient  # the plain client: no CSRF header unless a test adds one

from pranix.config.settings import Settings
from pranix.gateway.app import create_app

BODY = {"place": {"place_id": "geonames:100001"}, "local_datetime": "1984-12-08T00:20:00", "birth_time_known": True}
AGE = {"X-Age-Confirmed": "true"}
SPA = {"X-Requested-With": "pranix-spa"}


@pytest.fixture(scope="module")
def c() -> Iterator[TestClient]:
    with TestClient(create_app()) as client:
        yield client


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/v1/profiles"),
        ("DELETE", "/v1/profiles/00000000-0000-4000-8000-000000000000"),
        ("POST", "/v1/telemetry"),
    ],
)
def test_a_changing_request_without_the_header_is_refused(c: TestClient, method: str, path: str) -> None:
    r = c.request(method, path, json=BODY, headers=AGE)
    assert r.status_code == 403 and r.json()["code"] == "CSRF_REQUIRED"


def test_a_wrong_header_value_is_refused(c: TestClient) -> None:
    r = c.post("/v1/profiles", json=BODY, headers={**AGE, "X-Requested-With": "XMLHttpRequest"})
    assert r.status_code == 403


def test_a_cross_site_request_is_refused_even_with_the_header(c: TestClient) -> None:
    r = c.post("/v1/profiles", json=BODY, headers={**AGE, **SPA, "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and r.json()["code"] == "CSRF_REQUIRED"


@pytest.mark.parametrize("site", ["same-origin", "none"])
def test_our_page_gets_through(c: TestClient, site: str) -> None:
    r = c.post("/v1/profiles", json=BODY, headers={**AGE, **SPA, "Sec-Fetch-Site": site})
    assert r.status_code == 201


def test_reading_needs_no_header(c: TestClient) -> None:
    assert c.get("/v1/places", params={"q": "pun"}).status_code == 200


def test_the_api_map_is_off_in_production() -> None:
    app = create_app(Settings(env="prod", llm_fake="off", llm_chains="default"))
    assert app.openapi_url is None
    # no start-up here (prod refuses to start without its secrets); routing alone is enough
    assert TestClient(app, raise_server_exceptions=False).get("/openapi.json").status_code == 404
    assert create_app().openapi()["info"]["title"] == "Pranix API"  # the export tool still works


def test_the_api_map_stays_on_for_development(c: TestClient) -> None:
    assert c.get("/openapi.json").status_code == 200


def test_image_503_names_what_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(Settings(fonts_dir="/nowhere/fonts"))
    with TestClient(app, headers=SPA) as client:
        pid = client.post("/v1/profiles", json=BODY, headers=AGE).json()["profile_id"]
        r = client.get(f"/v1/profiles/{pid}/cards/identity.png")
    body: dict[str, Any] = r.json()
    assert r.status_code == 503 and body["code"] == "SERVICE_NOT_READY"
    assert "fonts" in body["message"] and "nowhere" not in body["message"]  # the reason, never a path
