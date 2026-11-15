# SPDX-License-Identifier: AGPL-3.0-only
"""Building the place index after the server started works without a restart."""

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from pranix.config.settings import get_settings
from pranix.gateway import routes_geo
from pranix.gateway.app import create_app


def test_index_built_after_startup_is_picked_up(tmp_path: Path, geo_db: Path, monkeypatch) -> None:
    late = tmp_path / "geonames.sqlite"
    monkeypatch.setattr(routes_geo, "RETRY_SECONDS", 0.0)
    s = get_settings().model_copy(update={"geo_db_path": str(late)})
    with TestClient(create_app(s)) as c:
        assert c.get("/readyz").status_code == 503
        assert c.get("/v1/places", params={"q": "Pune"}).status_code == 503
        shutil.copy(geo_db, late)  # e.g. tools/fetch_geonames.sh finished meanwhile
        r = c.get("/v1/places", params={"q": "Pune"})
        assert r.status_code == 200 and r.json()[0]["name"] == "Pune"
        assert c.get("/readyz").json() == {"status": "ready"}
