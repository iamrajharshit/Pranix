# SPDX-License-Identifier: AGPL-3.0-only
"""An unexpected error (bug bounty, 26 Nov).

Before: the answer was plain text, nothing was logged by the app (a production 500 left no trace),
and the error went on up to the server, whose log prints the exception message. Messages can carry
input values (pydantic puts `input_value=` in them), so a birth date could reach the log.
Now: problem+json with INTERNAL_ERROR and a request id; one safe log line with the same id, the
error type, the route and file:line frames, never the message or local values.
"""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from spa_client import TestClient

from pranix.gateway import routes_profiles
from pranix.gateway.app import create_app

SECRET = "1984-12-08T00:20:00 18.5204 73.8567"


@pytest.fixture
def crashing(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    def boom(inp: Any, *a: Any, **k: Any) -> Any:
        where = SECRET  # a local holding birth data, and the same text in the message
        raise RuntimeError("engine fell over on " + where)

    monkeypatch.setattr(routes_profiles, "compute", boom)
    # raise_server_exceptions=True (the default): the error must not escape the app at all
    with TestClient(create_app()) as c:
        yield c


def _post(c: TestClient) -> Any:
    body = {
        "place": {"lat": 18.5204, "lon": 73.8567},
        "local_datetime": "1984-12-08T00:20:00",
        "birth_time_known": True,
    }
    return c.post("/v1/profiles", json=body, headers={"X-Age-Confirmed": "true"})


def test_unexpected_error_is_a_problem_with_a_request_id(
    crashing: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    r = _post(crashing)
    assert r.status_code == 500 and r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "INTERNAL_ERROR" and len(body["request_id"]) == 16
    assert "fell over" not in r.text and "1984" not in r.text
    assert r.headers["cache-control"] == "private, no-store"

    logged = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    crash = [e for e in logged if e.get("event") == "http.unhandled"]
    assert len(crash) == 1
    e = crash[0]
    assert e["error"] == "RuntimeError" and e["request_id"] == body["request_id"]
    assert e["route"] == "/v1/profiles" and any("test_unhandled_errors.py" in f for f in e["frames"])
    access = [x for x in logged if x.get("event") == "http.request" and x.get("route") == "/v1/profiles"]
    assert access and access[-1]["status"] == 500  # the access log sees the 500 too
    everything = "\n".join(json.dumps(x) for x in logged)
    for needle in ("1984-12-08", "18.5204", "73.8567", "fell over"):
        assert needle not in everything
