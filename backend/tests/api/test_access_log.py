# SPDX-License-Identifier: AGPL-3.0-only
"""Request logs carry the route pattern only: never typed place text, coordinates or ids (rule 3)."""

import logging

from fastapi.testclient import TestClient

from pranix.config.settings import get_settings
from pranix.gateway.app import create_app


def test_access_log_has_no_query_or_coordinates(capsys) -> None:
    with TestClient(create_app(get_settings())) as c:
        assert logging.getLogger("uvicorn.access").disabled
        capsys.readouterr()
        c.get("/v1/places", params={"q": "Ranchi", "limit": 8})
        c.get("/v1/places/nearest", params={"lat": 23.3677, "lon": 85.3227})
        c.get("/v1/profiles/abc123secretid/dasha")
    out = capsys.readouterr().out
    assert '"route": "/v1/places"' in out and '"route": "/v1/places/nearest"' in out
    assert '"route": "/v1/profiles/{profile_id}/dasha"' in out
    for leaked in ("Ranchi", "23.3677", "85.3227", "abc123secretid", "q="):
        assert leaked not in out
