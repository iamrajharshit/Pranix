# SPDX-License-Identifier: AGPL-3.0-only
"""Serve the built React app same-origin (HOST-04) with security headers (NFR-SEC-03)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

SPA_ROUTES = ("/", "/details", "/dashboard", "/how", "/legal")

# Leaflet and React set inline style attributes; tiles come from OpenStreetMap only (D64).
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https://tile.openstreetmap.org; font-src 'self'; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
)
HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",  # OSM's tile policy needs a referrer
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def install(app: FastAPI, dist: str) -> bool:
    root = Path(dist)
    index = root / "index.html"

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        for k, v in HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    if not index.is_file():
        return False
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    def spa() -> FileResponse:
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    favicon = root / "favicon.svg"
    if favicon.is_file():
        app.add_api_route(
            "/favicon.svg",
            lambda: FileResponse(favicon, media_type="image/svg+xml"),
            methods=["GET"],
            include_in_schema=False,
        )
        app.add_api_route(
            "/favicon.ico",
            lambda: FileResponse(favicon, media_type="image/svg+xml"),
            methods=["GET"],
            include_in_schema=False,
        )

    for route in SPA_ROUTES:
        app.add_api_route(route, spa, methods=["GET"], include_in_schema=False)
    return True
