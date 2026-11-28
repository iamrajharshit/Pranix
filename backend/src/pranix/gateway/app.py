# SPDX-License-Identifier: AGPL-3.0-only
"""App factory (thin gateway, ARCH-04): health, version, places and guest charts."""

from __future__ import annotations

import json
import logging
import time
import traceback
import uuid
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
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
from ..llmgw.build import reword_gap_s, router
from ..obs.logging import configure
from ..store.cache import open_cache, start_purger
from . import routes_charts, routes_geo, routes_insights, routes_inspect, routes_profiles, web
from .guest_store import GuestStore
from .problems import install
from .ratelimit import TokenBucket

log = structlog.get_logger()
access = structlog.get_logger("pranix.access")
MAX_BODY_BYTES = 8_192


_PLAIN = {
    413: ("PAYLOAD_TOO_LARGE", "Request is too large."),
    500: ("INTERNAL_ERROR", "Something went wrong on our side. Please try again."),
    403: ("CSRF_REQUIRED", "This request must come from the Pranix page."),
}

CHANGING = {"POST", "PUT", "PATCH", "DELETE"}
SPA_HEADER = (b"x-requested-with", b"pranix-spa")


class Csrf:
    """D85: a changing request under /v1 must come from our page.

    It must carry X-Requested-With: pranix-spa (a cross-site page can't add a custom header without
    a preflight, and we allow no cross-origin calls), and a browser that says Sec-Fetch-Site:
    cross-site is refused even with the header. Reads (GET, HEAD, OPTIONS) need nothing."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope["method"] in CHANGING and scope["path"].startswith("/v1/"):
            headers = dict(scope.get("headers") or [])
            ours = headers.get(SPA_HEADER[0]) == SPA_HEADER[1]
            cross = headers.get(b"sec-fetch-site") == b"cross-site"
            if not ours or cross:
                await BodyLimit._refuse(send, 403)
                return
        await self.app(scope, receive, send)


def _plain_problem(status: int = 413) -> dict[str, Any]:
    code, message = _PLAIN.get(status, ("INVALID_REQUEST", "Bad request."))
    return {"code": code, "message": message, "retry_after": None, "reset_at": None, "request_id": "-"}


class Guard:
    """Catches an unexpected error before it leaves the app (bug bounty, 26 Nov).

    Answers problem+json INTERNAL_ERROR with a request id, and logs one line with the same id, the
    error type, the route pattern and file:line frames. Never the message or local values: messages
    can carry input values (pydantic adds `input_value=`), and rule 3 keeps birth data out of logs.
    The error is not re-raised, so the server's own error log (which prints messages) never sees it."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def watch(message: Any) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, watch)
        except Exception as e:
            rid = uuid.uuid4().hex[:16]
            frames = [f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in traceback.extract_tb(e.__traceback__)]
            route = getattr(scope.get("route"), "path", "unmatched")
            log.error("http.unhandled", error=type(e).__name__, route=route, request_id=rid, frames=frames[-12:])
            if started:  # a stream already under way: nothing more can be said, the connection just ends
                return
            body = json.dumps({**_plain_problem(500), "request_id": rid}).encode()
            headers = [(b"content-type", b"application/problem+json"), (b"content-length", str(len(body)).encode())]
            await send({"type": "http.response.start", "status": 500, "headers": headers})
            await send({"type": "http.response.body", "body": body})


class BodyLimit:
    """Caps every request body at MAX_BODY_BYTES, however it arrives (bug bounty, 26 Nov).

    The old check read only the Content-Length header, so a chunked upload (no header) or a header
    that understated the body reached the route's JSON parser at any size. This counts the bytes
    themselves. Our bodies are tiny, so it reads the whole body first, then replays it to the app;
    later receive() calls go straight through, so streams still hear the client disconnect.
    """

    def __init__(self, app: Any, limit: int = MAX_BODY_BYTES) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None:
            if not length.isdigit():
                await self._refuse(send, 400)
                return
            if int(length) > self.limit:
                await self._refuse(send, 413)
                return
        parts: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":  # client left before the body ended
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.limit:
                await self._refuse(send, 413)
                return
            parts.append(chunk)
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay() -> Any:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(parts), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def _refuse(send: Any, status: int) -> None:
        body = json.dumps(_plain_problem(status)).encode()
        headers = [(b"content-type", b"application/problem+json"), (b"content-length", str(len(body)).encode())]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


PROVIDER_LABELS = {
    "gemini": "Google Gemini",
    "groq": "Groq",
    "gemma": "Gemma (runs on our own server)",
    "fake": "Test provider",
}


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
            app.state.renderer_problem = str(e)
        purged = app.state.cache.purge_expired()  # also hourly, from the cleanup timer (Data_model_v1 §4)
        log.info("cache.ready", kind=type(app.state.cache).__name__, entries=app.state.cache.size(), purged=purged)
        app.state.ready, app.state.failures = not failures, failures
        log.info("selftest.result", ok=result.ok, failures=failures, ephemeris_mode=swe.mode())
        log.info(
            "insight.ready",
            library=app.state.library.stats(),
            drafts_served=settings.allow_drafts,
            ai_providers=[f"{li.provider.name}:{li.provider.model}" for li in app.state.insights.chain.links],
            background_reword=app.state.insights.rewording is not None,
        )
        stop_purger = start_purger(app.state.cache)
        yield
        stop_purger()
        app.state.card_pool.shutdown(wait=False, cancel_futures=True)
        if app.state.insights.rewording is not None:
            app.state.insights.rewording.stop()

    # D86: no explorer pages anywhere, and no machine-readable API map in production. The frontend's
    # types come from the committed schema.gen.ts; tools call app.openapi() directly.
    openapi_url = None if settings.env == "prod" else "/openapi.json"
    app = FastAPI(
        title="Pranix API",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=openapi_url,
    )
    app.state.settings = settings
    app.state.geo = None
    app.state.ready, app.state.failures = False, []
    app.state.guests = GuestStore(settings.guest_ttl_seconds, settings.guest_cache_max)
    # One bounded pool for every card stream (bug bounty, 26 Nov): a pool per stream meant four threads per
    # open dashboard, and the stream itself held one of the 40 request threads while it waited.
    app.state.card_pool = ThreadPoolExecutor(max_workers=settings.card_workers, thread_name_prefix="cards")
    app.state.limits = {
        "places": TokenBucket(settings.rate_places_per_min),
        "profiles": TokenBucket(settings.rate_profiles_per_min),
        "insights": TokenBucket(settings.rate_insights_per_min),
        "images": TokenBucket(settings.rate_images_per_min),
        "inspect": TokenBucket(settings.rate_inspect_per_min),
    }
    app.state.renderer = None
    app.state.image_cache = {}
    app.state.library = Library(allow_drafts=settings.allow_drafts)
    app.state.cache = open_cache(settings.cache_path)
    app.state.llm = router(settings)  # raises RoutingError on a config that could leak typed text (D82)
    app.state.insights = InsightService(
        app.state.library,
        app.state.llm.chain("card_reading"),
        cache=app.state.cache,
        background=app.state.llm.background,
        reword_max=settings.background_reword_max,
        reword_gap_s=reword_gap_s(settings),
    )
    install(app)
    app.add_middleware(Guard)  # innermost of ours, so the access log below still sees the 500

    @app.middleware("http")
    async def access_log(request: Request, call_next: Any) -> Any:
        # Route pattern only (e.g. /v1/places/nearest): never the query string, ids or bodies.
        start = time.perf_counter()
        response = await call_next(request)
        # API answers carry someone's chart or place: never stored by a browser or proxy cache unless
        # a route says otherwise (bug bounty, 26 Nov). The card stream, Inspector and images set their own.
        if request.url.path.startswith("/v1/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "private, no-store"
        route = request.scope.get("route")
        access.info(
            "http.request",
            method=request.method,
            route=getattr(route, "path", "unmatched"),
            status=response.status_code,
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
        )
        return response

    app.add_middleware(Csrf)
    app.add_middleware(BodyLimit)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:  # on the event loop: answers even when every worker thread is busy
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
            # how charts are made (D86 A6): shown on How we calculate, moved here from every chart
            "method": {"ayanamsa": "lahiri", "node_type": "mean", "house_system": "whole_sign"},
            "feature_flags": {
                "chat": settings.feature_chat,
                "inspect": settings.feature_inspect,
                "passkeys": settings.feature_passkeys,
            },
            "ai_providers": sorted(
                {PROVIDER_LABELS.get(li.provider.name, li.provider.name) for li in app.state.insights.chain.links}
            ),
        }

    app.include_router(routes_geo.router)
    app.include_router(routes_profiles.router)
    app.include_router(routes_insights.router)
    app.include_router(routes_charts.router)
    app.include_router(routes_inspect.router)
    app.state.spa = web.install(app, settings.web_dist)  # after the API routes so they win
    return app


app = create_app()
