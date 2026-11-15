# SPDX-License-Identifier: AGPL-3.0-only
"""App factory (thin gateway, ARCH-04): health, version, places and guest charts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .. import __version__
from ..config.settings import Settings, get_settings
from ..ephemeris import selftest, swe
from ..ephemeris.master import SCHEMA_VERSION
from ..ephemeris.ruleset import load_ruleset
from ..geo.index import GeoIndex
from ..obs.logging import configure
from . import routes_geo, routes_profiles
from .guest_store import GuestStore
from .problems import install
from .ratelimit import TokenBucket

log = structlog.get_logger()
MAX_BODY_BYTES = 8_192


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        problems = settings.problems()
        if problems:  # prod only: refuse to start without required secrets (CFG-01)
            raise RuntimeError("; ".join(problems))
        swe.init(settings.ephe_path)
        result = selftest.run()
        failures = list(result.failures)
        try:
            app.state.geo = GeoIndex(settings.geo_db_path)
            log.info("geo.ready", places=app.state.geo.count)
        except (FileNotFoundError, OSError):
            failures.append("geo_index_missing")
        app.state.ready, app.state.failures = not failures, failures
        log.info("selftest.result", ok=result.ok, failures=failures, ephemeris_mode=swe.mode())
        yield

    app = FastAPI(title="Pranix API", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.geo = None
    app.state.ready, app.state.failures = False, []
    app.state.guests = GuestStore(settings.guest_ttl_seconds, settings.guest_cache_max)
    app.state.limits = {
        "places": TokenBucket(settings.rate_places_per_min),
        "profiles": TokenBucket(settings.rate_profiles_per_min),
    }
    install(app)

    @app.middleware("http")
    async def limit_body(request: Request, call_next: Any) -> Any:
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse(
                {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": "Request is too large.",
                    "retry_after": None,
                    "reset_at": None,
                    "request_id": "-",
                },
                status_code=413,
                media_type="application/problem+json",
            )
        return await call_next(request)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    def readyz() -> JSONResponse:
        if app.state.ready:
            return JSONResponse({"status": "ready"})
        return JSONResponse({"status": "not_ready", "failures": app.state.failures}, status_code=503)

    @app.get("/version", tags=["ops"])
    def version() -> dict[str, Any]:
        rs = load_ruleset()
        return {
            "engine_version": __version__,
            "schema_version": SCHEMA_VERSION,
            "ruleset": {"id": rs.id, "version": rs.version, "hash": rs.hash},
            "ephemeris_mode": swe.mode(),
            "feature_flags": {"chat": settings.feature_chat, "passkeys": settings.feature_passkeys},
        }

    app.include_router(routes_geo.router)
    app.include_router(routes_profiles.router)
    return app


app = create_app()
