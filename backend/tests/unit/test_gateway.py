# SPDX-License-Identifier: AGPL-3.0-only
from fastapi.testclient import TestClient

from pranix.gateway.app import create_app


def test_health_ready_version() -> None:
    with TestClient(create_app()) as c:
        assert c.get("/healthz").json() == {"status": "ok"}
        assert c.get("/readyz").status_code == 200
        v = c.get("/version").json()
        assert v["ruleset"]["id"] == "vedic-core" and v["feature_flags"]["chat"] is False
