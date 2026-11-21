# SPDX-License-Identifier: AGPL-3.0-only
"""App factory (thin gateway, ARCH-04): health, version, places and guest charts."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .. import __version__
from ..cardimg.render import CardImageUnavailable, Renderer
from ..config.settings import Settings, get_settings
from ..ephemeris import selftest, swe
from ..ephemeris.master import SCHEMA_VERSION
from ..ephemeris.ruleset import load_ruleset
from ..geo.index import GeoIndex
from ..insight.library import Library
from ..insight.pipeline import InsightService
from ..llmgw.build import insights_chain
from ..obs.logging import configure
from ..store.cache import open_cache, start_purger
from . import routes_charts, routes_geo, routes_insights, routes_profiles, web
from .guest_store import GuestStore
from .problems import install
from .ratelimit import TokenBucket

log = structlog.get_logger()
access = structlog.get_logger("pranix.access")
MAX_BODY_BYTES = 8_192


PROVIDER_LABELS = {"gemini": "Google Gemini", "groq": "Groq", "fake": "Test provider"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Uvicorn's own access log prints full URLs, i.e. typed place text and map coordinates
        # (rule 3). Switch it off however the server was started; access_log below is the safe one.
        logging.getLogger("uvicorn.access").disabled = True
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
            log.warning("geo.missing", path=settings.geo_db_path, fix="run tools/fetch_geonames.sh")
        try:
            app.state.renderer = Renderer(settings.fonts_dir)
        except CardImageUnavailable as e:  # optional feature: the rest of the app works without it
            log.warning("cardimg.unavailable", reason=str(e))
        purged = app.state.cache.purge_expired()  # also hourly, from the cleanup timer (Data_model_v1 §4)
        log.info("cache.ready", kind=type(app.state.cache).__name__, entries=app.state.cache.size(), purged=purged)
        app.state.ready, app.state.failures = not failures, failures
        log.info("selftest.result", ok=result.ok, failures=failures, ephemeris_mode=swe.mode())
        log.info(
            "insight.ready",
            library=app.state.library.stats(),
            drafts_served=settings.allow_drafts,
            ai_providers=[f"{li.provider.name}:{li.provider.model}" for li in app.state.insights.chain.links],
        )
        stop_purger = start_purger(app.state.cache)
        yield
        stop_purger()

    app = FastAPI(title="Pranix API", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.geo = None
    app.state.ready, app.state.failures = False, []
    app.state.guests = GuestStore(settings.guest_ttl_seconds, settings.guest_cache_max)
    app.state.limits = {
        "places": TokenBucket(settings.rate_places_per_min),
        "profiles": TokenBucket(settings.rate_profiles_per_min),
        "insights": TokenBucket(settings.rate_insights_per_min),
        "images": TokenBucket(settings.rate_images_per_min),
    }
    app.state.renderer = None
    app.state.image_cache = {}
    app.state.library = Library(allow_drafts=settings.allow_drafts)
    app.state.cache = open_cache(settings.cache_path)
    app.state.insights = InsightService(app.state.library, insights_chain(settings), cache=app.state.cache)
    install(app)

    @app.middleware("http")
    async def access_log(request: Request, call_next: Any) -> Any:
        # Route pattern only (e.g. /v1/places/nearest): never the query string, ids or bodies.
        start = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        access.info(
            "http.request",
            method=request.method,
            route=getattr(route, "path", "unmatched"),
            status=response.status_code,
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
        )
        return response

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
            "ai_providers": sorted(
                {PROVIDER_LABELS.get(li.provider.name, li.provider.name) for li in app.state.insights.chain.links}
            ),
        }

    app.include_router(routes_geo.router)
    app.include_router(routes_profiles.router)
    app.include_router(routes_insights.router)
    app.include_router(routes_charts.router)
    app.state.spa = web.install(app, settings.web_dist)  # after the API routes so they win
    return app


app = create_app()
