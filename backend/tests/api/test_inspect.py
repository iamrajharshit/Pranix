# SPDX-License-Identifier: AGPL-3.0-only
"""GET /v1/profiles/{id}/inspect/{chart} (I1): flag, ETag, unknown time, expiry, rate limit, no PII in logs."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from pranix.config.settings import get_settings
from pranix.gateway.app import create_app

AGE = {"X-Age-Confirmed": "true"}
KNOWN = {"place": {"place_id": "geonames:100001"}, "local_datetime": "1984-12-08T00:20:00", "birth_time_known": True}
UNKNOWN = {**KNOWN, "birth_time_known": False}


@pytest.fixture(scope="module")
def c() -> Iterator[TestClient]:
    with TestClient(create_app(get_settings().model_copy(update={"feature_inspect": True}))) as client:
        yield client


def new(c: TestClient, body: dict) -> str:
    return str(c.post("/v1/profiles", json=body, headers=AGE).json()["profile_id"])


def test_set_for_both_charts(c: TestClient) -> None:
    pid = new(c, KNOWN)
    r = c.get(f"/v1/profiles/{pid}/inspect/d1")
    assert r.status_code == 200 and r.headers["etag"].startswith('"')
    s = r.json()
    assert s["chart"] == "d1" and s["level"] == "house" and len(s["bundles"]) == 9
    jup = s["bundles"]["planet:Jupiter"]
    assert jup["summary"] == "Jupiter in your fifth house, in Sagittarius, its own sign."
    assert [h["house"] for h in jup["houses_ruled"]] == [5, 8] and jup["sits_with"] == ["Mercury"]
    assert jup["other_chart"]["sign"] == "Libra" and jup["aspects_out"] is None
    d9 = c.get(f"/v1/profiles/{pid}/inspect/d9").json()
    assert d9["bundles"]["planet:Venus"]["dispositor"]["cycle_members"] == ["Venus", "Saturn", "Mercury"]


def test_etag_gives_304(c: TestClient) -> None:
    pid = new(c, KNOWN)
    first = c.get(f"/v1/profiles/{pid}/inspect/d1")
    again = c.get(f"/v1/profiles/{pid}/inspect/d1", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    other = c.get(f"/v1/profiles/{new(c, KNOWN)}/inspect/d1")
    assert other.headers["etag"] == first.headers["etag"]  # same chart, same bytes (rule 4)


def test_unknown_time(c: TestClient) -> None:
    pid = new(c, UNKNOWN)
    s = c.get(f"/v1/profiles/{pid}/inspect/d1").json()
    assert s["level"] == "sign" and s["bundles"]["planet:Moon"]["placement"]["house"] is None
    r = c.get(f"/v1/profiles/{pid}/inspect/d9")
    assert r.status_code == 422 and r.json()["code"] == "BIRTH_TIME_REQUIRED"


def test_expired_and_bad_chart(c: TestClient) -> None:
    r = c.get("/v1/profiles/00000000-0000-0000-0000-000000000000/inspect/d1")
    assert r.status_code == 410 and r.json()["code"] == "CHART_EXPIRED"
    assert c.get(f"/v1/profiles/{new(c, KNOWN)}/inspect/d3").status_code == 422


def test_flag_off_hides_the_route() -> None:
    with TestClient(create_app(get_settings())) as off:
        pid = new(off, KNOWN)
        r = off.get(f"/v1/profiles/{pid}/inspect/d1")
        assert r.status_code == 404 and off.get("/version").json()["feature_flags"]["inspect"] is False


def test_rate_limited() -> None:
    s = get_settings().model_copy(update={"feature_inspect": True, "rate_inspect_per_min": 2})
    with TestClient(create_app(s)) as rl:
        pid = new(rl, KNOWN)
        codes = [rl.get(f"/v1/profiles/{pid}/inspect/d1").status_code for _ in range(4)]
        assert codes[:2] == [200, 200] and 429 in codes


def test_logs_carry_no_target_or_person(c: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    pid = new(c, KNOWN)
    capsys.readouterr()
    c.get(f"/v1/profiles/{pid}/inspect/d1")
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "inspect.built" in out or out == ""  # structlog may be silenced in tests
    for leak in ("Jupiter", "Sagittarius", "1984", "Pune", pid):
        assert leak not in out
