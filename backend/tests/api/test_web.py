# SPDX-License-Identifier: AGPL-3.0-only
"""The built app is served same-origin, API routes win, and security headers are set (HOST-04, NFR-SEC-03)."""

from pathlib import Path

from fastapi.testclient import TestClient

from pranix.config.settings import get_settings
from pranix.gateway.app import create_app


def _dist(tmp: Path) -> Path:
    (tmp / "assets").mkdir()
    (tmp / "index.html").write_text('<!doctype html><div id="root"></div>')
    (tmp / "assets" / "app.js").write_text("console.log('ok')")
    (tmp / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    return tmp


def test_spa_routes_assets_and_headers(tmp_path: Path) -> None:
    s = get_settings().model_copy(update={"web_dist": str(_dist(tmp_path))})
    with TestClient(create_app(s)) as c:
        for route in ("/", "/details", "/dashboard", "/how", "/legal"):
            r = c.get(route)
            assert r.status_code == 200 and 'id="root"' in r.text
            assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
            assert r.headers["x-content-type-options"] == "nosniff"
        assert c.get("/assets/app.js").status_code == 200
        assert c.get("/favicon.ico").headers["content-type"].startswith("image/svg+xml")
        # API paths are never swallowed by the app shell
        assert c.get("/version").headers["content-type"].startswith("application/json")
        assert c.get("/v1/profiles/nope/dasha").headers["content-type"].startswith("application/problem+json")
        assert c.get("/not-a-page").status_code == 404


def test_api_only_when_no_build(tmp_path: Path) -> None:
    s = get_settings().model_copy(update={"web_dist": str(tmp_path / "missing")})
    with TestClient(create_app(s)) as c:
        assert c.get("/").status_code == 404
        assert c.get("/healthz").status_code == 200
        assert "content-security-policy" in c.get("/healthz").headers
