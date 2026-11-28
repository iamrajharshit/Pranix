# SPDX-License-Identifier: AGPL-3.0-only
"""POST/GET/DELETE /v1/profiles (guest charts)."""

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from spa_client import TestClient

from pranix.config.settings import Settings, get_settings
from pranix.gateway.app import create_app
from pranix.gateway.guest_store import GuestStore

AGE = {"X-Age-Confirmed": "true"}
PUNE = {"place_id": "geonames:100001"}  # fixture index
NYC = {"place_id": "geonames:100008"}


def body(**kw: Any) -> dict[str, Any]:
    b: dict[str, Any] = {"place": PUNE, "local_datetime": "1984-12-08T00:20:00", "birth_time_known": True}
    b.update(kw)
    return b


@pytest.fixture(scope="module")
def c() -> Iterator[TestClient]:
    with TestClient(create_app(get_settings())) as client:
        yield client


def test_known_time_chart(c: TestClient) -> None:
    r = c.post("/v1/profiles", json=body(), headers=AGE)
    assert r.status_code == 201
    j = r.json()
    m = j["master"]
    assert j["profile_id"] and j["expires_at"].endswith("Z")
    assert m["d1"]["lagna"]["sign"] == "Leo" and m["nakshatra"]["name"] == "Rohini"
    assert m["ishta_devta"]["main"] == "Gauri (Parvati)"
    assert m["dasha"]["as_of"] == datetime.now(UTC).date().isoformat()
    assert c.get(f"/v1/profiles/{j['profile_id']}").json()["master"] == m


def test_coordinates_and_unknown_time(c: TestClient) -> None:
    r = c.post(
        "/v1/profiles",
        json=body(
            place={"lat": 18.5204, "lon": 73.8567},
            birth_time_known=False,
            local_datetime="1984-12-08T17:45:00",
            time_accuracy="approx_1h",
        ),
        headers=AGE,
    )
    assert r.status_code == 201
    m = r.json()["master"]
    assert m["d1"]["lagna"] is None and m["d9"] is None and m["meta"]["birth_time_known"] is False


def test_age_confirmation_required(c: TestClient) -> None:
    r = c.post("/v1/profiles", json=body())
    assert r.status_code == 412 and r.json()["code"] == "AGE_CONFIRMATION_REQUIRED"


@pytest.mark.parametrize(
    ("dt", "code"),
    [
        ("1799-12-31T10:00:00", "OUT_OF_RANGE"),
        ("2999-01-01T10:00:00", "OUT_OF_RANGE"),
        (f"{date.today().year - 10}-01-01T10:00:00", "UNDER_AGE_PROFILE"),
        ("1990-02-30T10:00:00", "INVALID_REQUEST"),
    ],
)
def test_date_rules(c: TestClient, dt: str, code: str) -> None:
    r = c.post("/v1/profiles", json=body(local_datetime=dt), headers=AGE)
    assert r.status_code == 422 and r.json()["code"] == code


def test_dst_gap_and_fold(c: TestClient) -> None:
    gap = c.post("/v1/profiles", json=body(place=NYC, local_datetime="1990-04-01T02:30:00"), headers=AGE)
    assert gap.status_code == 422 and gap.json()["code"] == "NONEXISTENT_LOCAL_TIME"
    fold = c.post("/v1/profiles", json=body(place=NYC, local_datetime="1990-10-28T01:30:00"), headers=AGE)
    j = fold.json()
    assert fold.status_code == 422 and j["code"] == "AMBIGUOUS_LOCAL_TIME"
    assert [o["disambiguation"] for o in j["options"]] == ["earlier", "later"]
    ok = c.post(
        "/v1/profiles", json=body(place=NYC, local_datetime="1990-10-28T01:30:00", disambiguation="later"), headers=AGE
    )
    assert ok.status_code == 201


def test_bad_places(c: TestClient) -> None:
    r = c.post("/v1/profiles", json=body(place={"place_id": "geonames:999999"}), headers=AGE)
    assert r.status_code == 422 and r.json()["code"] == "INVALID_PLACE"
    r = c.post("/v1/profiles", json=body(place={"lat": 15.0, "lon": 70.0}), headers=AGE)  # Arabian Sea
    assert r.status_code == 422 and r.json()["code"] == "INVALID_PLACE"


def test_guest_profile_fields_are_rejected_without_echo(c: TestClient) -> None:
    for extra in ({"name": "Asha Kulkarni"}, {"pronouns": "she_her"}, {"for_other_person": True}):
        r = c.post("/v1/profiles", json=body(**extra), headers=AGE)
        assert r.status_code == 422 and r.json()["code"] == "INVALID_REQUEST"
        assert "Asha" not in r.text and "she_her" not in r.text


def test_delete_then_expired(c: TestClient) -> None:
    pid = c.post("/v1/profiles", json=body(), headers=AGE).json()["profile_id"]
    assert c.delete(f"/v1/profiles/{pid}").status_code == 204
    r = c.get(f"/v1/profiles/{pid}")
    assert r.status_code == 410 and r.json()["code"] == "CHART_EXPIRED"


def test_ttl_expiry() -> None:
    now = [1_000_000.0]
    app = create_app(get_settings())
    with TestClient(app) as client:
        app.state.guests = GuestStore(ttl_seconds=60, clock=lambda: now[0])
        pid = client.post("/v1/profiles", json=body(), headers=AGE).json()["profile_id"]
        assert client.get(f"/v1/profiles/{pid}").status_code == 200
        now[0] += 61
        assert client.get(f"/v1/profiles/{pid}").status_code == 410


def test_rate_limit() -> None:
    s = Settings(rate_profiles_per_min=2, geo_db_path=get_settings().geo_db_path)
    with TestClient(create_app(s)) as client:
        codes = [client.post("/v1/profiles", json=body(), headers=AGE).status_code for _ in range(3)]
        assert codes == [201, 201, 429]
        r = client.post("/v1/profiles", json=body(), headers=AGE)
        assert r.json()["code"] == "RATE_LIMITED" and int(r.headers["Retry-After"]) >= 1


def test_body_size_limit(c: TestClient) -> None:
    r = c.post("/v1/profiles", content=b"{" + b" " * 9000 + b"}", headers={**AGE, "content-type": "application/json"})
    assert r.status_code == 413


def test_logs_never_receive_birth_data(c: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    c.post("/v1/profiles", json=body(), headers=AGE)
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    created = [e for e in lines if e["event"] == "profile.created"]
    assert len(created) == 1 and len(created[0]["chart_key"]) == 16
    text = json.dumps(lines)
    for secret in ("1984", "12-08", "00:20", "18.52", "73.85", "Pune", "Kolkata", "geonames"):
        assert secret not in text
    assert "[redacted]" not in text  # nothing personal was even handed to the logger


def test_chart_key_is_stable_and_ignores_unknown_time_clock() -> None:
    from datetime import datetime

    from pranix.ephemeris.master import BirthInput
    from pranix.gateway.keys import chart_key

    p = b"pepper"
    a = BirthInput(datetime(1984, 12, 8, 9, 0), "Asia/Kolkata", 18.52041, 73.85669, birth_time_known=False)
    b = BirthInput(datetime(1984, 12, 8, 17, 0), "Asia/Kolkata", 18.5204, 73.8567, birth_time_known=False)
    assert chart_key(p, a) == chart_key(p, b) and chart_key(b"other", a) != chart_key(p, a)


def test_prod_refuses_to_start_without_peppers() -> None:
    s = Settings(env="prod", geo_db_path=get_settings().geo_db_path)
    with pytest.raises(RuntimeError, match="chart_key_pepper"), TestClient(create_app(s)):
        pass
