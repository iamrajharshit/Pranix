# SPDX-License-Identifier: AGPL-3.0-only
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from pranix.config.settings import Settings, get_settings
from pranix.gateway.app import create_app
from pranix.insight.cards import MODULES

AGE = {"X-Age-Confirmed": "true"}
BODY = {"place": {"place_id": "geonames:100001"}, "local_datetime": "1984-12-08T00:20:00", "birth_time_known": True}


def events(text: str) -> list[tuple[str, str | None, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        name = eid = data = None
        for line in block.splitlines():
            k, _, v = line.partition(": ")
            if k == "event":
                name = v
            elif k == "id":
                eid = v
            elif k == "data":
                data = json.loads(v)
        out.append((name, eid, data))
    return out


@pytest.fixture(scope="module")
def c() -> Iterator[TestClient]:
    with TestClient(create_app(get_settings())) as client:
        yield client


def test_full_stream(c: TestClient) -> None:
    pid = c.post("/v1/profiles", json=BODY, headers=AGE).json()["profile_id"]
    r = c.get(f"/v1/profiles/{pid}/insights")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = events(r.text)
    assert ev[0][0] == "plan" and ev[0][2] == {"modules": list(MODULES), "chart_ref": pid}
    cards = [e for e in ev if e[0] == "insight"]
    assert sorted(e[1] for e in cards) == sorted(MODULES)
    assert all(e[2]["chart_ref"] == pid and e[2]["module_id"] == e[1] for e in cards)
    assert all(e[2]["state"] == "ready" for e in cards)
    assert ev[-1] == ("done", None, {"degraded": False})


def test_subset_and_errors(c: TestClient) -> None:
    pid = c.post("/v1/profiles", json=BODY, headers=AGE).json()["profile_id"]
    ev = events(c.get(f"/v1/profiles/{pid}/insights", params={"modules": "deity,season"}).text)
    assert ev[0][2]["modules"] == ["season", "deity"] and len(ev) == 4
    assert c.get(f"/v1/profiles/{pid}/insights", params={"modules": "tarot"}).status_code == 422
    r = c.get("/v1/profiles/00000000-0000-0000-0000-000000000000/insights")
    assert r.status_code == 410 and r.json()["code"] == "CHART_EXPIRED"


def test_version_lists_no_providers_without_keys(c: TestClient) -> None:
    assert c.get("/version").json()["ai_providers"] == []


def test_insights_rate_limit() -> None:
    s = Settings(rate_insights_per_min=1, geo_db_path=get_settings().geo_db_path)
    with TestClient(create_app(s)) as client:
        pid = client.post("/v1/profiles", json=BODY, headers=AGE).json()["profile_id"]
        assert client.get(f"/v1/profiles/{pid}/insights").status_code == 200
        assert client.get(f"/v1/profiles/{pid}/insights").status_code == 429
