# SPDX-License-Identifier: AGPL-3.0-only
"""App factory: health, version and place endpoints. Chart and insight routes arrive in P1."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from .. import __version__
from ..config.settings import get_settings
from ..ephemeris import selftest, swe
from ..ephemeris.master import SCHEMA_VERSION
from ..ephemeris.ruleset import load_ruleset
from ..geo.index import GeoIndex
from ..geo.tz import tz_at
from ..obs.logging import configure
from .problems import ProblemError, install

log = structlog.get_logger()


def create_app() -> FastAPI:
    settings = get_settings()
    configure()
    state: dict[str, Any] = {"ready": False, "failures": [], "geo": None}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        swe.init(settings.ephe_path)
        result = selftest.run()
        failures = list(result.failures)
        try:
            state["geo"] = GeoIndex(settings.geo_db_path)
            log.info("geo.ready", places=state["geo"].count)
        except (FileNotFoundError, OSError):
            failures.append("geo_index_missing")
        state["ready"], state["failures"] = not failures, failures
        log.info("selftest.result", ok=result.ok, failures=failures, ephemeris_mode=swe.mode())
        yield

    app = FastAPI(title="Pranix API", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    install(app)

    def geo() -> GeoIndex:
        g: GeoIndex | None = state["geo"]
        if g is None:
            raise ProblemError(503, "SERVICE_NOT_READY", "Place search is not available yet.", retry_after=30)
        return g

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    def readyz() -> JSONResponse:
        if state["ready"]:
            return JSONResponse({"status": "ready"})
        return JSONResponse({"status": "not_ready", "failures": state["failures"]}, status_code=503)

    @app.get("/version")
    def version() -> dict[str, Any]:
        rs = load_ruleset()
        return {
            "engine_version": __version__,
            "schema_version": SCHEMA_VERSION,
            "ruleset": {"id": rs.id, "version": rs.version, "hash": rs.hash},
            "ephemeris_mode": swe.mode(),
            "feature_flags": {"chat": settings.feature_chat, "passkeys": settings.feature_passkeys},
        }

    @app.get("/v1/places", tags=["geo"])
    def search_places(
        q: str = Query(min_length=2, max_length=80), limit: int = Query(default=8, ge=1, le=10)
    ) -> list[dict[str, Any]]:
        """Offline autocomplete; [] when nothing matches (FR-GEO-01)."""
        return [p.to_dict() for p in geo().search(q, limit)]

    @app.get("/v1/places/nearest", tags=["geo"])
    def nearest_place(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)) -> dict[str, Any]:
        """Map pin (D64): nearest place within 50 km or null; tz always from the coordinates."""
        lat, lon = round(lat, 4), round(lon, 4)
        tz = tz_at(lat, lon)
        if tz is None:
            raise ProblemError(422, "OCEAN_OR_NO_TZ", "That point has no land time zone. Pick a point on land.")
        hit = geo().nearest(lat, lon)
        return {
            "place": hit[0].to_dict() if hit else None,
            "tz": tz,
            "distance_km": round(hit[1]) if hit else None,
        }

    return app


app = create_app()
